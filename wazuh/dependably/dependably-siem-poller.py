#!/usr/bin/python3
"""Pulls the dependably audit feed into a JSON log file the Wazuh macOS agent tails.

Runs from launchd once a minute; no persistent process. Stdlib only, and pinned to
/usr/bin/python3 (the Command Line Tools interpreter) for the same reason the Docker
listener is — that is the interpreter launchd's clean PATH resolves at boot.

Each run pulls the window (watermark, now] from GET /api/v1/siem/events/auth, follows
next_cursor to exhaustion, and appends one JSON object per line to the output log. The
watermark advances only after a fully successful drain, so a failed poll re-reads its
window on the next run instead of leaving a hole nobody can see.

A poll that fails emits a poller_error record. A collector that has stopped collecting
has to be visible in the SIEM; silence is indistinguishable from "nothing happened".
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
INSTANCE = os.environ.get("DEPENDABLY_SIEM_URL", "https://dependably.northwardlabs.ca")
TOKEN_FILE = os.environ.get(
    "DEPENDABLY_SIEM_TOKEN_FILE",
    os.path.join(HOME, "Library/Application Support/dependably-siem-poller/token"),
)
STATE_DIR = os.path.join(HOME, "Library/Application Support/dependably-siem-poller")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
# Deliberately NOT under ~/Library: wazuh-logcollector runs as root, and pointing a system
# daemon at a path inside a user's home is fragile on macOS (it depends on the user being
# logged in, and on whatever TCC decides about ~/Library in the next OS release).
OUT_DIR = os.environ.get("DEPENDABLY_SIEM_LOG_DIR", "/usr/local/var/log/dependably-siem")
OUT_FILE = os.path.join(OUT_DIR, "audit.log")
SELF_LOG = os.path.join(HOME, "Library/Logs/dependably-siem-poller.log")

MAX_BYTES = 20 * 1024 * 1024        # rotate the output past this size, one .1 kept
PAGE_LIMIT = 500                    # server clamps to 500
MAX_PAGES = 40                      # 20k events per run; a cursor loop cannot run away
RECENT_IDS_KEPT = 2000              # de-dupe ring, see DEDUPE below
# An event older than this at collection time is history, not something happening now. Wazuh
# correlates on INGEST time, so backfilled events would otherwise fabricate bursts: a 24h first
# run replays a day of scattered failures into one second and trips the brute-force rule on
# activity that never happened. Every record carries dependably.live, and only live ones feed
# the time-window rules.
LIVE_WINDOW_SECONDS = 300
HTTP_TIMEOUT = 30
BACKFILL_HOURS = int(os.environ.get("DEPENDABLY_SIEM_BACKFILL_HOURS", "24"))

# The action filter builds `LIKE '<prefix>.%'` server-side -- always with a trailing dot. So
# only actions that CONTAIN a dot can ever be returned, and these twelve prefixes are the
# complete reachable set (34 of dependably's 86 audit_log actions as of 0.10.0).
#
# The other 52 are flat names with underscores (checksum_failure, ssrf_blocked,
# provenance_verification_failed, upstream_source_pin_violation, token_created,
# member_role_changed, trust_anchor_added, quarantine_decision, ...) and NO value of `action=`
# can match them -- passing "token_created" yields the pattern 'token_created.%'. They are not
# missing from this list; they are unreachable through the API. Several are exactly the events
# a SIEM most wants. Filed against dependably as a blocking gap on issue #668.
#
# Note the server's own documented default (login. lockout. token. rbac.) is half dead for the
# same reason: the writers emit token_created and member_role_changed, so `token.` and `rbac.`
# match nothing. Never rely on the default; always pass this list explicitly.
ACTION_PREFIXES = [
    "login", "lockout", "auth", "saml", "user",      # authentication and accounts
    "mfa",                                           # MFA lifecycle: disable, recovery-code use
    "oci", "metrics", "ratelimit",                   # authorization/access denials
    "tenant", "system_admin",                        # security configuration, operator actions
]

# `auth.` above already covers the credential-refusal families dependably-community#676 adds
# (auth.token.rejected, auth.capability.denied); `ratelimit.` covers #678. Both are listed
# rather than assumed because the server's own default set cannot be relied on -- two of its
# four documented prefixes match no writer at all.
#
# POLICY DENIALS ARE NOT ON THIS FEED. Blocked pulls live on the activity plane, served by
# /api/v1/siem/events/activity (dependably-community#677a) -- a separate endpoint with its own
# cursor and its own lag cap. Until that ships and this collector grows a second poll loop, a
# SOC watching only this feed cannot see that a pull was refused by policy, which is the
# highest-value detection the registry emits. Tracked as the remaining work in #668.

# Actions collected by the prefixes above but deliberately NOT forwarded. These are DevOps
# operational insight, not security telemetry: they belong in dependably's own audit trail,
# which already has them. Dropping at the poller rather than with a level-0 rule means no
# bandwidth, no index space and no field cardinality spent on events a SOC would never act on.
#
# package.replace: a developer republishing a version. Whether that is permitted is the org's
#   version_overwrite_policy, and the event does not carry it, so no rule could separate a
#   policy violation from normal churn. The security-relevant form of this question is a
#   block-gate denial (dependably-community#670), not this event.
# package.override.set: an authorized admin accepting a risk for one package, through the
#   product's intended workflow. A SOC cannot triage it -- the event records only
#   {ecosystem, purl_name, override_value} with NO blocked arm, so there is no way to tell a
#   waved-through licence mismatch from a waved-through known-malicious package, and those
#   demand opposite responses. The answer always lives with the registry owner, so the alert
#   routes straight back. Its proper home is the quarantine review workflow
#   (QuarantineController's quarantine_decision), not a SIEM.
# project.create / project.created: project lifecycle. Two spellings exist for the same event
#   -- ProjectsController writes "project.created", SbomController writes "project.create".
#
# Trade-off accepted: neither is available in Wazuh as forensic context during an
# investigation. Pivot to dependably's own audit trail for that.
EXCLUDED_ACTIONS = frozenset({
    "package.replace",
    "package.override.set",
    "project.create",
    "project.created",
})

# Detail keys lifted to stable first-class fields so rules can match on a fixed name.
# Deliberately a closed allowlist: `detail` is free-form per action, and letting it
# expand straight into the index means an unbounded field count in wazuh-alerts-*.
# Everything not listed survives verbatim in detail_raw.
DETAIL_KEYS = (
    "method", "prior_artifact_hash", "artifact_hash", "override_value", "origin",
    "purl_name", "setting", "reason", "realm", "role", "outcome", "ecosystem",
    "email", "target_user", "capabilities", "status", "provider",
    # tenant.setting.change carries the security posture that actually moved.
    "key", "prior_value", "new_value",
)


def log(msg):
    line = "%s %s\n" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), msg)
    try:
        with open(SELF_LOG, "a") as fh:
            fh.write(line)
    except OSError:
        sys.stderr.write(line)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        "%03dZ" % (dt.microsecond // 1000)


def read_token():
    with open(TOKEN_FILE) as fh:
        return fh.read().strip()


def load_state():
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_FILE)


def rotate_if_needed():
    try:
        if os.path.getsize(OUT_FILE) > MAX_BYTES:
            os.replace(OUT_FILE, OUT_FILE + ".1")
    except OSError:
        pass


def emit(records):
    if not records:
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    rotate_if_needed()
    with open(OUT_FILE, "a") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def get_json(path, params, token):
    url = INSTANCE.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "dependably-siem-poller/1.0 (wazuh)",
    })
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def error_record(stage, message):
    return {
        "timestamp": iso(datetime.now(timezone.utc)),
        "dependably": {
            "instance": urllib.parse.urlsplit(INSTANCE).netloc,
            "record_type": "poller_error",
            "stage": stage,
            "message": str(message)[:500],
        },
    }


def shape_event(item, instance):
    """Turns one AuditEntry into the record Wazuh indexes."""
    action = item.get("action") or "unknown"
    dep = {
        "instance": instance,
        "record_type": "audit",
        "event_id": item.get("id"),
        "event_time": item.get("createdAt"),
        "action": action,
        # First segment, so a rule can match a whole family without a regex.
        "action_category": action.split(".", 1)[0],
        "scope": item.get("scope"),
        "org_id": item.get("orgId"),
        "org_slug": item.get("orgSlug"),
        "actor_id": item.get("actorId"),
        "actor_email": item.get("actorEmail"),
        "ecosystem": item.get("ecosystem"),
        "purl": item.get("purl"),
        "source_ip": item.get("sourceIp"),
    }

    # live vs history, decided here because a Wazuh rule cannot compare event_time to now.
    created = item.get("createdAt")
    dep["live"] = "false"
    if created:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds()
            dep["live"] = "true" if age <= LIVE_WINDOW_SECONDS else "false"
        except ValueError:
            pass

    raw = item.get("detail")
    detail = {}
    if raw:
        dep["detail_raw"] = raw if isinstance(raw, str) else json.dumps(raw)
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict):
                detail = parsed
        except ValueError:
            pass
    for key in DETAIL_KEYS:
        if key in detail and detail[key] is not None:
            dep["detail_" + key] = str(detail[key])

    # Wazuh rules cannot compare one field against another, so the comparison that makes
    # package.replace interesting -- did the bytes actually change? -- is decided here and
    # published as a plain field the rule can match.
    if action == "package.replace":
        prior = detail.get("prior_artifact_hash")
        current = detail.get("artifact_hash")
        if prior and current:
            dep["artifact_hash_changed"] = "true" if prior != current else "false"

    return {
        "timestamp": item.get("createdAt"),
        "dependably": {k: v for k, v in dep.items() if v is not None},
    }


def poll_events(token, state, instance):
    """Returns (records, new_watermark) or raises. Watermark is only the caller's to commit."""
    now = datetime.now(timezone.utc)
    watermark = state.get("watermark")
    if not watermark:
        watermark = iso(now - timedelta(hours=BACKFILL_HOURS))
        log("no watermark; backfilling %d hours from %s" % (BACKFILL_HOURS, watermark))
    until = iso(now)

    seen = set(state.get("recent_ids", []))
    records, fresh_ids = [], []
    cursor, pages = None, 0

    while pages < MAX_PAGES:
        params = {
            "since": watermark,
            "until": until,
            "limit": PAGE_LIMIT,
            "action": ACTION_PREFIXES,
        }
        if cursor:
            params["cursor"] = cursor
        body = get_json("/api/v1/siem/events/auth", params, token)
        items = body.get("items") or []
        for item in items:
            if item.get("action") in EXCLUDED_ACTIONS:
                continue
            eid = item.get("id")
            # DEDUPE: ListAuthEventsAsync closes the window on both ends (>= / <=), so an
            # event landing on exactly the millisecond we pass as `until` comes back again
            # next run when that same instant is the `since`. The ring is sized well above
            # one run's realistic volume.
            if eid and eid in seen:
                continue
            if eid:
                seen.add(eid)
                fresh_ids.append(eid)
            records.append(shape_event(item, instance))
        cursor = body.get("next_cursor")
        pages += 1
        if not cursor:
            break
    else:
        # Fell out on MAX_PAGES with a cursor still live: the window is bigger than one run
        # can drain. Do NOT advance the watermark -- the next run picks the rest up.
        log("page cap hit with cursor outstanding; leaving watermark at %s" % watermark)
        return records, watermark, fresh_ids

    return records, until, fresh_ids



