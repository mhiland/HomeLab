# Dependably audit feed into Wazuh

Monitors the self-hosted dependably artifact registry at `dependably.northwardlabs.ca`
from the homelab Wazuh manager (192.168.2.18, v4.12.0). Proof of concept for
[dependably-community#668](https://gitlab.northwardlabs.ca/moonlitlabs/dependably-community/-/work_items/668);
the generalized write-up belongs in `dependably-documentation` as an integration section.

```
dependably.northwardlabs.ca                         studio (Wazuh agent 011)
  GET /api/v1/siem/events/auth  ──────────────►  dependably-siem-poller.py  (launchd, 60 s)
  GET /api/v1/siem/vulnerabilities/summary               │
      (every 15 min)                                     ▼
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
   `dependably_rules.xml` (tick Overwrite when replacing). No manager restart is needed;
   confirm with Server management, Rules, filter `Custom rules`.

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

Rules `100100-100199`, all verified against `/logtest` before shipping - including a
negative control (a non-dependably JSON line matches nothing) and the catch-all.

Severity reflects **what a SOC can act on**, not what is technically interesting. The test each
rule has to pass: if this fires at 02:00, is there something to do about it?

| Rule | Level | Signal |
|---|---|---|
| 100113 | 12 | login success inside 300 s of a failure burst |
| 100122 | 10 | `package.override.set` to `allow` - a human disabled a control for a named package |
| 100125 | 10 | repeated authorization denials from one actor - capability probing |
| 100126 | 10 | SAML role change - privilege movement through the IdP |
| 100153 | 10 | a **security** setting changed (policy, enforcement, verify, overwrite, MFA, SSO) |
| 100124 | 7 | authorization denied - a credential attempting what it is not entitled to |
| 100120 | **3** | `package.replace` - **operational, not a detection** (see below) |
| 100122 | 10 | `package.override.set` to `allow` - a human overrode a policy block on a named package |
| 100111 | 10 | 8 failed logins in 120 s |
| 100114 | 10 | account lockout |
| 100140 | 10 | `rbac.*` / `auth.saml.role*` privilege change |
| 100152 | 10 | tenant deleted |
| 100170 | 10 | the poller itself failed |
| 100123 / 100130 / 100141 / 100150 / 100151 / 100161 | 7 | publish, token created, credential change, setting change, tenant lifecycle, CRITICAL vulns present |
| 100101 | 3 | catch-all, so a newly added action is still indexed before it has a rule |

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
is a block-gate denial, which lives in the activity plane and never reaches a SIEM
(dependably-community#670).

**Trade-off accepted:** neither event is available in Wazuh as forensic context during an
investigation. Pivot to dependably's own audit trail for that.

After filtering, every action that reaches Wazuh is security-relevant:

    login.success  login.failure  oci.scope_denied  package.override.set
    tenant.setting.change  auth.saml.*  saml.*        (+ the vuln_summary gauge)

Two design points worth keeping:

- **Wazuh rules cannot compare one field against another**, so "did the artifact bytes
  actually change?" is decided in the poller and published as
  `dependably.artifact_hash_changed`, which rule 100120 matches as a plain value.
- **Field matches are pinned to `type="pcre2"`.** In OS_Regex `\.` means *any character*,
  so `^login\.failure$` would quietly also match `loginXfailure`.

## What it cannot detect, and why

These are properties of dependably's SIEM surface, not of this integration. All are
recorded as gaps G1-G5 on issue #668.

- **Failed logins are unattributable.** `login.failure` rows carry no actor id and no
  email. Behind a reverse proxy with `TRUSTED_PROXIES` unset - the documented fail-closed
  default - every `source_ip` is the Docker bridge gateway, `172.17.0.1`. Rule 100111
  counts failures honestly; nothing can say whose or from where.
- **Policy denials are invisible.** A blocked pull lands in dependably's `activity` plane;
  the SIEM endpoint reads `audit_log`, and the two are deliberately never dual-written.
  "Someone tried to pull a package the policy blocks" is the highest-value detection this
  product could emit and it does not reach a SIEM at all.
- **Everything is an opaque id.** `actorEmail` and `orgSlug` are always null in the feed.
- **The action vocabulary is hardcoded.** `action=` is a repeatable prefix filter with no
  wildcard, so `ACTION_PREFIXES` in the poller has to name every category, and a category
  dependably adds later is silently absent until it is added there too.

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

Each of the four properties called out above as regression-critical was verified to actually
fail on a broken version of the code, not just pass on the current one - see the mutant table
in the change that introduced this suite.

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
