# BlueZoo semantics resolution — findings (MO_92, 2026-07-27)

Companion to `working-docs/bluezoo-live-verification/findings.md` Part 5, which
quantified `sensor_visits.valid` (half the rows, 72% of counts, a ~4× swing on
any impressions figure) but could not settle what it *means*. This workstream
runs the five tests in `.docs/version2-plan/bluezoo-semantics-resolution.md`
against live MO_92 data and ends with a recommended exclusion rule for Phase
11b plus sharpened client-outreach drafts.

> **A note on customer data.** MO_92 contains a real hospitality operator's
> venue names and traffic. Nothing identifying is committed anywhere in this
> branch: the operator's name, its venue names and its campaign names are
> **redacted throughout this document** (`⟨venue A⟩`, `⟨area name⟩`), and only
> shapes, units, ratios and order-of-magnitude figures are recorded. Raw query
> outputs live in `/tmp/bluezoo-semantics/` only, never committed. Treat MO_92
> credentials and any extract as customer-confidential; keys stay in `app/.env`,
> never in a commit.

**Method:** every query below went through `scripts/bluezoo_probe.py --sql`
(read-only + mandatory-time-constraint guards client-side; SELECT-only
server-side), with named columns and a stated byte budget — never `select *`.

## Preflight (2026-07-27)

- `BLUEZOO_ACCESS_KEY` + `BLUEZOO_BASE_URL` present in `app/.env` (presence
  checked only; values never printed).
- Quota-exempt `list_tables`: **19 tables**, identical to the
  `bluezoo-live-verification` scan — `sensor_pulses` entitled, `group_dwell`
  absent. Entitlements unchanged since 2026-07-27's scan.

## Test 0 — is `sensor_pulses` populated, and at what cadence?

**POPULATED — Test 2 is viable.** 30-day window (2026-06-27 → 2026-07-28):
**101,136 rows, 34 distinct sensors**, first/last timestamps on exact
15-minute boundaries (`…T23:45:00`).

**Cadence: exactly 96 rows per sensor per day** (top-10 sensors all at 96 on
2026-07-26) — the same dense 15-minute grid as `sensor_visits` (findings 5.4),
zeros-included. **Test 2 therefore equi-joins on `(sensor_id, timestamp)`**;
no bucketing needed.

One coverage caveat for Test 2's interpretation: only **34 sensors** report
pulses in the current window, versus 101 sensors across `sensor_visits`
history — the health join covers the currently-reporting subset, not every
sensor that ever existed. (34 ≈ the currently-active fleet; consistent with
96×34×31 ≈ 101k rows.)

Cost: ~1.6 MB (count over `timestamp`+`sensor_id`) + ~0.5 MB (one-day cadence
group-by). Evidence: `/tmp/bluezoo-semantics/test0-*.json` (uncommitted).

## Test 1 — the shape of the `valid` flip, and what `null` is

