# BlueZoo live API verification — authenticated scan (2026-07-25)

Companion to `working-docs/replan-data-track/bluezoo-mapping-verification.md`,
which verified our mimic against BlueZoo's **published** docs on 2026-07-16 and
left one item explicitly open: *"no authenticated call was made (no AccessKey);
… a live `desc_table`/`run_query` round-trip should re-confirm column lists."*
This document closes that item.

**Account:** org "Walmart Demo", Cluster/Account **Apollo / AP_599**, Super Admin.
**Method:** read-only calls via `scripts/bluezoo_probe.py`; full scan artifact in
`scan/scan.json` + `scan/scan.md` (19 tables, every column, row counts).
**Owner framing:** real data is coming later; the point of this pass is that our
schema and system are adapted to the actual BlueZoo system *before* it arrives.

## Verdict: mimic confirmed structurally; five new facts; one of our own
## corrections was wrong

Nothing found invalidates merged work. The demo path is untouched by any of
this. What changes is what Phase 11b must build against.

## Part 1 — confirmed against live schema

| Claim (source) | Live result |
|---|---|
| `sensor_visits` column list (ws05 port) | **Exact match**: `sensor_id`, `sensor_name`, `sensor_mac`, `sensor_address`, `sensor_latitude`, `sensor_longitude`, `timestamp`, `incoming_inner_count`, `incoming_outer_count`, `outgoing_inner_count`, `outgoing_outer_count`, `valid` (+2 extras, Part 2 #5) |
| Counts are FLOAT64, not integers | Confirmed — all four count columns FLOAT64 |
| `sensor_dwell` has 106 distribution bins | Confirmed exactly |
| Bins are HHMM-encoded, not minutes (ws05 correction #1) | **Confirmed** — `distribution_bin_0058_to_0100` and `distribution_bin_2400_to_beyond` both present. The port correction was right and the donor's minutes encoding was wrong |
| `minimum_/maximum_/average_visitors_*` naming | Confirmed on `sensor_visitors` |
| `sensor_visits` and `sensor_visitors` are separate tables (ws05 correction #5) | Confirmed — distinct tables, distinct column sets |
| `run_query` is SELECT-only | Confirmed (server-side) |
| `cuv` exists on UV tables | Confirmed — present despite being absent from the published example response |

## Part 2 — new facts the published docs did not contain

### 1. The hostname is cluster-scoped. There is no canonical host.

`hermes.apollo.bluezoo.io` and `apollo-api.bluefoxengage.com` both return 200
with byte-identical bodies — aliases for the **Apollo** cluster.
`morpheus-api.bluefoxengage.com` returns `{"status":"BAD_TOKEN"}` with the same
key: a *different cluster*, not a canonical alternative. The dashboard Profile
screen names the cluster ("Apollo / AP_599").

Q18 asked "which hostname is canonical." The question's premise was wrong — the
answer is "whichever one serves the customer's cluster." **The connector must
take the base URL as tenant configuration.**

### 2. The SQL dialect is BigQuery — confirmed, not inferred.

Error text is verbatim BigQuery: `invalidQuery: Unrecognized name: timestamp at
[1:164]`. Our inference from INT64/FLOAT64 type names was correct.

### 3. Every query must carry a time constraint (undocumented).

```
"SQL statement has no 'date_start', 'date_end' nor 'timestamp' constraints.
 At least one constraint on those field needs to be specified in the WHERE clause."
```

BlueZoo's own published example — `select * from sensor_visitors limit 1` —
**would fail against the live API.** This is a hard server-side requirement on
every historical read.

Which column satisfies it varies by table: `sensor_*` carry `timestamp`,
`group_uv_daily` carries `date`, the `group_convert*` family carries
`date_start`. There is no single filter clause that works everywhere.

### 4. This tenant has 19 tables, not the documented 14.

Beyond the documented set: `sensor_visitors_per_minute`, `group_convert`,
`group_convert_daily`, `group_convert_weekly`, `group_convert_monthly`,
`group_sensor_history`, `group_uv_quarterly`.

Table availability is an **account entitlement** — `list_tables` returns "the
tables available under the account." A different BlueZoo customer will return a
different set. **`list_tables` is a per-tenant capability probe, not a
constant.**

Two of these matter directly:

- **`sensor_visitors_per_minute` is enabled here.** Columns are `visitors_inner`
  / `visitors_outer` — occupancy, not visits, exactly as the docs verification
  concluded. **Q17's fallback (b) is available on this tenant without asking
  BlueZoo** — though whether it's enabled for *other* customers is precisely
  the kind of thing the connector must detect rather than assume.
- **`group_sensor_history`** (`group_id`, `group_name`, `sensor_id`,
  `sensor_name`, `timestamp`) **is the group↔sensor mapping table.** Q11 asked
  whether BlueZoo has an existing screen→sensor mapping convention or whether
  we must invent one: they have one, it is API-discoverable, and because it is
  timestamped, **group membership changes over time** — a mapping read is
  as-of-a-date, not a static lookup.

### 5. Undocumented columns that change our design

- **`time_zone` (STRING) on every sensor table**, alongside the documented
  `time_offset`. Directly relevant to the UTC-vs-sensor-local day-cut question
  (Q18) — presence is proven, behavior is not (no rows).
- **`sensor_dwell.distribution_average_duration` and
  `distribution_median_duration`.** `docs/METRICS.md` defers the "dwell
  histogram → scalar" aggregation rule to Phase 11, pending validation against
  a real BlueZoo response. **BlueZoo ships the scalar directly.** The rule is
  "read it, don't derive it" — no bin-midpoint weighting needed.

### 6. We corrected the donor wrongly on UV campaign keying

`group_uv_daily` carries **`campaign_id` AND `campaign_name`** (also
`calculation_unique_visitor_count`, `target_uv`, `actual_accuracy`,
`total_cost`, and more — 24 columns).

The 2026-07-16 docs verification concluded: *"the donor spec's claim that
BlueZoo stamps campaign on `group_uv_*` is contradicted by the docs (UV tables
are `group_id`-keyed, no campaign column); correct that prose when porting."*
That conclusion, recorded in Q6 and Q11, is **wrong against the live schema**.
The donor spec was right; the published docs were incomplete.

Caveat that survives: this is presumably still BlueZoo's own campaign concept,
not our ad campaigns — so the `ad_campaign_id` rename (ws05 correction #2)
stays correct and is in fact *reinforced*: a bare `campaign_id` now collides on
`group_uv_*` too, not only on the flow tables. `group_convert`'s schema
(`campaign_id`, `group_source_id`, `group_destination_id`) confirms the
flow-campaign meaning independently.

### 7. The account has zero rows.

Every table queries cleanly and returns 0 across 2020–2030. "Walmart Demo" is a
fresh tenant with no deployed sensors.

**Verifiable:** table entitlements, every column name and type, query mechanics,
error semantics, auth, host behavior.

**Not verifiable:** dwell bin scale (0–1 shares vs 0–100 percentages),
`valid=false` semantics and whether such rows should be excluded from
impressions, UTC vs sensor-local day cutting, `distribution_weight` meaning,
row caps and rate limits, and realistic magnitudes.

Those stay open until a tenant with real data exists — see "Remaining asks".

## Part 3 — drift in our own code

`app/models/attribution.py:43` `BlueZooVisitInterval` carries
`minimum_/maximum_/average_visitors_inner/outer`. Those columns live on
**`sensor_visitors`**, not `sensor_visits`.

ws05 port correction #5 said explicitly: *"the Phase 11a DTO/seam must not
assume one source table — the live adapter reads two. Keep
`BlueZooVisitInterval` scoped to `sensor_visits` fields only."* The donor's
`store_visits` merge (which fuses BlueZoo's two tables into one) leaked into the
DTO regardless.

The live schema confirms two separate tables, so **a live conformer populating
today's DTO must issue two queries and join them client-side** — on
`(sensor_id, timestamp)`, at 15-minute grain.

Not fixed here, deliberately: the DTO is consumed by merged demo-path code, and
choosing between "split the DTO" and "keep it and join in the adapter" is a
Phase 11b design decision, not a docs pass. Recorded in 11b's doc.

## Part 4 — tenant-genericity requirements for the connector

The owner's binding requirement: *"our agents can work with any of their
customer."* Everything below is a rule the live adapter must follow, each
derived from a finding above rather than from a guess.

1. **Base URL is tenant configuration.** Keyed to the customer's cluster; never
   a hardcoded constant. A key from one cluster returns `BAD_TOKEN` against
   another's host, so a wrong default fails in a way that looks like a bad
   credential.
2. **Call `list_tables` first and treat the result as capabilities.** Do not
   assume any table exists. At minimum, `sensor_visitors_per_minute`, the
   `group_convert*` family, `group_uv_quarterly` and `group_sensor_history`
   must all be optional. Missing table ⇒ that feature degrades, not an error.
3. **Every query carries a time constraint**, using the column that table
   actually has (`timestamp` / `date` / `date_start`). Build this into the
   query builder so it cannot be forgotten.
4. **Discover the group↔sensor mapping from `group_sensor_history`**, as of a
   date — do not invent a mapping table, and do not cache it as static.
5. **Zero rows is a valid answer.** A brand-new tenant returns empty from every
   table; the adapter must return an empty result, never raise or fall back to
   demo data (the fail-closed rule from 11a still applies to *credentials*, not
   to legitimately empty data).
6. **Two-table reads for visit intervals** — `sensor_visits` plus
   `sensor_visitors` if occupancy fields are needed.
7. **Counts are FLOAT64.** Our `video_metrics` schema assumes integer
   impressions; the conversion policy must be explicit, not a silent truncation.
8. **SQL is BigQuery dialect.**
9. **Prefer BlueZoo's own scalars** where they exist (dwell average/median)
   over deriving our own from distributions.

## Remaining asks for BlueZoo / the client

Reduced from the earlier list — most of Q18 is now answered empirically.

1. **A tenant with real historical data, or a seed of AP_599.** Without rows,
   every value-level question below stays open, and 11b would ship an adapter
   that is structurally correct but empirically unproven. *Highest priority.*
2. Dwell bin values: 0–1 shares or 0–100 percentages? (`distribution_weight`
   semantics likewise.)
3. Should `valid=false` rows be excluded when aggregating impressions?
4. Are daily buckets cut on UTC or sensor-local days — and what is the
   relationship between the undocumented `time_zone` and documented
   `time_offset` columns?
5. `run_query` row caps and rate limits.
6. Q17 still needs their answer for *other* tenants: is
   `sensor_visitors_per_minute` generally available, or per-account opt-in? (On
   AP_599 it is enabled.)
7. Q2(a) transport decision — REST (now proven working) vs BigQuery
   dataset-share — and Q1's repo-convergence question, both unchanged.

## Where this landed

- `11-live-bluezoo-adapter.md` — Part 2/3/4 amendment (11b's build rules).
- `12-live-pos-adapter.md` — tenant-config precedent note.
- `13-production-hardening-live-mode.md` — per-tenant config surface note.
- `99-open-questions.md` — Q11, Q12, Q17, Q18 answered/narrowed; Q6 corrected.
- `working-docs/replan-data-track/bluezoo-mapping-verification.md` — pointer
  from its "remaining unknowns" section to this document.
- `docs/METRICS.md` — dwell-scalar note (BlueZoo ships it).
