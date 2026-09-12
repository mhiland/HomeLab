#!/usr/bin/python3
"""Generates dependably-dashboard.ndjson for import into the Wazuh dashboard.

Kept as a generator rather than a hand-maintained 40 KB of JSON: the saved-object
format is mostly boilerplate, and a panel is easier to review as four lines of Python
than as an escaped visState string. Import via Dashboards Management > Saved objects.

Field paths come from what the manager actually produced under logtest: the JSON
decoder nests the poller's record under data.dependably.*, and the alert's own time
field is `timestamp` (ingest time, not event time -- see the note on the nav panel).
"""
import json

IDX = "wazuh-alerts-*"
TIME = "timestamp"
objs = []


def ref():
    return [{"name": "kibanaSavedObjectMeta.searchSourceJSON.index",
             "type": "index-pattern", "id": IDX}]


def vis(vid, title, vis_state, query, description=""):
    objs.append({
        "id": vid, "type": "visualization",
        "attributes": {
            "title": title,
            "description": description,
            "visState": json.dumps(vis_state, separators=(",", ":")),
            "uiStateJSON": "{}",
            "version": 1,
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({
                "query": {"query": query, "language": "kuery"},
                "filter": [],
                "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index",
            }, separators=(",", ":"))},
        },
        "references": ref(),
        "migrationVersion": {"visualization": "7.10.0"},
    })


def metric(vid, title, query, agg=None, color_mode="None"):
    vis(vid, title, {
        "title": title, "type": "metric",
        "params": {"addTooltip": True, "addLegend": False, "type": "metric",
                   "metric": {"percentageMode": False, "useRanges": False,
                              "colorSchema": "Green to Red", "metricColorMode": color_mode,
                              "colorsRange": [{"from": 0, "to": 1000000}],
                              "labels": {"show": True}, "invertColors": False,
                              "style": {"bgFill": "#000", "bgColor": False,
                                        "labelColor": False, "subText": "", "fontSize": 30}}},
        "aggs": [agg or {"id": "1", "enabled": True, "type": "count",
                         "schema": "metric", "params": {}}],
    }, query)


def max_agg(field):
    return {"id": "1", "enabled": True, "type": "max", "schema": "metric",
            "params": {"field": field}}


AXES = {
    "grid": {"categoryLines": False},
    "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom",
                      "show": True, "style": {}, "scale": {"type": "linear"},
                      "labels": {"show": True, "filter": True, "truncate": 100}, "title": {}}],
    "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left",
                   "show": True, "style": {}, "scale": {"type": "linear", "mode": "normal"},
                   "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                   "title": {"text": ""}}],
    "addTooltip": True, "addLegend": True, "legendPosition": "right",
    "times": [], "addTimeMarker": False, "labels": {},
    "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"},
}


def series(kind, label, agg_id="1", interpolate="linear"):
    return {"show": True, "type": kind, "mode": "stacked" if kind == "histogram" else "normal",
            "data": {"label": label, "id": agg_id}, "valueAxis": "ValueAxis-1",
            "drawLinesBetweenPoints": True, "lineWidth": 2, "interpolate": interpolate,
            "showCircles": True}


def date_hist(agg_id="2"):
    return {"id": agg_id, "enabled": True, "type": "date_histogram", "schema": "segment",
            "params": {"field": TIME, "timeRange": {}, "useNormalizedOpenSearchInterval": True,
                       "scaleMetricValues": False, "interval": "auto", "drop_partials": False,
                       "min_doc_count": 1, "extended_bounds": {}}}


def terms(agg_id, field, schema, size=10, order_by="1"):
    return {"id": agg_id, "enabled": True, "type": "terms", "schema": schema,
            "params": {"field": field, "orderBy": order_by, "order": "desc", "size": size,
                       "otherBucket": False, "otherBucketLabel": "Other",
                       "missingBucket": False, "missingBucketLabel": "Missing"}}


def table(vid, title, query, buckets, per_page=15, description=""):
    aggs = [{"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}]
    for i, (field, label, size) in enumerate(buckets, start=2):
        agg = terms(str(i), field, "bucket", size)
        agg["params"]["customLabel"] = label
        aggs.append(agg)
    vis(vid, title, {
        "title": title, "type": "table",
        "params": {"perPage": per_page, "showPartialRows": False, "showMetricsAtAllLevels": False,
                   "sort": {"columnIndex": None, "direction": None}, "showTotal": False,
                   "totalFunc": "sum", "percentageCol": ""},
        "aggs": aggs,
    }, query, description)


# ---------------------------------------------------------------- panels

objs.append({
    "id": "dep-nav", "type": "visualization",
    "attributes": {
        "title": "About this feed",
        "visState": json.dumps({
            "title": "About this feed", "type": "markdown",
            "params": {"fontSize": 11, "openLinksInNewTab": True, "markdown":
                       "**Dependably** artifact registry - `dependably.northwardlabs.ca`. "
                       "Pulled every 60s by `dependably-siem-poller.py` on **studio**, "
                       "rules `100100-100199`. "
                       "[Homelab SOC Overview](/app/dashboards#/view/homelab-soc-overview)\n\n"
                       "Three things this dashboard cannot paper over:\n\n"
                       "- **Failed logins have no attributable source.** Dependably's "
                       "`login.failure` rows carry no actor id, and behind a reverse proxy "
                       "with `TRUSTED_PROXIES` unset every `source_ip` is the Docker bridge "
                       "(`172.17.0.1`). Counts are real; attribution is not.\n"
                       "- **The time axis is ingest time.** Replayed history all lands at the "
                       "moment it was replayed; `data.dependably.event_time` holds the real "
                       "instant and is shown as a column in the tables below.\n"
                       "- **Check the filter bar before trusting a number.** Clicking a bar or a "
                       "table cell pins a filter that narrows *every* panel, which is easy to "
                       "miss. Unrelated tiles showing the same count is the usual tell - e.g. a "
                       "pinned `artifact_hash_changed: true` makes Audit events, Supply-chain "
                       "alerts and Artifact bytes replaced all show the same number, and blanks "
                       "the vulnerability tiles, because a vuln snapshot has no such field."},
            "aggs": []}, separators=(",", ":")),
        "uiStateJSON": "{}", "description": "", "version": 1,
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
            {"query": {"query": "", "language": "kuery"}, "filter": []})},
    },
    "references": [], "migrationVersion": {"visualization": "7.10.0"},
})

