"""Tests for dependably-siem-poller.py.

The module filename has hyphens, so it cannot be `import`ed normally; it is loaded via
importlib.util.spec_from_file_location() in the `poller` fixture below.

No network access: every test that reaches poll_events() monkeypatches the module's
`get_json` with a fake. Filesystem state (STATE_FILE, OUT_FILE, TOKEN_FILE, SELF_LOG) is
always redirected into a pytest tmp_path via the `sandbox` fixture -- no test touches the
real ~/Library paths.

Run with: /tmp/wazuh-test-venv/bin/pytest test_poller.py -v
(see README.md "Running the tests" for how that venv is built)
"""
import importlib.util
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "dependably-siem-poller.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("dependably_siem_poller", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def poller():
    """A fresh import of the module per test, so monkeypatched globals never leak."""
    mod = _load_module()
    yield mod
    sys.modules.pop("dependably_siem_poller", None)


@pytest.fixture
def sandbox(poller, tmp_path, monkeypatch):
    """Redirects every path the module touches into tmp_path and stubs a valid token."""
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    token_file = tmp_path / "token"
    self_log = tmp_path / "poller.log"

    monkeypatch.setattr(poller, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(poller, "STATE_FILE", str(state_dir / "state.json"))
    monkeypatch.setattr(poller, "OUT_DIR", str(out_dir))
    monkeypatch.setattr(poller, "OUT_FILE", str(out_dir / "audit.log"))
    monkeypatch.setattr(poller, "TOKEN_FILE", str(token_file))
    monkeypatch.setattr(poller, "SELF_LOG", str(self_log))

    token_file.write_text("test-token-123")

    return {
        "state_file": state_dir / "state.json",
        "out_file": out_dir / "audit.log",
        "token_file": token_file,
    }


def make_item(id="evt-1", action="login.success", created_at=None, detail=None, **extra):
    if created_at is None:
        created_at = poller_iso_now()
    item = {
        "id": id,
        "action": action,
        "createdAt": created_at,
        "scope": "org",
        "orgId": "org-1",
        "orgSlug": "acme",
        "actorId": "user-1",
        "actorEmail": None,
        "ecosystem": "npm",
        "purl": None,
        "sourceIp": "10.0.0.1",
    }
    if detail is not None:
        item["detail"] = detail
    item.update(extra)
    return item


def poller_iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fake_get_json_pages(pages):
    """Returns a fake get_json(path, params, token) that yields `pages` in sequence.

    Each page is a dict shaped like the server response: {"items": [...], "next_cursor": ...}.
    Records every params dict it was called with on ._calls for assertions.
    """
    pages = list(pages)
    calls = []

    def _fake(path, params, token):
        calls.append(params)
        if not pages:
            return {"items": [], "next_cursor": None}
        return pages.pop(0)

    _fake.calls = calls
    return _fake


# ---------------------------------------------------------------------------
# iso()
# ---------------------------------------------------------------------------

def test_iso_formats_millis_and_z(poller):
    dt = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc)
    assert poller.iso(dt) == "2026-01-02T03:04:05.678Z"


def test_iso_converts_non_utc_to_utc(poller):
    from datetime import timezone as tz
    est = tz(timedelta(hours=-5))
    dt = datetime(2026, 1, 2, 0, 0, 0, 0, tzinfo=est)
    assert poller.iso(dt) == "2026-01-02T05:00:00.000Z"


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

def test_load_state_missing_file_returns_empty_dict(sandbox, poller):
    assert poller.load_state() == {}


def test_load_state_corrupt_json_returns_empty_dict(sandbox, poller):
    sandbox["state_file"].parent.mkdir(parents=True, exist_ok=True)
    sandbox["state_file"].write_text("{not json")
    assert poller.load_state() == {}


def test_save_state_load_state_roundtrip(sandbox, poller):
    state = {"watermark": "2026-01-01T00:00:00.000Z", "recent_ids": ["a", "b"]}
    poller.save_state(state)
    assert poller.load_state() == state


# ---------------------------------------------------------------------------
# error_record()
# ---------------------------------------------------------------------------

