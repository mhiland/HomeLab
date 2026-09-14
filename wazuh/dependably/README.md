# Dependably audit feed into Wazuh

Monitors the self-hosted dependably artifact registry at `dependably.northwardlabs.ca`
from the homelab Wazuh manager (192.168.2.18, v4.12.0). Proof of concept for
[dependably-community#668](https://gitlab.northwardlabs.ca/moonlitlabs/dependably-community/-/work_items/668).
The generalized, product-facing write-up ships in `dependably-documentation` →
[Integrations → SIEM and SOC integration](https://gitlab.northwardlabs.ca/moonlitlabs/dependably-documentation/-/blob/main/docs/en/integrations/siem/index.md) -
this file stays the homelab-specific implementation log: what broke, what a generic operator
guide would never need to say, and the exact commands for this deployment.

```
dependably.northwardlabs.ca                         studio (Wazuh agent 011)
  GET /api/v1/siem/events/auth      ─┐
  GET /api/v1/siem/events/activity  ─┴──────────►  dependably-siem-poller.py  (launchd, 60 s)
                                                             │
                                                             ▼
                                          ~/Library/Logs/dependably-siem/audit.log
                                                         │  one JSON object per line
                                                         ▼
                                     wazuh-logcollector  <log_format>json</log_format>
                                                         ▼
                        manager ── dependably_rules.xml (100100-100199) ── "Dependably Registry"
```

## Why pull and not push

Dependably ships both a push forwarder (`SIEM_WEBHOOK_URL` / `SIEM_SYSLOG_HOST`) and a
pull API. Pull wins here on every axis that matters:

| | Push | Pull |
|---|---|---|
| Real time | yes | no (60 s) |
| Needs an instance restart + env change | yes | no |
| Backfills existing history | no | yes, to `SIEM_MAX_LOOKBACK_DAYS` (90) |
| Carries `source_ip` | no - `SiemEvent` omits it | yes |
| Wazuh ingests it natively | no (CEF needs a decoder; no HTTP receiver) | yes |

## Install

1. **Token.** A dependably API token carrying `read:audit`. Never in this repo:

       mkdir -p ~/Library/Application\ Support/dependably-siem-poller
       chmod 700 ~/Library/Application\ Support/dependably-siem-poller
       printf '%s' '<token>' > ~/Library/Application\ Support/dependably-siem-poller/token
       chmod 600 ~/Library/Application\ Support/dependably-siem-poller/token

2. **Poller under launchd** (runs as your user, no privileges needed):

       cp ca.northwardlabs.dependably-siem-poller.plist ~/Library/LaunchAgents/
       launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ca.northwardlabs.dependably-siem-poller.plist
       launchctl list | grep dependably-siem

3. **Agent config** (needs sudo):

       sudo ./install-agent-config.sh

   It creates `/usr/local/var/log/dependably-siem` owned by you, inserts the `<localfile>`
   **inside the first `<ossec_config>` block**, restarts the agent with a clean PATH, and
   prints the count of files logcollector has opened. Do not append a new `<ossec_config>`
   block: on this agent an appended block parses without error, reports nothing from
   `wazuh-logcollector -t`, and is then silently ignored. That is how the Docker shipper's
   block in `../mac-studio-docker/` came to be inert without anyone noticing - those logs
   have no rules, so no alert was ever expected and nothing distinguished "no rules" from
   "not being read". Old manual steps, kept only for reference:

       # Absolute path, not ~: `sudo sh -c` expands ~ against root's home, not yours,
       # so a tilde here silently appends nothing and the restart still succeeds.
       sudo sh -c 'cat /Users/michael/Projects/HomeLab/wazuh/dependably/ossec.conf.dependably.xml >> /Library/Ossec/etc/ossec.conf'
       sudo grep -c dependably-siem /Library/Ossec/etc/ossec.conf    # must print 1, not 0
       sudo env PATH=/usr/bin:/bin:/usr/sbin:/sbin /Library/Ossec/bin/wazuh-control restart

4. **Manager rules.** Dashboard, Server management, Rules, Import files, upload
   `dependably_rules.xml` (tick Overwrite when replacing). **A manager restart is required for
   the import to take effect** — see "The gotcha that cost the most time" below; `Server
   management > Rules` and `/logtest` both look correct while analysisd is still on the old
   ruleset, so do not use either as confirmation. `Server management > Status > Restart`, then
   verify with a real search on `wazuh-alerts-*`.

5. **Dashboard.** Dashboards Management, Saved objects, Import `dependably-dashboard.ndjson`.
   Opens at Dashboards, "Dependably Registry". The importer **regenerates object ids**, so a
   second import creates a duplicate dashboard rather than replacing the first - delete the
   old one.

   Then refresh the `wazuh-alerts-*` field list and add the scripted fields the vulnerability
   panels aggregate over (`install-scripted-fields.js`). Wazuh's JSON decoder stringifies
   every value, so `packages_affected` and the severity counts arrive as keywords that
   `max()` cannot touch; `dep_critical` and friends parse them back to numbers.

   Each scripted field must begin with `doc.containsKey(...)`. Indices written before this
   feed existed carry no mapping for the field, and `doc['missing.field']` **throws** - one
   `script_exception` shard failure per old index, which OpenSearch surfaces as a partial
   result ("1 of 24 shards failed"), not an error. `f.size() == 0` does not cover this: it
   guards a field that exists and is empty, which is a different condition. Verify over the
   whole index set with no time filter, since a dashboard-sized window only touches today's
   index and will look clean while older shards fail.

6. **Replay history into the new feed.** `wazuh-logcollector` seeks to the end of a file it
   has not seen before, so everything written before step 3 is never read. Re-emit it:

       ./dependably-siem-poller.py --replay 2160     # 90 days, the server's lookback cap

   Those alerts carry ingest time as their `timestamp`; `data.dependably.event_time` holds
   the real instant, and the dashboard tables show that column instead.

## What it detects

Rules `100100-100199`. Every rule below is transcribed directly from `dependably_rules.xml`
(`grep '<rule id=' dependably_rules.xml` reproduces this table verbatim) rather than kept by
hand, after this table drifted from the real ruleset once already — see git history for what
that looked like.

Severity reflects **what a SOC can act on**, not what is technically interesting. The test each
rule has to pass: if this fires at 02:00, is there something to do about it?

| Rule | Level | Signal |
|---|---|---|
| 100113 | 12 | successful login straight after a run of failures - possible brute-force success |
| 100106 | 10 | repeated policy refusals from one actor - possible probing |
| 100103 | 10 | **BLOCKED** a known-malicious or actively-exploited package |
| 100111 | 10 | repeated failed logins - possible brute force or password spray |
| 100114 | 10 | account lockout triggered |
| 100125 | 10 | repeated authorization denials from one actor - possible capability probing |
| 100126 | 10 | SAML role change - privilege movement through the IdP |
| 100128 | 10 | MFA **weakened** - disabled, or a recovery code spent |
| 100140 | 10 | privilege change (`rbac.*` / `auth.saml.role*`) |
| 100152 | 10 | tenant **deleted** |
| 100153 | 10 | a **security** setting changed (policy, enforcement, verify, overwrite, MFA, SSO) |
| 100170 | 10 | the poller itself failed |
| 100104 | 7 | blocked on vulnerability score (EPSS / vuln_score threshold) |
| 100124 | 7 | authorization denied - a credential attempting what it is not entitled to |
| 100127 | 7 | SAML configuration changed |
| 100129 | 7 | MFA lifecycle event (enrolled, disabled, recovery code used, ...) |
| 100130 | 7 | API token created |
| 100141 | 7 | credential change (password, email) |
| 100151 | 7 | tenant lifecycle (created, restored, status/quota changed) |
| 100154 | 7 | instance-operator action - legitimate admin work, and what a stolen operator session does too |
| 100105 | 5 | blocked by policy (licence, provenance, deprecation, install script, revoked, manual, release age) |
| 100110 | 5 | failed login (live) |
| 100131 | 5 | API token revoked |
| 100150 | 5 | a (non-security) setting changed |
| 100101 | 3 | audit-plane catch-all, so a newly added action is indexed before it has a rule of its own |
| 100102 | 3 | activity-plane catch-all, same purpose |
| 100112 | 3 | login (live) |
| 100115 / 100116 | 3 | failed / successful login, **backfilled history** - no correlation group, cannot feed 100111/100113 |
| 100100 | 0 | parent; matches any record the poller wrote, never itself indexed |

### Two feeds, and only one of them exists on every instance

The collector drains both SIEM pull feeds every run:

| Feed | Carries | Watermark |
|---|---|---|
| `/api/v1/siem/events/auth` | the `audit_log` plane - authentication, credential and capability refusals, MFA, SAML, security-setting change | ours: we pass `until` and commit it on a clean drain |
| `/api/v1/siem/events/activity` | the `activity` plane - every block-gate refusal (`blocked_*`) | **the server's**: see below |

They are polled in **separate `try` blocks holding separate watermarks and separate de-dupe
rings**. Sharing either would mean a permanently broken activity feed stopped the audit feed
from ever advancing, so the collector would fall further behind on both every run while
reporting one error.

**The activity watermark is the server's to give.** That plane is written by a background
writer, so rows land late; the server subtracts its own lag from now, serves that window, and
reports it back as `until`. It also *withholds* `until` on a truncated page, because rows come
newest-first: a page carrying a cursor has served the newest slice and left older rows behind
it, and a collector advancing to its own idea of `now` there would skip them permanently. So
the collector takes `until` from the body, only once the cursor is exhausted, and never sends
an `until` of its own.

No `event=` filter is sent. The default for this feed is the whole `blocked*` family and no
downloads, which is exactly the SOC subscription - and unlike the audit feed's default it
cannot widen into non-refusal traffic, because adding downloads takes an explicit opt-in.

**A 404 on the activity feed is a deployment fact, not an incident.** An instance older than
the feed answers 404 forever, and at a 60-second poll that would post an identical
`poller_error` every minute until someone upgraded - which teaches an operator to scroll past
`poller_error`, including the real one. So the *state change* is the event: the collector emits
one record on the first 404, one more when the feed starts answering, and logs the rest. A 500
is still an incident and still fails the run.

`dependably.northwardlabs.ca` was on a build that answered 404 on both endpoints until it was
upgraded to 0.11.0 on 2026-09-14. The 404-quieting behaviour above was written and tested against
that exact transition, and the collector logged the recovery automatically, unattended, the first
poll after the upgrade - `activity feed is being served again`.

### What is deliberately not collected

`package.replace`, `project.create` and `project.created` are filtered out in the poller
(`EXCLUDED_ACTIONS`), not merely down-ranked. They are DevOps operational insight and they
already live in dependably's own audit trail; forwarding them spends bandwidth, index space and
field cardinality on events a SOC would never act on.

`package.replace` in particular *looks* like tamper - "published bytes swapped under a version
that already existed" - and was originally level 12. It is not a detection here:

- The publishers in a private registry are your own developers.
- Whether a replace is permitted is the org's `version_overwrite_policy`, and the event **does
  not carry that policy**, so no rule can separate a violation from normal churn.
- It was ~13% of the feed and **100% of the level-12 tier**, which is how a SOC learns to mute a
  rule and loses the genuine edge cases with it.

The security-relevant form of the question - "did a replace happen where policy forbade it?" -
is a block-gate denial, and unlike `package.replace` itself, that **does** reach Wazuh: it lands
on the activity plane and matches rules 100102-100106 (dependably-community#670, closed).
`package.replace` and `project.create`/`project.created` remain deliberately excluded; only the
noise is gone, not the signal.

**Trade-off accepted:** the excluded events themselves are not available in Wazuh as forensic
context during an investigation. Pivot to dependably's own audit trail for that.

After filtering, every action that reaches Wazuh is security-relevant. Representative, not
exhaustive - `GET /api/v1/siem/actions` publishes the full declared vocabulary:

    login.success  login.failure  oci.scope_denied  auth.saml.*  saml.*
    mfa.*  tenant.setting.change  tenant.deleted  token.created
    blocked_deprecated  blocked_license  blocked_malicious  blocked_*  (the whole family)

`package.override.set` is in `EXCLUDED_ACTIONS`, same as `package.replace` - it never reaches
Wazuh at all, despite earlier revisions of this doc describing a dedicated rule (id 100122) for
it. That rule does not exist in the current `dependably_rules.xml`, and `EXCLUDED_ACTIONS`
confirms the omission is deliberate, not a regression: the doc drifted, the poller did not.

Two design points worth keeping:

- **Wazuh rules cannot compare one field against another.** `shape_event` still computes
  `dependably.artifact_hash_changed` for a `package.replace` event - "did the artifact bytes
  actually change?" is exactly the kind of question only the poller can answer, by comparing
  two fields dependably's own event carries - but `package.replace` is in `EXCLUDED_ACTIONS`
  and never reaches `shape_event` in the current build, so the field is currently dead code and
  no rule matches it. The design point (compute cross-field comparisons in the poller, publish
  the answer as a plain value a rule can match) is still the right one to keep in mind for the
  next action that needs it.
- **Field matches are pinned to `type="pcre2"`.** In OS_Regex `\.` means *any character*,
  so `^login\.failure$` would quietly also match `loginXfailure`.

## What it could not detect, and what changed

These were properties of dependably's SIEM surface, not of this integration, tracked as gaps
dependably-community#669-674 off the PoC issue #668. All six are now closed - most of what this
section originally listed here as a permanent limitation was fixed underneath this integration
without anything in `dependably-siem-poller.py` needing to change. What remains is genuinely
either closed or a deliberate design choice, not an open gap:

- **Policy denials now reach Wazuh** (#670, closed). A blocked pull lands on dependably's
  `activity` plane; the collector polls it (`poll_activity`, above) and rules 100102-100106
  match it. This was the single highest-value gap this section used to name, and it is the one
  most thoroughly verified: a live replay landed 428 activity events in `wazuh-alerts-*`, and a
  `blocked_deprecated` row resolved to `rule.id: 100105`, confirming the tiered rule fires and
  not just the catch-all.
- **The action vocabulary is no longer hardcoded** (#669, closed). `action=` matches the action
  of exactly that name plus its dotted family - not a bare prefix - and `GET
  /api/v1/siem/actions` publishes the full declared vocabulary plus the two limits a request may
  carry. `ACTION_PREFIXES` in the poller is now a list of dotted-family roots chosen for cost
  (each costs an unindexable `LIKE`), not a list of the only names reachable at all.
- **`orgSlug` is projected** (#671, closed - partially). `shape_event`/`shape_activity_event`
  read `item.get("orgSlug")` and it resolves to a real slug, not null, confirmed live. `actorEmail`
  remains always null - that half stays deliberate, not a gap: a user's display name is an email,
  and it would be personal data outside the retention/erasure sweeps' fixed column list.
- **`source_ip` attribution now depends on your own deployment, not on dependably.**
  `TRUSTED_PROXIES` unset is still the documented fail-closed default (#672, closed - the
  startup warning shipped; setting the value is still the operator's job). On this instance it
  is now set, and Web Station's proxy was also, separately, not sending `X-Forwarded-For` at
  all until that was added too - both were needed. Verified live: a test login through the real
  proxy recorded the connecting address, not the Docker bridge gateway.
- **Push carries strictly less than pull, and now says so** (#673, closed - documentation only,
  the gap in push itself is unchanged: no `source_ip`, no backfill, drops on queue overflow).
  Irrelevant to this integration, which only ever used pull.
- **`project.create` vs `project.created`** (#674, closed) - a duplicate-spelling bug in the
  writer, not a reader-side gap; not something this poller ever needed to work around.

## The gotcha that cost the most time: analysisd does not reload the ruleset

**Importing a rules file does not put it into effect. The manager has to be restarted.**

What makes this expensive is that the two obvious ways to verify a rule both pass while the
running manager is still using the old ruleset:

- `GET /rules` lists the new rules -- it reads the **files** on disk, not what analysisd loaded.
- `/logtest` fires them correctly -- a logtest session **loads its own copy** of the ruleset
  from disk when the session opens.

So the rules can look installed and verified from every angle while live events produce
nothing at all. The fix:

    PUT /manager/restart          # or Server management > Status > Restart

Verify with real events rather than logtest:

    GET wazuh-alerts-*/_search  {"query":{"term":{"rule.groups":"dependably"}}}

Two things that look like this failure but are not:

- **`grep -c 'analyzing file'` returning 0 does not mean no file is being read.** logcollector
  logs `Analyzing file:` for a literal `<location>` but not for a wildcard one. The authority
  on what is actually being tailed, and how far, is
  `/Library/Ossec/queue/logcollector/file_status.json` -- it lists every file with a byte
  offset. Check that, not ossec.log.
- **Wildcard `<location>` works fine.** So does appending a separate `<ossec_config>` block.
  Both were suspected here and both were wrong.

## Backfilled events must never drive time-window rules

Wazuh correlates on **ingest** time, not on the event's own timestamp. A backfill therefore
lands months of scattered events in a single second and manufactures correlations that never
happened. The first PoC run produced four "repeated failed logins - possible brute force"
alerts whose underlying events were days apart; a first install would do the same, because the
default first run backfills 24 hours.

The poller stamps every record with `dependably.live` - true when the event was less than
`LIVE_WINDOW_SECONDS` (300) old at collection time. The rule pairs split on it:

| | live | backfilled |
|---|---|---|
| `login.failure` | 100110, level 5, feeds the frequency window | 100115, level 3, **no correlation group** |
| `login.success` | 100112, level 3, `authentication_success` | 100116, level 3, **no correlation group** |

The decision is made in the poller because a Wazuh rule cannot compare `event_time` to now.

Verify both directions after any change here - a one-sided test proves nothing, since a rule
that never fires also passes the negative case:

    12 backfilled failures -> 100115 x12, and 100111 must NOT appear
    12 live failures       -> 100110, with 100111 firing on the 8th

## A pinned filter silently narrows every panel

Clicking a bar or a table cell pins a dashboard-level filter that ANDs into every panel's own
query. It is easy to miss in the filter bar and invisible in a screenshot.

**The tell is unrelated tiles showing the same number.** A pinned
`artifact_hash_changed: true` produces:

    Audit events 45 | Supply-chain alerts 45 | Artifact bytes replaced 45
    Failed logins 0 | CRITICAL vulns - | Packages affected -

...because a login has no artifact hash and a vulnerability snapshot has no such field at all,
so `max` has nothing to aggregate and renders `-`. Nothing is broken; clear the filter pill.

Unfiltered all-time counts as of the PoC, for comparison: Audit events 332, Supply-chain
alerts 81, Artifact bytes replaced 45, Failed logins 40.

## A transient upstream 400 was observed, and handled correctly

On 2026-09-12 two consecutive polls returned HTTP 400 and the next succeeded with the same
watermark and the same request shape. The instance logged no errors, and the identical query
reproduced 200 immediately afterwards, so the cause is unexplained rather than diagnosed — recorded
here as an observation, not a root cause.

What matters is that the collector behaved as designed under an unplanned fault: it **held the
watermark**, emitted two `poller_error` records, and re-read the same window on recovery. No events
were lost and the gap is visible in the SIEM (rule 100170, level 10) rather than silent. That
property had only ever been exercised by induced failures — a forced 401 and an unresolvable
host — so this is the first time it was proven against a real one.

If it recurs, capture the response body: the endpoint returns a `detail` string naming the
rejected parameter, and the two candidates worth ruling out first are a `since`/`until` pair that
collapses to zero width, and an over-long repeated `action=` list.

## Expect up to two minutes of latency

A new event is not visible on the dashboard immediately, and that is normal. Two 60-second
waits stack:

1. the poller's launchd `StartInterval` (up to 60 s before the event is collected), and
2. the dashboard's own auto-refresh (another 60 s).

So failing a login and checking the dashboard straight away correctly shows nothing. To test
without waiting, force a poll and then hit Refresh:

    ./dependably-siem-poller.py && echo polled

If real-time matters more than `source_ip` and backfill, dependably's push forwarder
(`SIEM_SYSLOG_HOST`) is the trade to make - see the table at the top.

## Operating notes

- **Watermark discipline.** The poller advances its watermark only after a fully successful
  drain. A failed poll leaves it alone and re-reads the window next run, so a transient
  outage costs duplicates (which the id ring absorbs) rather than a silent hole.
- **Silence is ambiguous, so the poller reports its own failures** as `poller_error`
  records behind rule 100170. An empty "Feed health" panel is the healthy state.
- **`detail` is lifted through a closed allowlist** (`DETAIL_KEYS`). The payload is
  free-form per action; letting it expand straight into the index means an unbounded field
  count in `wazuh-alerts-*`. Anything not listed survives verbatim in `detail_raw`.
- **Removal:** `launchctl bootout gui/$(id -u)/ca.northwardlabs.dependably-siem-poller`,
  delete the plist, remove the `<ossec_config>` block, delete `dependably_rules.xml` from
  the manager, delete the saved objects, and remove `~/Library/Logs/dependably-siem` and
  `~/Library/Application Support/dependably-siem-poller` (the token lives there).

## Running the tests

`test_poller.py` sits next to the script rather than in a `tests/` directory - it is one
file testing one file, and importlib already has to work around the script's hyphenated
name (`import dependably-siem-poller` is not valid Python), so a package layout would add
a directory for no benefit here.

The script itself stays stdlib-only and pinned to `/usr/bin/python3` (see its docstring),
but `/usr/bin/python3` has no pip packages installed system-wide and none should be added
there. Build a throwaway venv **from that same interpreter** so the tests run under the
production Python, not whatever `python3` resolves to on PATH:

    /usr/bin/python3 -m venv /tmp/dependably-siem-poller-venv
    /tmp/dependably-siem-poller-venv/bin/pip install pytest
    /tmp/dependably-siem-poller-venv/bin/pytest test_poller.py -v

No network access is required or made: every test that reaches `poll_events()` monkeypatches
the module's `get_json` with a fake, and all state/log/token file paths are redirected into a
pytest `tmp_path` by the `sandbox` fixture. The suite covers, with a name per behaviour:

- watermark discipline (`test_main_holds_watermark_when_poll_fails`,
  `test_main_advances_watermark_and_emits_events_on_success`,
  `test_poll_events_holds_watermark_when_page_cap_hit_with_cursor_outstanding`)
- id-ring de-duplication, both within one run's page walk and across runs
  (`test_poll_events_dedupes_id_seen_within_the_same_run`,
  `test_poll_events_dedupes_id_seen_in_a_prior_run`)
- the `live`/backfilled split (`test_shape_event_marks_recent_event_live`,
  `test_shape_event_marks_old_event_not_live`)
- `EXCLUDED_ACTIONS` (`test_poll_events_drops_excluded_actions`)
- `artifact_hash_changed` (the four `test_shape_event_artifact_hash_changed_*` tests)
- the `DETAIL_KEYS` closed allowlist (`test_shape_event_lifts_only_allowlisted_detail_keys`)
- `poller_error` emission on a failed poll and on a missing/empty token
  (`test_main_holds_watermark_when_poll_fails`, `test_main_reports_missing_token_as_poller_error`,
  `test_main_reports_empty_token_as_poller_error`)
- the activity plane's server-given watermark, including the two cases where it must be held
  (`test_poll_activity_takes_the_watermark_from_the_server_not_the_clock`,
  `test_poll_activity_holds_the_watermark_when_the_server_withholds_until`,
  `test_poll_activity_holds_the_watermark_when_the_page_cap_is_hit`)
- the two planes not bleeding into each other - separate rings, separate watermarks, separate
  failure handling (`test_poll_activity_dedupes_on_its_own_ring`,
  `test_main_keeps_the_two_planes_watermarks_independent`, `test_replay_rewinds_both_planes`)
- the 404 quieting and its boundaries: once, not every minute; the recovery record; and a 500
  still failing loudly (`test_main_reports_an_absent_activity_feed_once_not_every_minute`,
  `test_main_reports_the_activity_feed_coming_back`,
  `test_main_still_fails_loudly_on_a_broken_activity_feed`)

Each property called out above as regression-critical was verified to actually fail on a
broken version of the code, not just pass on the current one. For the activity plane the
mutants run were: take the watermark from our own clock instead of the server's `until`
(2 red); share one de-dupe ring between the planes (1 red); fold the activity poll into the
audit feed's `try` (1 red); quiet every HTTP error rather than only 404 (2 red); and never
clear the absent flag (1 red).

## Files

| File | Where it goes |
|---|---|
| `dependably-siem-poller.py` | runs in place, from launchd |
| `test_poller.py` | run locally before shipping a change to the poller; not deployed |
| `ca.northwardlabs.dependably-siem-poller.plist` | `~/Library/LaunchAgents/` |
| `ossec.conf.dependably.xml` | appended to `/Library/Ossec/etc/ossec.conf` |
| `dependably_rules.xml` | manager `etc/rules/`, via the dashboard's rules importer |
| `dependably-dashboard.ndjson` | dashboard saved objects, via Import |
| `build-dashboard.py` | regenerates the ndjson; edit this, not the ndjson |
