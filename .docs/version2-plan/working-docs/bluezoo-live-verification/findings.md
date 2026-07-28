# BlueZoo live API verification — authenticated scan (2026-07-25)

Companion to `working-docs/replan-data-track/bluezoo-mapping-verification.md`,
which verified our mimic against BlueZoo's **published** docs on 2026-07-16 and
left one item explicitly open: *"no authenticated call was made (no AccessKey);
… a live `desc_table`/`run_query` round-trip should re-confirm column lists."*
This document closes that item.

**Accounts:** two, deliberately.
**AP_599** — org "Walmart Demo", cluster **Apollo**, Super Admin, `hermes.apollo.bluezoo.io`.
Empty; proves schema and entitlements (Parts 1–4).
**MO_92** — org "Hotels International", cluster **Morpheus** (staging),
`hermes.morpheus.bluezoo.io`, its own AccessKey. Real data from real customer
venues; proves semantics, magnitudes and the cost model (**Part 5**, added
2026-07-27). Read Part 5 before designing any live query — it contains the
quota constraint that shapes the whole adapter.
**Method:** read-only calls via `scripts/bluezoo_probe.py`; full scan artifact in
`scan/scan.json` + `scan/scan.md` (19 tables, every column, row counts over a
2020-01-01…2030-12-31 window). Everything about *schemas, entitlements and row
counts* is reproducible from that artifact by re-running the script. Four
claims below are **not** — host aliasing (Part 2 #1), the BigQuery error text
(#2), the time-constraint error message (#3), and the SELECT-only guarantee
(Part 1) — because they are properties of *rejected* calls, which no successful
scan records. Those come from the pre-kickoff manual probe calls transcribed in
this workstream's `WORK_LOG.md` (checkpoint 1), with the error strings quoted
verbatim there and below.
**Owner framing:** real data is coming later; the point of this pass is that our
schema and system are adapted to the actual BlueZoo system *before* it arrives.

## Verdict: mimic confirmed structurally; five new facts; one of our own
## corrections was wrong

Nothing found invalidates merged work. The demo path is untouched by any of
this. What changes is what Phase 11b must build against.

## Part 1 — confirmed against live schema

| Claim (source) | Live result |
|---|---|
| `sensor_visits` column list (as documented, and as ws05 verified against the docs) | **Exact match** to the published list: `sensor_id`, `sensor_name`, `sensor_mac`, `sensor_address`, `sensor_latitude`, `sensor_longitude`, `timestamp`, `incoming_inner_count`, `incoming_outer_count`, `outgoing_inner_count`, `outgoing_outer_count`, `valid` (+2 extras, Part 2 #5). Our *mimic* deliberately diverges per ws05's naming policy (`screen_visits`, keyed `screen_id`/`ad_campaign_id`, no sensor identity columns, occupancy fields merged in) — see `app/demo_data/BLUEZOO_MAPPING.md`; what this row confirms is that BlueZoo's real columns are what the docs said, so that policy was applied to an accurate baseline |
| Counts are FLOAT64, not integers | Confirmed — all four count columns FLOAT64 |
| `sensor_dwell` has 106 distribution bins | Confirmed exactly |
| Bins are HHMM-encoded, not minutes (ws05 correction #1) | **Confirmed** — `distribution_bin_0058_to_0100` and `distribution_bin_2400_to_beyond` both present. The port correction was right and the donor's minutes encoding was wrong |
| `minimum_/maximum_/average_visitors_*` naming | Confirmed on `sensor_visitors` |
| `sensor_visits` and `sensor_visitors` are separate tables (ws05 correction #5) | Confirmed — distinct tables, distinct column sets |
| `run_query` is SELECT-only | **Not tested — inherited from BlueZoo's published guarantee.** Sending a non-SELECT to verify would have been a write attempt against a customer account; this workstream is read-only by construction, so the claim stands on their documentation, not our evidence |
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

Which column satisfies it varies by table, and not even consistently within a
family: `sensor_*` carry `timestamp`; `group_uv_daily` carries `date`;
`group_convert`, `_weekly` and `_monthly` carry `date_start`/`date_end`/`date`
— but **`group_convert_daily` carries only `date`**. There is no single filter
clause that works everywhere, and no safe per-family assumption either:
discover the column from the schema, never hardcode a table→column map.

### 4. This tenant's entitlements differ from the documented set in *both* directions.

19 tables, against 14 documented. Six are beyond the documented set:
`sensor_visitors_per_minute`, `group_convert_daily`, `group_convert_weekly`,
`group_convert_monthly`, `group_sensor_history`, `group_uv_quarterly`.
(`group_convert` itself is *not* new — it appears in the documented
`list_tables` inventory, undocumented as to schema; see
`working-docs/replan-data-track/bluezoo-mapping-verification.md`.)

**And one documented table is missing: `group_dwell` is not entitled here.**
That is the more important half. 14 documented − 1 absent + 6 extras = the 19
observed. Entitlements are not a superset of the docs; they are a different
set, and a connector that assumes any documented table exists will break on
some tenant.

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
   assume any table exists — *including documented ones*: `group_dwell` is
   documented and absent here, while six undocumented tables are present. At
   minimum `sensor_visitors_per_minute`, the `group_convert*` family,
   `group_uv_quarterly`, `group_sensor_history` and `group_dwell` must all be
   optional. Missing table ⇒ that feature degrades, not an error.
3. **Every query carries a time constraint**, using the column that table
   actually has — **read from the table's own schema, not from a hardcoded
   map**: `group_convert_daily` has only `date` while the rest of its family
   has `date_start`, so even per-family assumptions are unsafe. Build this into
   the query builder so it cannot be forgotten.
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

---

# Part 5 — second tenant, with real data (MO_92, 2026-07-27)

Everything above was learned from **AP_599 (Apollo)**, which has zero rows.
BlueZoo then granted access to **MO_92 (Morpheus), org "Hotels International"** —
their staging environment, carrying real sensor data from real customer venues.
Base URL `https://hermes.morpheus.bluezoo.io/v2/dwh`, **its own AccessKey**.
Artifact: `scan-mo92/`.

This closes almost every value-level question Part 2 #7 had to leave open.

> **A note on customer data.** MO_92 contains a real hotel operator's venue
> names and traffic. This document quotes two venue names that BlueZoo
> themselves put in writing when granting access, plus numeric magnitudes, and
> deliberately does **not** reproduce the full 93-sensor inventory. The
> committed scan artifacts are schema and row counts only — no venue names, no
> traffic. Treat MO_92 credentials and any extract as customer-confidential.

## 5.0 The cluster finding, confirmed the hard way

Our Apollo key returned `BAD_TOKEN` against the Morpheus host. **Each cluster
issues its own AccessKey**, so credentials are cluster-scoped, not user-scoped —
a stronger version of Part 2 #1. Base URL and key travel together as one
credential pair, which is now a Phase 13 requirement.

Entitlements on MO_92 are **identical** to AP_599: the same 19 tables, same
`group_dwell` absence. Two independent tenants agreeing is decent evidence that
this 19-table shape is a common default rather than bespoke per customer.

## 5.1 THE OPERATIONAL CONSTRAINT: a metered bytes-scanned quota

Not documented anywhere, and the most consequential finding of the whole
workstream.

```
HTTP 400  You've reached your monthly fair use limit of 1GB data scanned per
          sensor. Please contact customer support (support@bluezoo.io) to
          upgrade your plan or consider optimizing your queries to scan less data.
```

This answers Q18's "row caps / rate limits" — and the premise was wrong again.
There is **no row cap**. There is a monthly **bytes-scanned** allowance, billed
BigQuery-style on columns read × rows scanned.

What we learned by hitting it:

- **It is small.** Roughly **735 MB** of full-history aggregate queries
  exhausted it. Whatever "per sensor" means in their message, it did *not*
  behave like 1 GB × 101 sensors.
- **Exhaustion is total.** Afterwards *every* `run_query` failed, including a
  single-sensor single-day one. There is no degraded mode.
- **Metadata and Real-time are exempt.** `list_tables`, `desc_table`,
  `get_occupancy_count` and `get_visits` all kept working throughout.
- **There is no way to check remaining allowance.** No endpoint, and responses
  carry no bytes-scanned metadata. You discover the limit by hitting it.

**Where the 735 MB went** — not row count, but *columns × history*. A single
`select distinct time_zone, time_offset` over full history cost ~245 MB; the
probe's own 2020–2030 `count(*)` sweep cost ~147 MB. Meanwhile the entire
second round — every finding in Part 5 below — cost **under 3 MB**, because it
used narrow windows and explicit column lists.

**The trap to design against:** `sensor_dwell` is 120 columns, **1,013 bytes
per row**. A `select *` over its 5.1M rows is **~5.2 GB — several times a
tenant's whole monthly allowance in one statement.**

Consequences for Phase 11b, which are architectural rather than cosmetic:

1. Never `select *`. Name columns; the query builder should require them.
2. Narrow time predicates always — which is very likely *why* BlueZoo mandates
   a time constraint at all (partition pruning).
3. An end-of-day reconciliation job issuing per-ad-play queries across many
   sensors is a plausible way to exhaust a customer's monthly allowance. Budget
   the access pattern before building it; consider one windowed bulk read per
   day over per-play queries.
4. `QuotaExceeded` needs distinct handling: unfixable by retry or narrowing,
   and it disables the whole warehouse path until reset. A live conformer
   should surface it as a named operational state, not a generic 5xx.

## 5.2 Dwell — Q18 answered, and METRICS.md's deferred rule is now settled

Sampled `sensor_dwell` rows (one venue, 2026-07-26):

| ts | total_visits | weight | avg_dur | median_dur | bin 0-1m | 1-2m | 2-3m | 5-6m |
|---|---|---|---|---|---|---|---|---|
| 00:00 | 8.613 | **0.0** | **null** | **null** | 0.0 | 0.0 | 0.0 | 0.0 |
| 17:15 | 7.623 | 2.2 | 260 | 260 | 8.65 | 12.37 | 10.46 | 14.42 |
| 22:00 | 40.004 | 3.0 | 402 | 441 | 5.77 | 8.25 | 6.97 | 5.19 |
| 01:45 | 40.800 | 0.8 | 160 | 142 | 17.30 | 24.75 | 20.92 | 6.22 |

- **Bins are 0–100 percentages, not 0–1 shares.** The 01:45 row's first three
  bins alone total 62.9. Getting this wrong would have been a 100× error.
- **`distribution_average_duration` / `_median_duration` are integer SECONDS** —
  260 s, 402 s, 160 s. That is a **direct 1:1 mapping onto our
  `dwell_time_seconds` column.** `docs/METRICS.md`'s deferred aggregation rule
  resolves to *read BlueZoo's scalar; do not weight bins.*
- **`distribution_weight` is a sample/confidence weight**, and the critical
  detail: **when it is 0.0, every bin is 0 and both scalars are NULL** — while
  `total_visits` is still non-zero. A live conformer **must handle null dwell**;
  it is not an error, it is "no distribution was derivable for this slot."
- `total_visits` is FLOAT (8.613, 40.800) — extrapolated, never an integer.

## 5.3 `valid` — half the data, and it decides a 4× swing

Across full history on `sensor_visits`:

| `valid` | rows | Σ `incoming_inner_count` | avg | sensors |
|---|---|---|---|---|
| `false` | 2,544,033 | 196,962,769 | 77.4 | 93 |
| `true` | 2,499,495 | 77,845,697 | 31.1 | 29 |
| `null` | 63,242 | 1,377,292 | 21.8 | 6 |

- **`valid=false` is not rare and not empty.** It is half the rows and **72% of
  all counts**, with a *higher* average than valid rows. Excluding it is a 4×
  change to any impressions figure.
- **`null` is an undocumented third state.**
- It is **per-sensor, not per-slot**: for one sensor over one day, 96 rows /
  96 distinct timestamps / **1 distinct `valid` value**. Some sensors do carry
  more than one value across history (128 sensor-appearances vs 101 sensors),
  so it looks like a commissioning/calibration status that flips over time.
- **`(sensor_id, timestamp)` is unique — no versioning, so no double-count
  risk** from summing across states. That was worth ruling out.

Q18's "should `valid=false` be excluded?" was filed as a small confirmation. It
is the single most consequential open question we have, and it still needs
BlueZoo's answer.

## 5.4 Tables are dense: 96 slots per sensor per day, zeros included

One sensor / one day = exactly 96 rows = 96 × 15 minutes, including all-zero
overnight slots. Confirmed across a whole day at tenant scale: 1,440 rows for
15 valid sensors = 96 each.

Useful because it means **absence of a row is not absence of traffic** — a gap
is a sensor outage, not a quiet period. A conformer can treat missing slots as
a data-quality signal rather than silently zero-filling.

## 5.5 `group_sensor_history` — Q11's answer, with real contents

75 groups, 93 sensors, 1,181 rows, spanning 2021-08-02 → 2025-12-02.

Many rows share a single identical timestamp, so the table is **snapshot- /
revision-versioned**: each membership change writes a fresh set of rows stamped
with that revision time (~12.7 revisions per sensor on average). Groups are
human-named (e.g. `hotel-downtown`) and map to venue-level sensor sets — for a
hotel, individual rooms such as the bar's dining room and named ballrooms.

**Read it as-of a date** (`max(timestamp) <= D`), never as a static lookup, and
never assume the newest revision applied to historical traffic.

## 5.6 `group_uv_daily.campaign_id` — the Q6 reversal, now fully resolved

**9,480 of 10,075 rows (94%) carry both `campaign_id` and `campaign_name`**,
across 13 distinct campaigns. So the column is not vestigial — it is in active
use, which settles the caveat Part 2 #6 had to leave open.

And we can now see *what it means*. Sample rows (2026-07-26):

| campaign_id | campaign_name | group_id | cuv | target_uv | actual_accuracy |
|---|---|---|---|---|---|
| 1301 | Hotel Olympus | 2194 | 82.81 | 2000 | 100.0 |
| 1303 | Hotel Downtown | 2196 | 959.46 | 2000 | 99.99999997 |
| 1325 | `Lobbies ` | 2212 | 179.98 | 2000 | 99.99999999 |

`campaign_id` is effectively **1:1 with `group_id`** (campaign 1303 "Hotel
Downtown" ↔ group 2196 `hotel-downtown`) and carries `target_uv` and
`actual_accuracy`. It is a **BlueZoo unique-visitor *measurement* campaign over
a sensor group — not an advertising campaign.**

So: the donor spec was right that the column exists, our docs-based correction
was wrong to deny it, **and the `ad_campaign_id` rename is more necessary than
ever** — the name now collides on the UV tables too, with a concept that means
something entirely different. (Note also the trailing space in `"Lobbies "` —
campaign names are free text and need trimming.)

`cuv` is FLOAT (82.81, 959.46): extrapolated from sampled MACs, never a count.

## 5.7 Magnitudes, for demo calibration

One real venue (a hotel bar/dining room, America/New_York), 2026-07-26, busiest
15-minute slots — `incoming_inner` / `incoming_outer`:

| slot (UTC) | inner | outer |
|---|---|---|
| 20:45 | 26.80 | 40.19 |
| 17:45 | 20.42 | 24.88 |
| 18:15 | 18.50 | 29.99 |
| 21:30 | 17.23 | 25.52 |

Tenant-wide for that day, valid sensors only: **12,280 inner visits across 15
sensors** (~800/sensor/day), peak single slot **113.6**.

**Inner is consistently below outer** (~0.67 at this venue), matching the
inner=engaged / outer=passersby model our impressions definition rests on.
These are plausible real-world figures for a demo to be calibrated against.

## 5.8 `sensor_visitors_per_minute` is entitled but DORMANT

2.8M rows historically — and **zero rows in all of 2026** (`max(timestamp)`
returns null for 2026). The feed is switched on as an entitlement but is not
currently producing data on this tenant.

Directly narrows **Q17**: fallback (b), per-minute occupancy as a sub-15-minute
proxy, is *entitled* here but has no current data to validate against. And the
general lesson for the connector: **entitlement ≠ population.** Checking
`list_tables` is necessary but not sufficient; a capability probe must also
confirm recent rows exist before relying on a feed.

## 5.9 What Part 2 #7 said we couldn't verify — status now

| Was unverifiable on AP_599 | Status on MO_92 |
|---|---|
| Dwell bin scale (0–1 vs 0–100) | **Answered** — percentages (5.2) |
| `distribution_weight` semantics | **Answered** — sample weight; 0 ⇒ null scalars (5.2) |
| `valid=false` semantics | **Quantified**, not settled — needs BlueZoo's rule (5.3) |
| Row caps / rate limits | **Answered** — bytes-scanned quota, not row caps (5.1) |
| Realistic magnitudes | **Answered** (5.7) |
| UTC vs sensor-local day cut | **Still open** — see below |

**UTC vs sensor-local remains genuinely open.** `time_zone` is *sparsely
populated* (mostly null); `time_offset` is better but also has nulls, and
varies with DST (`-04:00`/`-05:00` for New York). The tenant spans
America/New_York, America/Los_Angeles and offsets from `-08:00` to `+03:00`, so
a multi-region deployment cannot assume one timezone — and neither column can
be relied on to tell you which. This needs BlueZoo's answer, and it is now a
sharper question than before.

## Remaining asks for BlueZoo / the client

**Rewritten 2026-07-27 after MO_92.** The old #1 ask — "give us a tenant with
real data" — is **granted and closed**. Most of the rest resolved empirically.
What remains is genuinely theirs to answer:

1. **Should `valid=false` rows be excluded when aggregating impressions?** The
   single highest-value open question: it is half the rows and 72% of counts
   (5.3). We cannot guess this — the answer changes every impressions number by
   ~4×. Also: what does `valid = null` mean, and what makes a sensor flip?
2. **The quota.** Is the allowance 1 GB total or 1 GB × sensor count, and how is
   it charged for a query spanning many sensors? Is there any way to check
   remaining consumption? Are the tables partitioned/clustered on
   `timestamp`/`sensor_id`, so we can predict cost? And what allowance would a
   production end-of-day reconciliation job need? (5.1)
3. **Day-cut timezone.** UTC or sensor-local? What is the intended relationship
   between `time_zone` (sparse) and `time_offset` (DST-varying, also nullable),
   and which should a multi-region consumer trust? (5.9)
4. **`group_uv_daily.campaign_id`** — confirm it is a UV-measurement campaign
   over a group, as the data suggests, and that it will never carry an
   advertiser's campaign. (5.6)
5. **`sensor_visitors_per_minute`** — dormant on MO_92 since 2025. Is it
   generally available, opt-in, or being retired? This decides whether Q17's
   fallback (b) is real. (5.8)
6. **A docs bug to report back:** every `run_query` requires a time constraint,
   which is undocumented, and their own published example
   (`select * from sensor_visitors limit 1`) fails against the live API.
7. Q2(a) transport decision — REST (now proven working end-to-end against real
   data) vs BigQuery dataset-share — and Q1's repo-convergence question, both
   unchanged and both decisions rather than unknowns.

## Where this landed

- `11-live-bluezoo-adapter.md` — Part 2/3/4 amendment (11b's build rules).
- `12-live-pos-adapter.md` — tenant-config precedent note.
- `13-production-hardening-live-mode.md` — per-tenant config surface note.
- `99-open-questions.md` — Q11, Q12, Q17, Q18 answered/narrowed; Q6 corrected.
- `working-docs/replan-data-track/bluezoo-mapping-verification.md` — pointer
  from its "remaining unknowns" section to this document.
- `docs/METRICS.md` — dwell-scalar note (BlueZoo ships it).