def test_error_record_shape(poller):
    rec = poller.error_record("events", "boom")
    assert rec["dependably"]["record_type"] == "poller_error"
    assert rec["dependably"]["stage"] == "events"
    assert rec["dependably"]["message"] == "boom"
    assert "timestamp" in rec
    # matches iso()'s own format
    assert rec["timestamp"].endswith("Z")


def test_error_record_truncates_long_message(poller):
    rec = poller.error_record("events", "x" * 1000)
    assert len(rec["dependably"]["message"]) == 500


# ---------------------------------------------------------------------------
# shape_event(): live vs backfilled  (property 3)
# ---------------------------------------------------------------------------

def test_shape_event_marks_recent_event_live(poller):
    created = poller.iso(datetime.now(timezone.utc) - timedelta(seconds=10))
    item = make_item(created_at=created)
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["live"] == "true"


def test_shape_event_marks_old_event_not_live(poller):
    created = poller.iso(datetime.now(timezone.utc) - timedelta(hours=2))
    item = make_item(created_at=created)
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["live"] == "false"


def test_shape_event_missing_created_at_defaults_to_not_live(poller):
    item = make_item(created_at=None)
    item["createdAt"] = None
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["live"] == "false"


# ---------------------------------------------------------------------------
# shape_event(): DETAIL_KEYS closed allowlist  (property 6)
# ---------------------------------------------------------------------------

def test_shape_event_lifts_only_allowlisted_detail_keys(poller):
    detail = json.dumps({"method": "PUT", "reason": "expired", "totally_free_form": "danger"})
    item = make_item(detail=detail)
    rec = poller.shape_event(item, "example.test")
    dep = rec["dependably"]
    assert dep["detail_method"] == "PUT"
    assert dep["detail_reason"] == "expired"
    assert "detail_totally_free_form" not in dep
    # but the free-form payload still survives verbatim
    assert "totally_free_form" in dep["detail_raw"]


def test_shape_event_detail_as_dict_not_string(poller):
    item = make_item(detail={"role": "admin"})
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["detail_role"] == "admin"


def test_shape_event_unparseable_detail_does_not_crash(poller):
    item = make_item(detail="{not json")
    rec = poller.shape_event(item, "example.test")
    # raw is preserved even though it could not be parsed into fields
    assert rec["dependably"]["detail_raw"] == "{not json"


# ---------------------------------------------------------------------------
# shape_event(): artifact_hash_changed  (property 5)
# ---------------------------------------------------------------------------

def test_shape_event_artifact_hash_changed_true_when_hashes_differ(poller):
    detail = json.dumps({"prior_artifact_hash": "aaa", "artifact_hash": "bbb"})
    item = make_item(action="package.replace", detail=detail)
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["artifact_hash_changed"] == "true"


def test_shape_event_artifact_hash_changed_false_when_hashes_match(poller):
    detail = json.dumps({"prior_artifact_hash": "aaa", "artifact_hash": "aaa"})
    item = make_item(action="package.replace", detail=detail)
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["artifact_hash_changed"] == "false"


def test_shape_event_artifact_hash_changed_absent_when_hashes_missing(poller):
    item = make_item(action="package.replace", detail=json.dumps({}))
    rec = poller.shape_event(item, "example.test")
    assert "artifact_hash_changed" not in rec["dependably"]


def test_shape_event_artifact_hash_changed_absent_for_other_actions(poller):
    detail = json.dumps({"prior_artifact_hash": "aaa", "artifact_hash": "bbb"})
    item = make_item(action="login.success", detail=detail)
    rec = poller.shape_event(item, "example.test")
    assert "artifact_hash_changed" not in rec["dependably"]


def test_shape_event_drops_none_valued_fields(poller):
    item = make_item(actorEmail=None, purl=None)
    rec = poller.shape_event(item, "example.test")
    assert "actor_email" not in rec["dependably"]
    assert "purl" not in rec["dependably"]


def test_shape_event_action_category_is_first_segment(poller):
    item = make_item(action="tenant.setting.change")
    rec = poller.shape_event(item, "example.test")
    assert rec["dependably"]["action_category"] == "tenant"