def replay(hours):
    """Rewinds the watermark so the next run re-emits an already-collected window.

    Needed because wazuh-logcollector seeks to the end of a file it has not seen before:
    lines the poller wrote before the agent was configured are never read. Re-emitting them
    appends them as new lines, which the agent does pick up. The alert timestamps are then
    ingest time, not event time -- data.dependably.event_time carries the real instant, and
    the dashboard's tables show that column rather than the alert timestamp.
    """
    state = load_state()
    state["watermark"] = iso(datetime.now(timezone.utc) - timedelta(hours=hours))
    state["recent_ids"] = []
    save_state(state)
    log("replay armed: watermark rewound to %s" % state["watermark"])
    print("watermark rewound to %s; the next poll re-emits that window" % state["watermark"])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--replay":
        replay(int(sys.argv[2]) if len(sys.argv) > 2 else 24)
        return 0

    instance = urllib.parse.urlsplit(INSTANCE).netloc
    try:
        token = read_token()
    except OSError as exc:
        log("token unreadable: %s" % exc)
        emit([error_record("token", exc)])
        return 1
    if not token:
        log("token file is empty")
        emit([error_record("token", "token file is empty")])
        return 1

    state = load_state()
    out, failed = [], False

    try:
        records, watermark, fresh_ids = poll_events(token, state, instance)
        out.extend(records)
        # Committed together: advancing the watermark without keeping the ids that came
        # from that window would reopen the duplicate the ring exists to close.
        state["watermark"] = watermark
        state["recent_ids"] = (state.get("recent_ids", []) + fresh_ids)[-RECENT_IDS_KEPT:]
        log("events: %d new, watermark %s" % (len(records), watermark))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        detail = exc
        if isinstance(exc, urllib.error.HTTPError):
            detail = "HTTP %s %s" % (exc.code, exc.reason)
        log("event poll failed: %s (watermark held)" % detail)
        out.append(error_record("events", detail))
        failed = True

    emit(out)
    save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
