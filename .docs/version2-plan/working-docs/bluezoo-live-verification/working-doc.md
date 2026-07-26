# Workstream bluezoo-live-verification

**Branch:** version_2_bluezoo-live-verification
**Phase doc:** none — non-numbered workstream (precedent: `replan-data-track`)
**Account:** org "Walmart Demo", Cluster/Account **Apollo / AP_599**, role Super Admin

## Why this exists

The owner obtained a live BlueZoo account. Until now every schema claim in this
plan rested on BlueZoo's *published* Postman docs (verified 2026-07-16,
`working-docs/replan-data-track/bluezoo-mapping-verification.md`), with an
explicit open item: "no authenticated call was made … a live `desc_table`/
`run_query` round-trip should re-confirm column lists."

Owner directive (verbatim): *"we need to make sure we are super alinged in
bluezoo connectors so that our agents can work with any of their customer is
very crucual. So running a pass and saving the results of full scan of db is
important. we can keep it seeprate and then odify our workstreams to adpat to
the changes. Only the workstreams which are pending."*

So this workstream has two products: a **saved full scan** (the durable
artifact) and **tenant-genericity requirements** extracted from it, amended
into the pending phases only.

## Research findings

All findings below are from authenticated read-only calls made during kickoff
(raw scan saved to scratch; the committed script reproduces it).

### Confirmed — our mimic is right where it matters

- **`sensor_visits` columns match our port exactly**: `sensor_id`,
  `sensor_name`, `sensor_mac`, `sensor_address`, `sensor_latitude`,
  `sensor_longitude`, `timestamp` (TIMESTAMP), `incoming_inner_count`,
  `incoming_outer_count`, `outgoing_inner_count`, `outgoing_outer_count`
  (all FLOAT64), `valid` (BOOL) — plus two extras below.
- **`sensor_dwell` = 106 distribution bins, HHMM-encoded**, including the
  boundary bin `distribution_bin_0058_to_0100` and the open-ended
  `distribution_bin_2400_to_beyond`. ws05's port correction #1 (regenerate bin
  names in HHMM, fix the minutes-based midpoint decoder) is **vindicated
  against live data**.
- `minimum_/maximum_/average_visitors_*` naming on `sensor_visitors` confirmed.

### New facts the published docs did not contain

1. **Host is cluster-scoped; there is no canonical hostname.**
   `hermes.apollo.bluezoo.io` and `apollo-api.bluefoxengage.com` both return
   200 with identical bodies (aliases for the Apollo cluster);
   `morpheus-api.bluefoxengage.com` returns `{"status":"BAD_TOKEN"}` — a
   *different cluster*, not a canonical alternative. The profile screen names
   the cluster ("Apollo / AP_599"). **Answers Q18's hostname bullet, and
   refutes its premise** — the adapter needs a configurable base URL keyed to
   the customer's cluster, never a constant.
2. **SQL dialect is BigQuery — confirmed, not inferred.** Error text is
   verbatim BigQuery: `invalidQuery: Unrecognized name: timestamp at [1:164]`.
   Answers Q18's dialect bullet.
3. **Undocumented mandatory time filter.** `run_query` rejects any statement
   without a `date_start` / `date_end` / `timestamp` constraint in the WHERE
   clause:
   `"SQL statement has no 'date_start', 'date_end' nor 'timestamp'
   constraints. At least one constraint on those field needs to be specified
   in the WHERE clause."` BlueZoo's own documented example
   (`select * from sensor_visitors limit 1`) would fail. Every live query the
   adapter emits must carry one.
4. **19 tables on this account, not the documented 14.** Extra:
   `sensor_visitors_per_minute`, `group_convert`, `group_convert_daily/weekly/
   monthly`, `group_sensor_history`, `group_uv_quarterly`. Table availability
   is an **account entitlement**, so `list_tables` is a per-tenant capability
   probe, not a constant.
5. **`sensor_visitors_per_minute` is enabled here** — schema is
   `visitors_inner` / `visitors_outer` (occupancy, as we concluded, not
   visits). **Q17 fallback (b) is available without asking BlueZoo**, at least
   on this tenant.