# ---------------------------------------------------------------------------
# poll_events(): EXCLUDED_ACTIONS  (property 4)
# ---------------------------------------------------------------------------

def test_poll_events_drops_excluded_actions(poller):
    page = {
        "items": [
            make_item(id="e1", action="package.replace"),
            make_item(id="e2", action="package.override.set"),
            make_item(id="e3", action="project.create"),
            make_item(id="e4", action="project.created"),
            make_item(id="e5", action="login.success"),
        ],
        "next_cursor": None,
    }
    fake = fake_get_json_pages([page])
    poller.get_json = fake
    records, watermark, fresh_ids = poller.poll_events("tok", {}, "example.test")
    ids_emitted = [r["dependably"]["event_id"] for r in records]
    assert ids_emitted == ["e5"]
    assert fresh_ids == ["e5"]


# ---------------------------------------------------------------------------
# poll_events(): de-duplication  (property 2)
# ---------------------------------------------------------------------------

def test_poll_events_dedupes_id_seen_within_the_same_run(poller):
    # The server's window is closed on both ends: the boundary event can be returned
    # twice across the two pages of a single run's cursor walk.
    boundary = make_item(id="boundary-1", action="login.success")
    page1 = {"items": [boundary], "next_cursor": "cursor-2"}
    page2 = {"items": [boundary], "next_cursor": None}
    fake = fake_get_json_pages([page1, page2])
    poller.get_json = fake
    records, watermark, fresh_ids = poller.poll_events("tok", {}, "example.test")
    assert len(records) == 1
    assert fresh_ids == ["boundary-1"]


def test_poll_events_dedupes_id_seen_in_a_prior_run(poller):
    boundary = make_item(id="boundary-1", action="login.success")
    page = {"items": [boundary], "next_cursor": None}
    fake = fake_get_json_pages([page])
    poller.get_json = fake
    state = {"watermark": poller.iso(datetime.now(timezone.utc)), "recent_ids": ["boundary-1"]}
    records, watermark, fresh_ids = poller.poll_events("tok", state, "example.test")
    assert records == []
    assert fresh_ids == []


# ---------------------------------------------------------------------------
# poll_events(): watermark advancement
# ---------------------------------------------------------------------------

