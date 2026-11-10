# Airport Operations Real-Time Dashboard

A 4-page Fabric Real-Time Dashboard (24 tiles, 30s auto-refresh) on top of the simulator's Eventhouse tables.
Parameters: **Time range** (default 30 min), **Airline**, **Origin**.

| Page | Tiles |
|---|---|
| Overview | KPI cards (passengers, bags checked in / loaded / delivered, exception bags, mishandled %), bag events per minute by stage, bag pipeline, passengers vs bags, exceptions over time |
| Flights | Live flight board (loaded %, delivered, exceptions, status), top 10 flights by exceptions, avg bag weight by airline, bags by destination |
| Exceptions | Rejected / withheld / lost / not collected cards, exceptions with anomaly detection, by airline, by destination |

| Network Map | Bubble map of bag volume by airport, exception hotspot map (attributed to origin airport), airport scorecard table. Uses `dash_airports()` (IATA -> lat/lon), which covers all 52 airports in the simulator's built-in routes; custom `--airports-file` codes must be added to it. |

## Setup
1. Ensure the tables from `kql\airport_events.kql` and `kql\event_tables.kql` exist (the `flights` / CDC tables are **not** used).
2. Run `kql\dashboard_functions.kql` in the KQL database (adds `Airport.Baggage.Lost_v1` and the `dash_*` functions).
3. Run the simulator with `--ce-mode structured` (the ingestion mapping expects structured CloudEvents).
4. Generate the definition with your data source and import it:
   ```
   python dashboard\build_dashboard.py --cluster-uri <query URI> --database <db> --workspace-id <workspace guid>
   ```
   In Fabric: create a **new** Real-Time Dashboard named "Airport Operations v2" (this leaves your existing
   "Airport Operations Dashboard" untouched), then **Manage > Replace with file** on that new, empty dashboard and pick
   `dashboard\airport-operations-dashboard.json`. Only ever use Replace with file on the v2 dashboard. The generated file validates against the official schema
   (`https://dataexplorer.azure.com/static/d/schema/60/dashboard.json`). If the data source binding is not accepted, open
   **Manage > Data sources** and point `Airport-Eventhouse` at your database. If the import rejects the file,
   export your existing dashboard once and compare the structure with the generated JSON; tile queries can
   also be pasted individually from `build_dashboard.py`.

## Troubleshooting: every tile shows an error
- Most common cause: the data source is not bound. Open **Manage > Data sources**, edit `Airport-Eventhouse`, and select
  your Eventhouse and KQL database from the picker (or regenerate with real `--cluster-uri` / `--database` / `--workspace-id`;
  `--database` must be the KQL database item GUID, not its name).
- Click the error icon on a tile for the message. "Failed to resolve ... dash_..." means `kql\dashboard_functions.kql`
  was not run in the same database the data source points at.
- Test the same query in the KQL database queryset with `_startTime`/`_endTime` replaced, e.g.
  `dash_bag_state(ago(30m), now()) | summarize count() by state`.

## Semantics
- **Time**: all tiles filter on **ingestion time** (wall clock), because `___time` is simulated time that runs
  at `--clock-speed` and can be ahead of `now()`.
- **Bag state** (`dash_bag_state(from, to)`): one mutually exclusive state per bag, for bags with at least one event ingested in the range, precedence
  NotCollected > CustomsWithheld > Delivered > Lost > Rejected > Unloaded > Loaded > Screened > CheckedIn.
- **Exception bags** = Rejected, Lost, CustomsWithheld, NotCollected. **Mishandled %** = exception bags / all bags
  first seen in the selected time range.
- **Performance**: the functions take the dashboard time range and filter each table by ingestion time before joining.
- Airline/origin/destination/weight only exist on check-in events; `dash_bag_events()` enriches every event with them.
- Flight status is derived from bag lifecycle counts.
- The anomaly tile needs at least 5 exceptions in the range. The default exception rates are very low (loss 0.2%, reject 0.3%, not-collected 0.5%), so for demos run e.g.:
  `bhsim --clock-speed 120 --flight-interval-minutes 5 --loss-rate 0.03 --reject-rate 0.04 --not-collected-rate 0.06`
- Known gap: the simulator emits `Airport.Baggage.Customs.Screened` while the table policy expects
  `Airport.Baggage.CustomsScreened`; customs-cleared is therefore not used by the dashboard.
- `Airport.Stats.*` tables (Stream Analytics) are not used.

Not validated against a live Eventhouse in this environment.
