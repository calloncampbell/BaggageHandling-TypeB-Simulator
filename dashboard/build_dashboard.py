"""Generate the Airport Operations Real-Time Dashboard definition (Fabric / ADX dashboard schema v60).

Usage:
    python dashboard\\build_dashboard.py [--cluster-uri URI] [--database NAME] [--workspace-id GUID]
        [--out dashboard\\airport-operations-dashboard.json]

Queries live in this file so each tile is reviewable; they rely on the functions in
kql\\dashboard_functions.kql. IDs are deterministic so regenerating yields stable diffs.
"""
import argparse
import json
import uuid
from pathlib import Path

NS = uuid.UUID("6f1d2c52-0b3a-4a3e-9a55-0c7a1b1d0001")


def gid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


DS_ID = gid("datasource")

# Dashboard parameters: _startTime/_endTime (time range), _airline, _origin.
EV_FILTER = (
    "| where ingest between (_startTime .. _endTime)\n"
    "| where (isempty(_airline) or airline in (_airline)) and (isempty(_origin) or origin in (_origin))"
)
ST_FILTER = (
    "| where firstIngest between (_startTime .. _endTime)\n"
    "| where (isempty(_airline) or airline in (_airline)) and (isempty(_origin) or origin in (_origin))"
)
EXC_STAGES = "('Rejected', 'Lost', 'CustomsWithheld', 'NotCollected')"


def stage_card(stage: str, col: str) -> str:
    return (
        f"dash_bag_events(_startTime, _endTime)\n{EV_FILTER}\n| where stage == '{stage}'\n"
        f"| summarize ['{col}'] = dcount(bagId)"
    )


Q = {}
T = []  # tiles
PAGES = ["Overview", "Flights", "Exceptions"]


def tile(page, title, query, visual, x, y, w, h, options=None):
    qid = gid("q:" + page + ":" + title)
    Q[qid] = {
        "id": qid,
        "dataSource": {"kind": "inline", "dataSourceId": DS_ID},
        "text": query.strip(),
        "usedVariables": ["_startTime", "_endTime", "_airline", "_origin"],
    }
    T.append(
        {
            "id": gid("t:" + page + ":" + title),
            "title": title,
            "visualType": visual,
            "pageId": gid("page:" + page),
            "layout": {"x": x, "y": y, "width": w, "height": h},
            "queryRef": {"kind": "query", "queryId": qid},
            "visualOptions": options or {},
        }
    )


def series_opts(x, y, series=None):
    return {"xColumn": x, "yColumns": y, "seriesColumns": series}


# ---------------------------------------------------------------- Overview
P = "Overview"
tile(P, "Passengers checked in", f"""['Airport.Passenger.Checkin_v1']
| where ingestion_time() between (_startTime .. _endTime)
| extend ingest = ingestion_time()
{EV_FILTER}
| summarize Passengers = dcount(paxId)""", "card", 0, 0, 4, 3)
tile(P, "Bags checked in", stage_card("Checkin", "Bags"), "card", 4, 0, 4, 3)
tile(P, "Bags loaded", stage_card("Loaded", "Bags"), "card", 8, 0, 4, 3)
tile(P, "Bags delivered to belt", stage_card("Delivered", "Bags"), "card", 12, 0, 4, 3)
tile(P, "Exception bags", f"""dash_bag_state(_startTime, _endTime)
{ST_FILTER}
| summarize Exceptions = countif(isException)""", "card", 16, 0, 4, 3)
tile(P, "Mishandled %", f"""dash_bag_state(_startTime, _endTime)
{ST_FILTER}
| summarize Rate = round(100.0 * countif(isException) / count(), 2)
| project ['Mishandled %'] = Rate""", "card", 20, 0, 4, 3)
tile(P, "Bag events per minute by stage", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| summarize Bags = dcount(bagId) by Time = bin(ingest, 1m), stage
| order by Time asc""", "line", 0, 3, 14, 8,
     series_opts("Time", ["Bags"], ["stage"]))
tile(P, "Bag pipeline (bags reaching each stage)", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage in ('Checkin', 'Screened', 'Loaded', 'Unloaded', 'Delivered')
| summarize Bags = dcount(bagId) by stage
| extend ord = case(stage == 'Checkin', 1, stage == 'Screened', 2, stage == 'Loaded', 3, stage == 'Unloaded', 4, 5)
| order by ord asc
| project stage, Bags""", "bar", 14, 3, 10, 8,
     series_opts("stage", ["Bags"]))