def test_poll_events_advances_watermark_on_full_drain(poller):
    page = {"items": [make_item(id="e1")], "next_cursor": None}
    fake = fake_get_json_pages([page])
    poller.get_json = fake
    records, watermark, fresh_ids = poller.poll_events("tok", {}, "example.test")
    # watermark moved to "until" (now), not left at the backfill start
    watermark_dt = datetime.strptime(watermark, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    assert abs((watermark_dt - datetime.now(timezone.utc)).total_seconds()) < 5


def test_poll_events_holds_watermark_when_page_cap_hit_with_cursor_outstanding(poller, monkeypatch):
    monkeypatch.setattr(poller, "MAX_PAGES", 2)
    old_watermark = "2020-01-01T00:00:00.000Z"
    pages = [
        {"items": [make_item(id="e1")], "next_cursor": "c1"},
        {"items": [make_item(id="e2")], "next_cursor": "c2"},  # cursor still live at cap
    ]
    fake = fake_get_json_pages(pages)
    poller.get_json = fake
    records, watermark, fresh_ids = poller.poll_events(
        "tok", {"watermark": old_watermark}, "example.test"
    )
    assert watermark == old_watermark
    assert len(records) == 2  # already-fetched pages are still emitted


def test_poll_events_propagates_transport_errors(poller):
    def _raise(path, params, token):
        raise urllib.error.URLError("no route to host")

    poller.get_json = _raise
    with pytest.raises(urllib.error.URLError):
        poller.poll_events("tok", {}, "example.test")


def test_poll_events_backfills_from_scratch_when_no_watermark(poller, monkeypatch):
    monkeypatch.setattr(poller, "BACKFILL_HOURS", 24)
    fake = fake_get_json_pages([{"items": [], "next_cursor": None}])
    poller.get_json = fake
    poller.poll_events("tok", {}, "example.test")
    since = fake.calls[0]["since"]
    since_dt = datetime.strptime(since, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    expected = datetime.now(timezone.utc) - timedelta(hours=24)
    assert abs((since_dt - expected).total_seconds()) < 5


# ---------------------------------------------------------------------------
# main(): watermark held on failure end-to-end  (property 1)
# ---------------------------------------------------------------------------

def test_main_holds_watermark_when_poll_fails(sandbox, poller):
    old_watermark = "2020-06-01T00:00:00.000Z"
    poller.save_state({"watermark": old_watermark, "recent_ids": []})

    def _raise(path, params, token):
        raise urllib.error.HTTPError("url", 401, "unauthorized", {}, None)

    poller.get_json = _raise

    rc = poller.main()

    assert rc == 1
    state_after = poller.load_state()
    assert state_after["watermark"] == old_watermark
    assert "activity_watermark" not in state_after

    # A credential failure fails BOTH feeds, and each reports its own -- a single record would
    # leave an operator reading "the audit poll is broken" while the refusal feed was equally
    # dark. The stages are what distinguish a token problem (both) from one plane being down.
    lines = sandbox["out_file"].read_text().strip().splitlines()
    assert len(lines) == 2
    stages = sorted(json.loads(l)["dependably"]["stage"] for l in lines)
    assert stages == ["activity", "events"]
    assert all(json.loads(l)["dependably"]["record_type"] == "poller_error" for l in lines)


def test_main_advances_watermark_and_emits_events_on_success(sandbox, poller):
    poller.save_state({"watermark": "2020-06-01T00:00:00.000Z", "recent_ids": []})
    item = make_item(id="e1", action="login.success")
    fake = fake_get_json_pages([{"items": [item], "next_cursor": None}])
    poller.get_json = fake

    rc = poller.main()

    assert rc == 0
    state_after = poller.load_state()
    assert state_after["watermark"] != "2020-06-01T00:00:00.000Z"
    assert state_after["recent_ids"] == ["e1"]

    lines = sandbox["out_file"].read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["dependably"]["record_type"] == "audit"
    assert rec["dependably"]["event_id"] == "e1"


# ---------------------------------------------------------------------------
# main(): error records  (property 7)
# ---------------------------------------------------------------------------

def test_main_reports_missing_token_as_poller_error(sandbox, poller):
    sandbox["token_file"].unlink()
    rc = poller.main()
    assert rc == 1
    lines = sandbox["out_file"].read_text().strip().splitlines()
    rec = json.loads(lines[0])
    assert rec["dependably"]["record_type"] == "poller_error"
    assert rec["dependably"]["stage"] == "token"


def test_main_reports_empty_token_as_poller_error(sandbox, poller):
    sandbox["token_file"].write_text("")
    rc = poller.main()
    assert rc == 1
    lines = sandbox["out_file"].read_text().strip().splitlines()
    rec = json.loads(lines[0])
    assert rec["dependably"]["record_type"] == "poller_error"
    assert rec["dependably"]["stage"] == "token"
    assert "empty" in rec["dependably"]["message"]


# ---------------------------------------------------------------------------
# replay()
# ---------------------------------------------------------------------------

def test_replay_rewinds_watermark_and_clears_ring(sandbox, poller, capsys):
    poller.save_state({"watermark": "2026-01-01T00:00:00.000Z", "recent_ids": ["a", "b"]})
    poller.replay(48)
    state = poller.load_state()
    rewound = datetime.strptime(state["watermark"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    expected = datetime.now(timezone.utc) - timedelta(hours=48)
    assert abs((rewound - expected).total_seconds()) < 5
    assert state["recent_ids"] == []


# ---------------------------------------------------------------------------
# poll_activity() and shape_activity_event()
# ---------------------------------------------------------------------------

def make_activity(id="act-1", action="blocked_license", created_at=None, detail=None, **extra):
    """One activity-plane event. Deliberately missing `scope` and `orgSlug`: the server
    says those are audit-plane columns with no counterpart here, so a shaper that invented
    them would be shaping a response shape that does not exist."""
    if created_at is None:
        created_at = poller_iso_now()
    item = {
        "id": id,
        "action": action,
        "createdAt": created_at,
        "orgId": "org-1",
        "actorId": "user-1",
        "ecosystem": "npm",
        "purl": "pkg:npm/left-pad@1.3.0",
        "sourceIp": "10.0.0.9",
    }
    if detail is not None:
        item["detail"] = detail
    item.update(extra)
    return item


def test_shape_activity_event_categorizes_every_blocked_arm_as_one_family(poller):
    # The point of action_category: a rule matching "any block-gate refusal" must not have to
    # enumerate the arms. Splitting on "." -- what the audit plane does -- would give each
    # underscore-named arm its own category and break exactly that rule.
    for arm in ("blocked_license", "blocked_vulnerability", "blocked_provenance"):
        rec = poller.shape_activity_event(make_activity(action=arm), "inst")
        assert rec["dependably"]["action_category"] == "blocked", arm
        assert rec["dependably"]["action"] == arm
    assert rec["dependably"]["record_type"] == "activity"


def test_shape_activity_event_omits_columns_this_plane_does_not_have(poller):
    rec = poller.shape_activity_event(make_activity(), "inst")
    dep = rec["dependably"]
    assert "scope" not in dep
    assert "org_slug" not in dep
    assert dep["org_id"] == "org-1"
    assert dep["source_ip"] == "10.0.0.9"


def test_poll_activity_takes_the_watermark_from_the_server_not_the_clock(poller, monkeypatch):
    # The activity plane is written late, so the server subtracts its own lag and reports the
    # window it actually served. Using our own `now` would claim rows the writer had not
    # reached yet, and they would never be read again.
    served = "2026-01-01T00:00:00.000Z"
    fake = fake_get_json_pages([
        {"items": [make_activity()], "next_cursor": None, "until": served, "lag_seconds": 30},
    ])
    monkeypatch.setattr(poller, "get_json", fake)
    records, watermark, ids = poller.poll_activity("tok", {}, "inst")
    assert len(records) == 1
    assert watermark == served
    assert ids == ["act-1"]


def test_poll_activity_holds_the_watermark_when_the_server_withholds_until(poller, monkeypatch):
    # A truncated page serves the NEWEST slice and leaves older rows behind the cursor, so the
    # server withholds `until` there. Advancing anyway would skip every older row permanently.
    # This is the failure the whole server-gives-the-watermark contract exists to prevent.
    fake = fake_get_json_pages([
        {"items": [make_activity(id="act-1")], "next_cursor": None, "until": None},
    ])
    monkeypatch.setattr(poller, "get_json", fake)
    records, watermark, _ = poller.poll_activity("tok", {"activity_watermark": "held"}, "inst")
    assert len(records) == 1, "the rows are still emitted"
    assert watermark == "held", "but the window is not claimed as drained"


def test_poll_activity_holds_the_watermark_when_the_page_cap_is_hit(poller, monkeypatch):
    pages = [{"items": [make_activity(id="a%d" % i)], "next_cursor": "c%d" % i,
              "until": "2026-01-01T00:00:00.000Z"}
             for i in range(poller.MAX_PAGES + 2)]
    monkeypatch.setattr(poller, "get_json", fake_get_json_pages(pages))
    _, watermark, _ = poller.poll_activity("tok", {"activity_watermark": "held"}, "inst")
    assert watermark == "held"


def test_poll_activity_sends_no_until_and_no_event_filter(poller, monkeypatch):
    # Not sending `until` is what lets the server apply its lag. Not sending `event` takes the
    # server default, which is the whole blocked* family and no downloads.
    fake = fake_get_json_pages([{"items": [], "next_cursor": None, "until": "x"}])
    monkeypatch.setattr(poller, "get_json", fake)
    poller.poll_activity("tok", {"activity_watermark": "2026-01-01T00:00:00.000Z"}, "inst")
    params = fake.calls[0]
    assert "until" not in params
    assert "event" not in params
    assert params["since"] == "2026-01-01T00:00:00.000Z"


def test_poll_activity_dedupes_on_its_own_ring(poller, monkeypatch):
    fake = fake_get_json_pages([
        {"items": [make_activity(id="seen"), make_activity(id="fresh")],
         "next_cursor": None, "until": "2026-01-01T00:00:00.000Z"},
    ])
    monkeypatch.setattr(poller, "get_json", fake)
    # "seen" is in the ACTIVITY ring; the audit ring must not be consulted for this plane.
    state = {"activity_recent_ids": ["seen"], "recent_ids": ["fresh"]}
    records, _, ids = poller.poll_activity("tok", state, "inst")
    assert ids == ["fresh"]
    assert [r["dependably"]["event_id"] for r in records] == ["fresh"]


def test_main_keeps_the_two_planes_watermarks_independent(sandbox, poller, monkeypatch):
    # A broken activity feed must not stop the audit feed advancing. Sharing one handler would
    # mean the collector fell further behind on BOTH planes every run while reporting one error.
    def fake(path, params, token):
        if "activity" in path:
            raise urllib.error.HTTPError(path, 500, "Server Error", {}, None)
        return {"items": [make_item(id="evt-1")], "next_cursor": None}

    monkeypatch.setattr(poller, "get_json", fake)
    rc = poller.main()
    assert rc == 1, "a failed plane is still a failed run"

    state = poller.load_state()
    assert state.get("watermark"), "the audit feed advanced"
    assert not state.get("activity_watermark"), "the activity feed did not"

    kinds = [json.loads(l)["dependably"]["record_type"]
             for l in sandbox["out_file"].read_text().strip().splitlines()]
    assert "audit" in kinds, "the audit rows were still emitted"
    assert "poller_error" in kinds, "and the activity failure was reported as an event"


def test_replay_rewinds_both_planes(sandbox, poller):
    # A replay that rewound only the audit plane would re-emit half the data and leave the
    # operator believing they had replayed the window.
    poller.save_state({
        "watermark": "2026-01-01T00:00:00.000Z", "recent_ids": ["a"],
        "activity_watermark": "2026-01-01T00:00:00.000Z", "activity_recent_ids": ["b"],
    })
    poller.replay(6)
    state = poller.load_state()
    assert state["watermark"] == state["activity_watermark"]
    assert state["recent_ids"] == []
    assert state["activity_recent_ids"] == []


def test_main_reports_an_absent_activity_feed_once_not_every_minute(sandbox, poller, monkeypatch):
    # A 404 is an instance older than the feed, not an incident. Emitting it every run would
    # post an identical record every minute and teach the operator to scroll past poller_error.
    def fake(path, params, token):
        if "activity" in path:
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(poller, "get_json", fake)

    assert poller.main() == 0, "an instance that predates the feed is not a failed run"
    first = sandbox["out_file"].read_text().strip().splitlines()
    assert len(first) == 1
    rec = json.loads(first[0])["dependably"]
    assert rec["stage"] == "activity"
    assert "404" in rec["message"]
    assert poller.load_state()["activity_absent"] is True

    assert poller.main() == 0
    assert len(sandbox["out_file"].read_text().strip().splitlines()) == 1, "still one record"


def test_main_reports_the_activity_feed_coming_back(sandbox, poller, monkeypatch):
    # The other half: an operator who was told the feed is missing has to be told when it is
    # not, or the first 404 record stands as the last word forever.
    poller.save_state({"activity_absent": True})
    served = "2026-01-01T00:00:00.000Z"

    def fake(path, params, token):
        if "activity" in path:
            return {"items": [], "next_cursor": None, "until": served}
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(poller, "get_json", fake)
    assert poller.main() == 0

    messages = [json.loads(l)["dependably"].get("message", "")
                for l in sandbox["out_file"].read_text().strip().splitlines()]
    assert any("recovered" in m for m in messages)
    assert "activity_absent" not in poller.load_state()
    assert poller.load_state()["activity_watermark"] == served


def test_main_still_fails_loudly_on_a_broken_activity_feed(sandbox, poller, monkeypatch):
    # Only 404 is special-cased. A 500 is an incident and must keep failing the run, or the
    # quieting added for old instances would swallow a real outage.
    def fake(path, params, token):
        if "activity" in path:
            raise urllib.error.HTTPError(path, 500, "Server Error", {}, None)
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(poller, "get_json", fake)
    assert poller.main() == 1
    assert "activity_absent" not in poller.load_state()
