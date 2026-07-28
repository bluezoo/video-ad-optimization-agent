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

_(pending)_

## Test 2 — does `valid` track sensor health?

_(pending — gated on Test 0)_

## Test 3 — what BlueZoo themselves do with invalid sensors

_(pending)_

## Test 4 — are invalid counts implausible?

_(pending)_

## Test 5 — UTC vs sensor-local (the testable half)

_(pending)_

## Recommended `valid` rule

_(pending — synthesized after Tests 0–5)_

## Outreach drafts

See `outreach-drafts.md` (written after synthesis).