tile(P, "Passengers vs bags checked in", f"""let pax = ['Airport.Passenger.Checkin_v1']
    | where ingestion_time() between (_startTime .. _endTime)
    | extend ingest = ingestion_time()
    {EV_FILTER}
    | summarize Count = dcount(paxId) by Time = bin(ingest, 1m)
    | extend Series = 'Passengers';
let bags = dash_bag_events(_startTime, _endTime)
    {EV_FILTER}
    | where stage == 'Checkin'
    | summarize Count = dcount(bagId) by Time = bin(ingest, 1m)
    | extend Series = 'Bags';
union pax, bags
| order by Time asc""", "area", 0, 11, 14, 8,
     series_opts("Time", ["Count"], ["Series"]))
tile(P, "Exceptions over time", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage in {EXC_STAGES}
| summarize Bags = dcount(bagId) by Time = bin(ingest, 1m), stage
| order by Time asc""", "stackedcolumn", 14, 11, 10, 8,
     series_opts("Time", ["Bags"], ["stage"]))

# ---------------------------------------------------------------- Flights
P = "Flights"
tile(P, "Live flight board", f"""dash_bag_state(_startTime, _endTime)
{ST_FILTER}
| summarize Bags = count(),
    Loaded = countif(set_has_element(stages, 'Loaded')),
    Unloaded = countif(set_has_element(stages, 'Unloaded')),
    Delivered = countif(state == 'Delivered'),
    Exceptions = countif(isException),
    Updated = max(lastIngest)
    by Flight = flightNumber, Airline = airline, Origin = origin, Destination = destination
| extend ['Loaded %'] = round(100.0 * Loaded / Bags, 1)
| extend Status = case(
    Delivered + Exceptions >= Bags, 'Baggage complete',
    Unloaded > 0, 'At baggage claim',
    Loaded > 0, 'Loading / in flight',
    'Check-in')
| project Flight, Airline, Route = strcat(Origin, ' -> ', Destination), Bags, ['Loaded %'], Delivered, Exceptions, Status, Updated
| order by Updated desc
| take 50""", "table", 0, 0, 16, 10)
tile(P, "Top 10 flights by exceptions", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage in {EXC_STAGES}
| summarize Exceptions = dcount(bagId) by Flight = strcat(flightNumber, ' ', origin, '-', destination)
| top 10 by Exceptions desc""", "bar", 16, 0, 8, 10,
     series_opts("Flight", ["Exceptions"]))
tile(P, "Average bag weight by airline (kg)", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage == 'Checkin' and isnotempty(airline)
| summarize ['Avg kg'] = round(avg(weightKg), 1) by airline
| order by ['Avg kg'] desc""", "bar", 0, 10, 12, 8,
     series_opts("airline", ["Avg kg"]))
tile(P, "Bags by destination", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage == 'Checkin'
| summarize Bags = count() by destination
| top 15 by Bags desc""", "bar", 12, 10, 12, 8,
     series_opts("destination", ["Bags"]))

# ---------------------------------------------------------------- Exceptions
P = "Exceptions"
tile(P, "Rejected", stage_card("Rejected", "Rejected"), "card", 0, 0, 6, 3)
tile(P, "Customs withheld", stage_card("CustomsWithheld", "Withheld"), "card", 6, 0, 6, 3)
tile(P, "Lost", stage_card("Lost", "Lost"), "card", 12, 0, 6, 3)
tile(P, "Not collected", stage_card("NotCollected", "Not collected"), "card", 18, 0, 6, 3)
tile(P, "Exceptions with anomaly detection", f"""dash_bag_events(_startTime, _endTime)
{EV_FILTER}
| where stage in {EXC_STAGES}
| make-series Exceptions = dcount(bagId) default = 0 on ingest from bin(_startTime, 1m) to _endTime step 1m
| where array_sum(Exceptions) >= 5
| extend (Anomalies, Score, Baseline) = series_decompose_anomalies(Exceptions, 1.5, -1, 'linear', 0)""",
     "anomalychart", 0, 3, 24, 8,
     {"xColumn": "ingest", "yColumns": ["Exceptions"], "anomalyColumns": ["Anomalies"]})