One full-history grouped read (`sensor_id`, `valid`, min/max `timestamp`,
`count(*)`; 17 B/row ≈ 87 MB — the workstream's one big read), 128 sensor×state
rows over 101 sensors, classified client-side:

| Category | Sensors |
|---|---|
| always `false` | **69** |
| one-way `false` → `true` (ranges never overlap) | **23** |
| always `true` | 3 |
| always `null` | 3 |
| `null` → `true` | 2 |
| `null` → `true` → `false` (see below) | 1 |

**Finding 1 — the flip is one-way, commissioning-shaped.** Zero sensors
interleave `false` and `true`: every two-state sensor's `false` window ends
before its `true` window begins. Flipped sensors spent **median 21 days false
before turning true** (min 0, max 1119) — the shape of an
install→calibrate→accept pipeline, not of outage-driven health flapping.

**Finding 2 — `null` means "before instrumentation," full stop.** Globally,
the last `null` slot is `2021-10-14T12:45Z` and the first non-null slot is
`2021-10-14T13:00Z` — a razor cutover at one 15-minute boundary. The column
was simply added on 2021-10-14; the 3 always-null sensors died before that
date. `null` is **not** a third semantic state.

**Finding 3 — `false` does not mean dead.** Of the 69 always-false sensors,
**19 still produce data today** (last slot 2026-07-27), alongside 15
currently-producing `true` sensors — 34 total, exactly the pulse-reporting
fleet Test 0 counted. `valid=false` on this tenant is a live population of
never-commissioned sensors, not retired hardware.

**Finding 4 — one true→false exception, consistent with decommission.**
Sensor 319 (ids only; no names selected) ran `true` 2021-10 → 2022-07, shows a
short `false` window 2022-12-05..12, then never reports again. ~50 of the 69
always-false sensors also went dark in the same late-2022 window — a fleet
retirement event. So the only observed reverse flip coincides with
end-of-life, reinforcing (not weakening) the commissioning reading.

Evidence: `/tmp/bluezoo-semantics/test1.json` (uncommitted; ids and
timestamps only — no name columns were ever selected).

## Test 2 — does `valid` track sensor health?

30-day equi-join `sensor_visits` × `sensor_pulses` on `(sensor_id,
timestamp)` (15-min grids match, Test 0), health =
`pulse_count / expected_pulse_count`. 34 sensors joined — 15 valid-only, 19
invalid-only, 0 mixed (as Test 1 predicts: the flag is per-sensor and stable).

| Fleet | mean health | min | median | max |
|---|---|---|---|---|
| `valid=true` (15) | **0.773** | 0.0 | **0.99** | 0.994 |
| `valid=false` (19) | **0.128** | 0.0 | **0.00** | 0.991 |

**Strong correlation, with exceptions that sharpen the meaning rather than
blur it:**

- 12/15 valid sensors sit at ≥ 0.74 (mostly ≈ 0.99); 18/19 invalid sensors sit
  ≤ 0.42 (13 of them at exactly 0.0 — delivering none of their expected
  pulses despite emitting grid rows).
- **3 valid sensors currently run health 0.0** (ids 343/855/865) — and their
  `valid` did *not* flip back. So `valid` is **not** a live health flag; a
  commissioned sensor that later degrades keeps `valid=true`.
- **1 invalid sensor is healthy (0.991, id 866)** — reporting perfectly but
  not (yet) accepted; exactly what a sensor inside Test 1's median-21-day
  pre-commissioning window looks like.

**Combined with Test 1, this names the flag:** `valid` ≈ **"accepted into
service after verified reporting"** — set once at commissioning (which is why
it correlates with health so strongly), one-way in practice, and not
maintained as ongoing health state. Ongoing outage shows up as missing rows /
zero counts (prior findings 5.4: grids are dense, absence = outage), not as a
`valid` flip.

Secondary corroboration (mac/rssi) not needed — the pulse ratio is
conclusive. Cost: ~5 MB. Evidence: `/tmp/bluezoo-semantics/test2.json`.

## Test 3 — what BlueZoo themselves do with invalid sensors

Full-history `group_sensor_history` pull, **ids only** (`group_id`,
`sensor_id`, `timestamp` — name columns deliberately never selected): 1,181
rows, 75 groups, 94 sensors, revisions 2021-08-02 → 2025-12-02 (~28 KB).
Joined client-side against Test 1's per-sensor latest `valid` state.

**Hypothesis refuted: BlueZoo does NOT exclude invalid sensors from groups.**

- Latest revision of each group contains **51 invalid + 22 valid** sensors
  (plus 10 ids that never appear in `sensor_visits`).
- **All 19 currently-live invalid sensors are members of current group
  revisions** — every one of them, same as the 15 valid ones.
- The 17 sensors never grouped skew *both* ways (10 false, 4 true, 3 null).

**Interpretation:** groups are a **venue-topology construct** (which rooms
belong to which property — prior findings 5.5), not a data-quality filter.
The scope doc's fallback rule ("if BlueZoo's own group products exclude
invalid sensors, that's a defensible rule for us") gets no support from
membership. Whether group-level *aggregates* (`group_uv_daily` etc.) filter
`valid` rows internally at computation time is invisible from membership and
moves to the outreach draft as a sharpened question.