6. **`group_uv_daily` carries `campaign_id` AND `campaign_name`** (plus `cuv`,
   which the published example response omitted). This **contradicts the
   2026-07-16 docs-based conclusion** recorded in Q6/Q11 ("UV tables are
   `group_id`-keyed, no campaign column, contrary to the donor spec's claim")
   — the donor spec was right and our correction of it was wrong. Needs a
   provenance amendment, not a silent edit.
7. **`group_sensor_history` is the group↔sensor mapping table**
   (`group_id`, `group_name`, `sensor_id`, `sensor_name`, `timestamp`).
   **Q11 has a real answer**: BlueZoo does have a mapping convention and it is
   API-discoverable; membership is timestamped, so it changes over time.
8. **`time_zone` (STRING) exists on every sensor table**, alongside the
   documented `time_offset`. Directly relevant to Q18's UTC-vs-sensor-local
   day-cut question — though with no rows, only the *presence* is proven.
9. **`sensor_dwell` exposes `distribution_average_duration` and
   `distribution_median_duration`.** `docs/METRICS.md:45` defers the
   "histogram → scalar dwell" rule to Phase 11 pending a real BlueZoo
   response. BlueZoo **ships the scalar directly** — the rule is "read it,
   don't derive it."
10. **The account has zero rows.** Every table queries cleanly and returns 0
    across 2020-2026. Structure is fully verifiable; **values are not** — bin
    scale (0–1 vs 0–100), `valid=false` semantics, day-cut timezone, and
    realistic magnitudes all remain unproven.

### Drift found in our own code

- `app/models/attribution.py:43` `BlueZooVisitInterval` carries
  `minimum_/maximum_/average_visitors_inner/outer` — fields that live on
  **`sensor_visitors`**, a different table from `sensor_visits`. ws05's port
  correction #5 explicitly said "keep `BlueZooVisitInterval` scoped to
  `sensor_visits` fields only" so the live adapter isn't designed against a
  single-table assumption. The donor's `store_visits` merge leaked into the
  DTO anyway. The live schema confirms two tables → a live conformer
  populating today's DTO needs **two queries joined client-side**. Recording
  this as a finding for 11b; not fixing the DTO here (that is 11b's design
  decision, and changing it now would touch merged demo-path code).

## Implementation approach

Three deliverables, deliberately small.

**1. Committed read-only probe script** — `scripts/bluezoo_probe.py`:
- Key from `app/.env` (`BLUEZOO_ACCESS_KEY`), base URL from
  `BLUEZOO_BASE_URL` (defaults to the Apollo host), both env-driven so any
  tenant/cluster can run it.
- Read-only by construction: `list_tables`, `desc_table` per table, and
  `select`-only counts/samples that always carry the mandatory time filter.
- Writes a timestamped JSON scan + a human-readable markdown summary.
- Never prints or persists the key; refuses to run if it's missing.

**2. The saved scan** — committed under
`working-docs/bluezoo-live-verification/scan/`: full 19-table schema JSON plus
a generated markdown digest. This is the artifact the owner asked to keep, and
what future workstreams diff against when a tenant differs.

**3. A tenant-genericity requirements section** — the connector rules this
scan implies, written where 11b will read them:
- base URL configurable per cluster; never hardcode a host
- `list_tables` first: treat tables as per-tenant entitlements, degrade
  gracefully when one is absent (`sensor_visitors_per_minute`, the
  `group_convert*` family and `group_uv_quarterly` are all optional)
- every query carries a time constraint (undocumented hard requirement)
- discover group↔sensor mapping from `group_sensor_history`; do not invent one
- zero rows is a legitimate answer, not an error
- BigQuery dialect for any SQL construction

**Alternatives considered.** (a) *Scratch scripts in a gitignored
`.bluezoo_connect/`* — the owner's first instinct, rejected in the option
discussion because the findings are load-bearing for 11b and would vanish.
(b) *Fold into 11b's kickoff* — rejected: 11b is still blocked on the Q1/Q2
transport decision, and this scan is what makes that conversation concrete;
blocking the scan on the blocked phase inverts the dependency. (c) *Build the
live conformer now* — out of scope by a wide margin; the account has no data
to validate against.

## Test plan

- **Probe script runs clean against the live account** and reproduces the
  recorded findings byte-for-byte (same 19 tables, same column lists) — the
  primary gate, run by me before the PR.
- **Unit tests for the script's pure helpers** (query-builder emits the
  mandatory time filter; capability detection handles a missing table; missing
  key raises a clear error) — no network in unit tests, so `make test-unit`
  stays offline and fast.
- `make test-unit` + `make test-e2e` unchanged and green (this workstream
  touches no app code).
- **No demo scenario applies** — and this is deliberate, not an omission: the
  workstream changes zero agent-visible behavior (no tools, prompts, routing,
  or artifacts). Same justification the docs-only `replan-data-track` and the
  no-agent-change Phase 6 used. `DEMO_GUIDE.md` gains nothing because there is
  nothing for the owner to click.

## Out of scope

- **No adapter code.** No `LiveBlueZooAudienceDataSource`, no
  `CachedBlueZooAudienceDataSource` — those are Phase 11b.
- **No changes to the demo path**, the `AudienceDataSource` seam, the
  `BlueZooVisitInterval` DTO, or any merged phase's code. The DTO drift found
  above is *recorded* for 11b, not fixed here.
- **No writes to BlueZoo.** Read-only calls only; `run_query` is server-side
  SELECT-only regardless.
- **No credential in the repo.** Key lives in `app/.env` (gitignored);
  `app/.env.example`-style documentation only.
- **No amendments to merged phases' docs** (per owner: pending workstreams
  only) — 11b, 12, 13, plus the shared records
  (`bluezoo-mapping-verification.md`, `99-open-questions.md`) and
  `docs/METRICS.md`'s deferred dwell note, which is a live-data question this
  scan answers.
- **No client outreach drafted here** — the remaining asks are noted, but
  writing the message is a separate task.
