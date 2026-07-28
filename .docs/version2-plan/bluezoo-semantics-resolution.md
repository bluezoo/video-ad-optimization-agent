# Workstream — BlueZoo semantics resolution (`valid`, day-cut)

**Type:** non-numbered workstream (precedent: `replan-data-track`, `bluezoo-live-verification`). Not a phase in `00-overview.md`'s numbered sequence, but it **runs before Phase 11b** — see Dependencies.

**Status:** not started. Registered 2026-07-27.

## Goal

Answer, from live data rather than from an email round-trip, as much as possible of the two highest-value semantic unknowns blocking Phase 11b:

1. **What `sensor_visits.valid` means, and what the exclusion rule should be.** Currently the single most consequential open question in the plan: `valid=false` is **half the rows and 72% of all counts**, so including or excluding it swings any impressions figure **~4×**. There is also an undocumented `null` third state.
2. **Whether `timestamp` is UTC or sensor-local, and how days are cut.** `time_zone` is sparsely populated and `time_offset` is DST-varying and nullable, across a tenant spanning `-08:00`…`+03:00`.

The deliverable is **evidence plus a recommended rule**, not certainty. See "What this cannot settle."

## Why this is separate from Phase 11b

Same reasoning that kept `bluezoo-live-verification` separate: this is empirical API research whose *output is an input to 11b's design*. Folding exploratory querying into a large build phase muddies both. 11b should start already knowing which rows it counts.

## Access

Both tenants are already provisioned. Credentials live in `app/.env` (gitignored) — **never** in a commit, a doc, or a chat message.

| Tenant | Base URL | Use here |
|---|---|---|
| MO_92 (Morpheus, staging) | `https://hermes.morpheus.bluezoo.io/v2/dwh` | **All of it.** 5.1M rows, 101 sensors, 2021-03 → current |
| AP_599 (Apollo) | `https://hermes.apollo.bluezoo.io/v2/dwh` | Not useful — zero rows |

Keys are **cluster-scoped**: the Apollo key returns `BAD_TOKEN` against Morpheus. Use `scripts/bluezoo_probe.py` (already committed, read-only, SELECT-only, guards the mandatory time constraint, models `QuotaExceeded`). Read `working-docs/bluezoo-live-verification/findings.md` **Part 5** first — it holds every fact this workstream builds on.

## The tests

All are narrow aggregates. Every query **must** carry a `timestamp`/`date` constraint (undocumented BlueZoo requirement) and **must** name columns explicitly — never `select *`.

### Test 0 — is `sensor_pulses` populated here? (do this first)

The MO_92 scan counted only 6 of 19 tables; `sensor_pulses`'s row count is **unknown**. Test 2 depends on it. One cheap count settles it, and also establishes the pulse cadence (does it share `sensor_visits`' 15-minute grid, or is it coarser?). If the table is empty, Test 2 is dead and the health hypothesis stays a client question.

### Test 1 — the shape of the flip, and what `null` is

```sql
select sensor_id, valid,
       min(timestamp) as first_seen, max(timestamp) as last_seen, count(*) as slots
from sensor_visits
where timestamp between <start> and <end>
group by sensor_id, valid
```

Reads ~17 bytes/row (`sensor_id` 8 + `valid` 1 + `timestamp` 8) — ~87 MB at full history, far less windowed.

- Per sensor, if the `false` window and the `true` window **do not overlap** → `valid` is a one-way commissioning/calibration flag.
- If they **interleave** → it is health/outage driven, and must be evaluated per slot rather than per sensor.
- The same result answers `null`: if every `null` predates every non-null, the column was simply **added later** and `null` means "before instrumentation," not a third semantic state.

### Test 2 — does `valid` track sensor health?

`sensor_pulses` carries **`expected_pulse_count` and `pulse_count`** — a per-sensor, per-timestamp health ratio. This is the test that could actually *name* the meaning.

```sql
select v.sensor_id,
       countif(v.valid)     as valid_slots,
       countif(not v.valid) as invalid_slots,
       avg(if(v.valid,     safe_divide(p.pulse_count, p.expected_pulse_count), null)) as health_when_valid,
       avg(if(not v.valid, safe_divide(p.pulse_count, p.expected_pulse_count), null)) as health_when_invalid
from sensor_visits v
join sensor_pulses p
  on p.sensor_id = v.sensor_id and p.timestamp = v.timestamp
where v.timestamp between <start> and <end>
  and p.timestamp between <start> and <end>
group by 1
```

If `health_when_invalid` is materially lower, `valid` means "the sensor was reporting properly." **Adjust the join if Test 0 shows the pulse cadence differs** from the 15-minute visit grid — bucket both sides rather than joining on exact equality.

`sensor_pulses` also carries `mac_count_global` / `mac_count_local` / `rssi_*` — secondary corroboration if the pulse ratio is inconclusive.

### Test 3 — what BlueZoo themselves do with invalid sensors