## Test 4 — are invalid counts implausible?

30-day window (17 B/row ≈ 1.7 MB), `incoming_inner_count` by state:

| `valid` | slots | mean | p50 | p99 | max |
|---|---|---|---|---|---|
| `false` | 56,508 | 15.98 | **0.0** | 290.4 | 951.4 |
| `true` | 44,624 | 33.06 | 2.09 | 655.3 | 1219.2 |

(No `null` rows in the window — consistent with Test 1: `null` ended 2021-10-14.)

**The historical "invalid counts are higher" inverts in the current fleet.**
Full history showed false-mean 77.4 vs true-mean 31.1 (prior findings 5.3);
the last 30 days show false-mean **16.0 vs true-mean 33.1**, with invalid
sensors silent at the median slot (p50 = 0). The high historical invalid
counts came from the **retired late-2022 fleet** (Test 1 Finding 4), not from
today's uncommissioned sensors.

**Interpretation:** current invalid sensors are not implausible over-counters
— they look like real but unvetted placements (quieter locations, or simply
not calibrated/accepted). This weakens "miscalibrated garbage" and supports
"unverified/uncommissioned": the data may be physically real, but BlueZoo has
not signed off on it. Either way, the exclusion recommendation is unaffected —
what matters is that the operator's *accepted* fleet is the `true` set.

## Test 5 — UTC vs sensor-local (the testable half)

**Verdict: `timestamp` is UTC.** Local-day bucketing on our side must apply
the sensor's offset ourselves.

Getting there took a fallback chain worth recording:

- **Current window:** only America/New_York carries traffic (32 sensors); the
  2 America/Los_Angeles sensors (ids 800/859 — both in Test 2's invalid,
  health-0.0 set; distinct from the May-2024 west sensor 865 below) have zero
  visits → no cross-zone comparison possible on current data.
- **May 2024** turned out to be the right window: `-04:00` (36 sensors, 5.3 M
  visits) and `-07:00` (3 sensors, 406 K) both busy.
- Diurnal curves (hourly means over 4 weeks, busiest sensor per offset,
  ids 861 east / 865 west):
  - East (−04:00): overnight trough at **UTC 04–07** = local 00–03.
  - West (−07:00): hard-zero closed block at **UTC 06–11** = local 23–04.
  - Each trough is displaced by exactly that sensor's own UTC offset. If
    timestamps were sensor-local, both hospitality venues' quiet hours would
    sit at the *same* clock values (~00–04); they don't — they sit at
    local-midnight *converted to UTC*. Timestamps are UTC. (The 15-minute
    boundary alignment of every `min/max(timestamp)` at `…T23:45:00+00:00`
    corroborates: grids align to UTC midnight.)

**Two side findings on the zone columns:**

- `time_zone` (IANA string) is **fully populated in the current window** but
  **null everywhere in 2023/2024** — its population is a recent change.
  Historical bucketing must rely on `time_offset`; `time_zone`'s "sparse"
  reputation (prior findings 5.9) is really "recently introduced."
- `time_offset` values observed: `-04:00`/`-05:00`/`-07:00`/`+02:00` —
  DST-varying as documented, so a local-day cut needs the offset *per row*
  (or an IANA zone), not a per-sensor constant.

**What stays a client question (weaker half, as scoped):** how BlueZoo cut
*their own* daily aggregates (`group_uv_daily.date` etc.) — UTC days or
venue-local days — and which of `time_zone`/`time_offset` they intend
consumers to trust. Moves to the outreach draft, now sharpened by "the raw
feed is UTC; we've verified it."

Cost: ~25 MB across the fallback chain (zone/offset group-bys ~4 MB each ×
5 windows, two diurnal curves ~1.5 MB each, sensor pickers ~4 MB).

## Recommended `valid` rule