DEP = "rule.groups:dependably"

metric("dep-m-events", "Audit events", DEP)
metric("dep-m-config", "Security config changes", "rule.id:100153", color_mode="Labels")
metric("dep-m-authz", "Authorization denials", "rule.groups:dependably_authz", color_mode="Labels")
metric("dep-m-authfail", "Failed logins", "rule.id:100110")
metric("dep-m-health", "Poller errors", "rule.id:100170", color_mode="Labels")

# Auth outcome over time.
vis("dep-auth-time", "Logins: success vs failure", {
    "title": "Logins: success vs failure", "type": "histogram",
    "params": dict(AXES, type="histogram", seriesParams=[series("histogram", "Count")]),
    "aggs": [{"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
             date_hist("2"),
             terms("3", "rule.description", "group", 6)],
}, "rule.id:(100110 or 100112 or 100111 or 100113 or 100114)")

# What kinds of events the registry is producing at all.
vis("dep-actions", "Events by action", {
    "title": "Events by action", "type": "horizontal_bar",
    "params": dict(AXES, type="histogram", seriesParams=[series("histogram", "Count")]),
    "aggs": [{"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
             terms("2", "data.dependably.action", "segment", 15)],
}, DEP)


table("dep-supply-table", "Authorization denials",
      "rule.groups:dependably_authz", [
    # Nested terms aggs intersect: a document missing ANY of these fields produces no row at
    # all. purl was here and authorization denials do not carry one, so the table rendered
    # empty while its own metric tile showed 60. Only fields present on every matching event.
    ("data.dependably.event_time", "Event time (UTC)", 50),
    ("data.dependably.action", "Action", 10),
    ("data.dependably.actor_id", "Actor", 20),
    ("data.dependably.detail_raw", "Detail", 50),
], description="A human disabling a control for a named package, and credentials attempting "
                "operations they are not entitled to. Artifact republishes are deliberately not "
                "collected - they are operational and live in dependably's own audit trail.")

table("dep-config-table", "Configuration and tenant changes",
      "rule.groups:(dependably_config or dependably_privilege or dependably_credentials)", [
          ("data.dependably.event_time", "Event time (UTC)", 50),
          ("data.dependably.action", "Action", 15),
          ("data.dependably.detail_key", "Setting", 20),
          ("data.dependably.detail_prior_value", "From", 20),
          ("data.dependably.detail_new_value", "To", 20),
          ("data.dependably.actor_id", "Actor", 20),
      ])

table("dep-health-table", "Feed health: poller failures", "rule.id:100170", [
    ("data.dependably.stage", "Stage", 10),
    ("data.dependably.message", "Error", 20),
], per_page=5,
    description="Empty is the healthy state. A gap in the feed with no rows here means the "
                "poller is running and the registry is quiet; rows here mean it is not.")

# ---------------------------------------------------------------- dashboard

LAYOUT = [
    ("dep-nav",            0,  0, 48, 6),
    ("dep-m-events",       0,  6, 10, 6),
    ("dep-m-authz",       10,  6, 10, 6),
    ("dep-m-config",      20,  6,  9, 6),
    ("dep-m-authfail",    29,  6,  9, 6),
    ("dep-m-health",      38,  6, 10, 6),
    ("dep-supply-table",   0, 12, 28, 15),
    ("dep-actions",       28, 12, 20, 15),
    ("dep-auth-time",      0, 27, 28, 13),
    ("dep-health-table",  28, 27, 20, 13),
    ("dep-config-table",   0, 40, 48, 14),
]

panels, refs = [], []
for i, (vid, x, y, w, h) in enumerate(LAYOUT, start=1):
    panels.append({"version": "2.19.1", "gridData": {"x": x, "y": y, "w": w, "h": h, "i": str(i)},
                   "panelIndex": str(i), "embeddableConfig": {}, "panelRefName": "panel_%d" % i})
    refs.append({"name": "panel_%d" % i, "type": "visualization", "id": vid})

objs.append({
    "id": "dependably-registry", "type": "dashboard",
    "attributes": {
        "title": "Dependably Registry",
        "description": "Audit, supply-chain and vulnerability telemetry pulled from the "
                       "dependably artifact registry.",
        "panelsJSON": json.dumps(panels, separators=(",", ":")),
        "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
        "version": 1, "timeRestore": True, "timeTo": "now", "timeFrom": "now-7d",
        "refreshInterval": {"pause": False, "value": 60000},
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
            {"query": {"query": "", "language": "kuery"}, "filter": []})},
    },
    "references": refs,
    "migrationVersion": {"dashboard": "7.9.3"},
})

with open("dependably-dashboard.ndjson", "w") as fh:
    for o in objs:
        fh.write(json.dumps(o, separators=(",", ":")) + "\n")

print("wrote %d saved objects (%d visualizations + 1 dashboard)" % (len(objs), len(objs) - 1))
