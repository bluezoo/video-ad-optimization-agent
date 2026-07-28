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

_(pending)_

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

_(pending)_

## Recommended `valid` rule

_(pending — synthesized after Tests 0–5)_

## Outreach drafts

See `outreach-drafts.md` (written after synthesis).