**Rule R, for Phase 11b:** when aggregating impressions (or any visit-count
metric) from `sensor_visits`, **include only rows where `valid IS TRUE`** —
in BigQuery SQL simply `WHERE valid`, which excludes both `false` and `NULL`.
Log the exclusion (rows in / rows kept) at query time so the policy is
visible, per `docs/METRICS.md`'s "explicit and logged" requirement.

**Why exclude `false`:** the flag means "accepted into service after verified
reporting" (Tests 1+2: one-way commissioning flip, median 21-day probation,
median pulse-health 0.99 for valid vs 0.00 for invalid). Invalid sensors are
mostly *not delivering their expected pulses* — and BlueZoo's counts are
extrapolations from sampled radio traffic, so counts from a sensor failing
its own health telemetry are not auditable measurements. This holds even
though the current invalid fleet's counts aren't implausibly high (Test 4):
"looks plausible" is not "accepted by the operator."

**Why exclude `null`:** it means "before the `valid` column existed"
(razor cutover 2021-10-14T13:00Z, Test 1) — acceptance is unknowable for
those rows, and on this tenant they are 1.2% of rows, all pre-2022. Excluding
them costs nothing and keeps the predicate one word.

**Quantified impact (so nobody is surprised):** full-history, rule R keeps
28% of summed counts (the famous ~4× swing — prior findings 5.3). But the
historical bulk of invalid counts came from a fleet retired in late 2022;
on the **current** fleet the same rule keeps 62% of counts (~1.6× swing).
The scary historical number overstates the go-forward effect.

**Confidence:** **high** on the *meaning* (commissioning acceptance — the
one-way flip, the probation window, the health correlation, and the
no-flip-back-on-degradation behavior all agree; nothing observed
contradicts it). **Medium-high** on the *policy*, because two things are
genuinely BlueZoo's to answer: (a) whether they intend consumers to filter
on it (their own groups don't — Test 3 — and their group-level aggregates
may or may not filter internally); (b) whether `valid` can ever be revoked
operationally (we saw one true→false, coincident with decommissioning).
This is exactly the split the scope doc predicted: data settles the
semantics; intent needs one confirmation.

**The confirmation question for BlueZoo** (verbatim into the outreach
draft): *"We observe that `valid` flips one-way false→true after a median
~21-day period during which the sensor's `pulse_count`/`expected_pulse_count`
ratio is near zero, and that currently-valid sensors hold ~0.99 pulse health
while never-accepted ones sit near 0.00 (current-fleet cross-section — one
not-yet-accepted sensor reporting at 0.99 looks like a pre-acceptance
snapshot); that `valid` does not flip back when a commissioned sensor later
degrades; that `NULL` simply predates the column (2021-10-14); and that your
own sensor groups contain invalid sensors. We read `valid` as 'sensor
accepted into service' and therefore plan to count impressions only from
`valid IS TRUE` rows. Please confirm this is the intended consumer behavior —
and whether your group-level aggregates (`group_uv_daily` etc.) already
apply the same filter internally."*

**Timestamp verdict (Test 5), for 11b's bucketing:** `timestamp` is UTC;
any venue-local day cut on our side must apply `time_offset` per row (or
the IANA `time_zone`, which is only populated on recent data). How BlueZoo
cut their own `group_*_daily.date` buckets remains an outreach question.

## Scope-doc validation status

- Test 0: **result** (populated, 96/day cadence). Test 1: **result** (one-way
  flip; null = pre-instrumentation). Test 2: **result** (health-correlated
  acceptance flag). Test 3: **result** (hypothesis refuted — groups don't
  filter). Test 4: **result** (current fleet inverts the historical skew).
  Test 5: **result** (UTC), via historical fallback window; no test
  documented-impossible.
- Recommended rule: above, with confidence stated.
- Amendments + outreach: see the workstream's amendment commits and
  `outreach-drafts.md`.
- Total bytes scanned this workstream: **~125 MB** (dominated by Test 1's
  one full-history 87 MB read; everything else windowed/narrow), against a
  500 GB/sensor-location ceiling.

## Outreach drafts

See `outreach-drafts.md` (written after synthesis).