`group_sensor_history` (1,181 rows, trivially cheap) gives group membership over time. If sensors are absent from every group while invalid, then **BlueZoo's own group-level products already exclude them** — which is a defensible rule for us regardless of the stated semantics, and arguably better evidence than a definition.

### Test 4 — are invalid counts implausible?

We already know invalid rows average *higher* than valid ones. Distribution shape distinguishes "miscalibrated over-counting" from "fine but unverified":

```sql
select valid, count(*) as slots,
       avg(incoming_inner_count) as mean,
       approx_quantiles(incoming_inner_count, 100)[offset(50)] as p50,
       approx_quantiles(incoming_inner_count, 100)[offset(99)] as p99,
       max(incoming_inner_count) as max
from sensor_visits
where timestamp between <start> and <end>
group by valid
```

### Test 5 — UTC vs sensor-local (partial)

**Testable:** what the raw `timestamp` column *is*. Pick sensors with a known, populated `time_zone` in different zones and plot the diurnal curve. Foot traffic has a reliable overnight minimum; if that trough sits at the same UTC hour for sensors in different zones, timestamps are UTC and local-day bucketing must apply `time_offset` ourselves. This is the half that actually governs our own bucketing.

**Weaker:** how BlueZoo cuts *their* daily aggregates. `group_uv_daily.cuv` is deduplicated and extrapolated, so it will not reconcile arithmetically against summed visit counts — don't expect a clean tie-out. Report what the diurnal test shows and leave BlueZoo's own bucketing as a (now much sharper) client question.

## Cost

Not a constraint any more, but stay disciplined — see `findings.md` Part 5.1. The quota is an **abuse guard with a per-tenant ceiling BlueZoo raises on request**; MO_92 is at **500 GB per sensor location** this month. Every test above is a narrow aggregate: ~150 MB worst case at full history, single-digit MB windowed. Prefer a bounded window first and widen only if the answer is ambiguous.

The probe defaults to a 30-day count window; `--full-history` is opt-in. Note that a query spanning all locations appears to draw against *every* location's allowance rather than a shared pool (735 MB once tripped a limit nominally worth 1 GB × 101), so prefer per-sensor or per-group scoping where a test allows it.

## What this cannot settle

Whether BlueZoo **intends** consumers to exclude `valid=false` rows, and whether that intent is stable policy. A 4× swing on the headline metric is not something to infer from correlation. This workstream's job is to convert an open-ended question into a confirmable one:

> "We observe that `valid=false` coincides with X, that invalid sensors are/aren't in groups, and that the flag is/isn't one-way. We therefore plan to apply rule E. Confirm?"

That is far likelier to get a fast, correct answer than "what does `valid` mean?"

## Deliverables

1. `working-docs/bluezoo-semantics-resolution/findings.md` — evidence per test, and **a recommended `valid` rule stated plainly enough for 11b to implement**.
2. Amendments with provenance to `11-live-bluezoo-adapter.md`, `99-open-questions.md` (Q18), and `docs/METRICS.md`'s `valid` appendix row — per the DISCOVERY protocol in `tracking-workstream-progress`.
3. **The client-outreach drafts**, carried over from `bluezoo-live-verification` and now sharpened by the evidence. To BlueZoo: the `valid` rule, quota accounting per sensor location, whether the raised ceiling persists past "this month," day-cut confirmation, `campaign_id` confirmation, per-minute feed status, and their docs bug (the published example query fails against the live API). To the retailer/PoS side: Q3/Q4.
4. Any new probe capability needed, as tested code in `scripts/`.

## Constraints

- **Read-only.** `list_tables`, `desc_table`, SELECT. No writes, ever.
- **No credentials, no customer identifiers committed.** MO_92 carries a real hospitality operator's data. Redact organization, venue, campaign and group names as `bluezoo-live-verification` did; commit shapes, units, ratios and magnitudes only. Sweep the branch before the PR.
- **No app behavior change expected.** If that turns out false, stop and re-scope — a semantics finding that demands code is 11b's work, not this workstream's.

## Validation

- [ ] Every test either produced a result or is documented as impossible, with the reason (e.g. `sensor_pulses` empty).
- [ ] A recommended `valid` rule exists, with its evidence and its confidence stated honestly.
- [ ] Amendments carry provenance notes; `99-open-questions.md` Q18 reflects what closed and what did not.
- [ ] Client-outreach drafts written.
- [ ] Credential/PII sweep clean across the whole branch diff.
- [ ] `make test` green; lint clean.
- [ ] Demo scenario skipped by design **only if** there is genuinely zero agent-visible change — state the justification explicitly, as `bluezoo-live-verification` did.

## Dependencies

`bluezoo-live-verification` (merged, `e834bb9`) — this builds directly on its Part 5. **Blocks nothing formally**, but Phase 11b should not start before it, because 11b would otherwise have to invent the `valid` policy blind.