tile(P, "Exceptions by airline", f"""dash_bag_state(_startTime, _endTime)
{ST_FILTER}
| where isnotempty(airline)
| summarize Exceptions = countif(isException) by airline
| order by Exceptions desc""", "bar", 0, 11, 12, 8,
     series_opts("airline", ["Exceptions"]))
tile(P, "Exceptions by destination", f"""dash_bag_state(_startTime, _endTime)
{ST_FILTER}
| where isException
| summarize Bags = count() by destination, state
| order by Bags desc
| take 40""", "stackedcolumn", 12, 11, 12, 8,
     series_opts("destination", ["Bags"], ["state"]))


def build(args):
    pq = {
        "airline": gid("pq:airline"),
        "origin": gid("pq:origin"),
    }
    for col, qid in pq.items():
        Q[qid] = {
            "id": qid,
            "dataSource": {"kind": "inline", "dataSourceId": DS_ID},
            "text": f"dash_bags_dim(ago(1d)) | where isnotempty({col}) | distinct {col} | order by {col} asc",
            "usedVariables": [],
        }

    def str_param(name, var, col):
        return {
            "kind": "string",
            "id": gid("param:" + col),
            "displayName": name,
            "description": "",
            "variableName": var,
            "selectionType": "array",
            "includeAllOption": True,
            "defaultValue": {"kind": "all"},
            "dataSource": {
                "kind": "query",
                "columns": {"value": col},
                "queryRef": {"kind": "query", "queryId": pq[col]},
            },
            "showOnPages": {"kind": "all"},
        }

    return {
        "$schema": "https://dataexplorer.azure.com/static/d/schema/60/dashboard.json",
        "schema_version": "60",
        "title": "Airport Operations v2",
        "tiles": T,
        "baseQueries": [],
        "parameters": [
            {
                "kind": "duration",
                "id": gid("param:time"),
                "displayName": "Time range",
                "description": "",
                "beginVariableName": "_startTime",
                "endVariableName": "_endTime",
                "defaultValue": {"kind": "dynamic", "count": 30, "unit": "minutes"},
                "showOnPages": {"kind": "all"},
            },
            str_param("Airline", "_airline", "airline"),
            str_param("Origin", "_origin", "origin"),
        ],
        "dataSources": [
            {
                "id": DS_ID,
                "name": "Airport-Eventhouse",
                "scopeId": "kusto-trident",
                "kind": "kusto-trident",
                "clusterUri": args.cluster_uri,
                "database": args.database,
                "workspace": args.workspace_id,
            }
        ],
        "pages": [{"name": p, "id": gid("page:" + p)} for p in PAGES],
        "queries": list(Q.values()),
        "autoRefresh": {"enabled": True, "defaultInterval": "30s", "minInterval": "30s"},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cluster-uri", default="<EVENTHOUSE_QUERY_URI>",
                    help="Eventhouse 'Query URI', e.g. https://trd-xxxx.z0.kusto.fabric.microsoft.com")
    ap.add_argument("--database", default="<KQL_DATABASE_ID_OR_NAME>",
                    help="Item ID (GUID) of the KQL database; copy from the database URL in Fabric")
    ap.add_argument("--workspace-id", default="<FABRIC_WORKSPACE_ID>",
                    help="Workspace GUID (from the workspace URL: /groups/<guid>/)")
    ap.add_argument("--out", default=str(Path(__file__).with_name("airport-operations-dashboard.json")))
    a = ap.parse_args()
    unresolved = [n for n, v in (("--cluster-uri", a.cluster_uri), ("--database", a.database),
                                 ("--workspace-id", a.workspace_id)) if v.startswith("<")]
    if unresolved:
        print("WARNING: placeholders left for " + ", ".join(unresolved)
              + "; every tile will error until the data source is bound (Manage > Data sources).")
    Path(a.out).write_text(json.dumps(build(a), indent=2), encoding="utf-8")
    print(f"Wrote {a.out}: {len(T)} tiles, {len(PAGES)} pages")
