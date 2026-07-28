# BlueZoo Semantics Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution-mode exception (owner-approved at plan gate):** Task 1 (probe extension — real code) runs via subagent-driven-development as normal. Tasks 2–11 are live research against a metered, credentialed, customer-confidential tenant where each query's result gates the next query's shape — they run **inline in the controlling session**, with every result mirrored into `findings.md` and `WORK_LOG.md` as it lands. This is the same posture `bluezoo-live-verification` used. Task 12 uses `requesting-code-review` + `finishing-a-development-branch` as normal.

**Goal:** Resolve empirically what `sensor_visits.valid` means (the ~4× impressions swing) and whether `timestamp` is UTC, producing a recommended exclusion rule 11b can implement plus sharpened client-outreach drafts.

**Architecture:** A small extension to the existing read-only probe (`scripts/bluezoo_probe.py`) gives it an `--sql` runner and `app/.env`-sourced base URL; then six live tests (0–5) run as narrow, byte-budgeted SELECT aggregates against MO_92, each recorded (redacted) in `findings.md`; findings then drive doc amendments and outreach drafts.

**Tech Stack:** Python stdlib only (urllib), pytest, BlueZoo DWH REST API (BigQuery SQL dialect).

## Global Constraints

- **Read-only:** `list_tables`, `desc_table`, SELECT only. The probe's client-side guards stay in the path for every query.
- **Every query carries a `timestamp`/`date` constraint and names columns explicitly — never `select *`.** (Undocumented server-side requirement + metered bytes-scanned quota.)
- **Bounded window first** (30 days default), widen only if the answer is ambiguous; prefer per-sensor/per-group scoping (per-location quota accounting suspicion, findings.md 5.1). MO_92 ceiling this month: 500 GB/sensor location; every query below is ≤ ~90 MB worst case.
- **Redaction at capture time:** MO_92 is a real hospitality operator's data. Never select name columns unless the test requires them (`time_zone` OK; avoid `sensor_name`, `group_name`, `campaign_name`). Raw query outputs go to `/tmp/bluezoo-semantics/` (never committed); only redacted shapes/units/ratios/magnitudes enter committed files, `⟨venue A⟩`-style.
- **Never commit a credential.** `BLUEZOO_ACCESS_KEY` / `BLUEZOO_BASE_URL` live in `app/.env` (gitignored) only.
- **No app behavior change.** If a finding demands one: stop, log a DISCOVERY, re-scope with the owner.
- **No AI-attribution trailers** in commits or the PR body. `STATUS.md` edits only in the main checkout.
- Today is 2026-07-27; "30-day window" below = `timestamp >= '2026-06-27' and timestamp < '2026-07-28'`.

---

### Task 1: Probe extension — env-file base URL + `--sql` runner

**Files:**
- Modify: `scripts/bluezoo_probe.py` (functions `load_access_key` at ~line 306, `main` at ~line 320)
- Test: `tests/unit/test_bluezoo_probe.py`

**Interfaces:**
- Consumes: existing `BlueZooProbe.query()` (guarded SELECT), existing `load_access_key()`.
- Produces: `load_env_var(name: str, env_file: Path | None = None) -> str` (env wins, falls back to `app/.env`, returns `""` if absent); `run_sql(probe: BlueZooProbe, sql: str) -> str` (guarded query, rows rendered as indented JSON); CLI flag `--sql "<select …>"`; `--base-url` default now honors `BLUEZOO_BASE_URL` from `app/.env`. All later tasks issue queries via `python scripts/bluezoo_probe.py --sql "…"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_bluezoo_probe.py`:

```python
class TestLoadEnvVar:
    """Base URL and key both come from the environment or app/.env —
    the env file half previously existed only for the AccessKey."""

    def test_environment_wins_over_env_file(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BLUEZOO_BASE_URL=https://file.example/v2/dwh\n")
        monkeypatch.setenv("BLUEZOO_BASE_URL", "https://env.example/v2/dwh")
        assert (
            bluezoo_probe.load_env_var("BLUEZOO_BASE_URL", env_file)
            == "https://env.example/v2/dwh"
        )

    def test_env_file_value_is_read_and_unquoted(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BLUEZOO_BASE_URL", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('OTHER=x\nBLUEZOO_BASE_URL="https://file.example/v2/dwh"\n')
        assert (
            bluezoo_probe.load_env_var("BLUEZOO_BASE_URL", env_file)
            == "https://file.example/v2/dwh"
        )

    def test_missing_everywhere_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BLUEZOO_BASE_URL", raising=False)
        assert bluezoo_probe.load_env_var("BLUEZOO_BASE_URL", tmp_path / "absent") == ""


class TestRunSql:
    def test_renders_rows_as_json(self):
        probe = FakeProbe(
            tables=["sensor_visits"],
            schemas={"sensor_visits": _cols("sensor_id", "timestamp")},
            counts={"sensor_visits": 42},
        )
        out = bluezoo_probe.run_sql(
            probe, "select count(*) as n from sensor_visits where timestamp >= '2026-07-01'"
        )
        assert json.loads(out) == [{"n": 42}]

    def test_guards_still_apply(self):
        probe = FakeProbe(tables=[], schemas={})
        with pytest.raises(BlueZooError, match="constrain"):
            bluezoo_probe.run_sql(probe, "select 1 from t")
        with pytest.raises(BlueZooError, match="SELECT"):
            bluezoo_probe.run_sql(probe, "delete from t where timestamp > '2020-01-01'")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_bluezoo_probe.py -v -k "LoadEnvVar or RunSql"`
Expected: FAIL — `AttributeError: module 'bluezoo_probe' has no attribute 'load_env_var'` (and `run_sql`).

- [ ] **Step 3: Implement**

In `scripts/bluezoo_probe.py`, replace `load_access_key()` with:

```python
def load_env_var(name: str, env_file: Path | None = None) -> str:
    """Environment wins; otherwise app/.env (gitignored, never committed)."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    env_file = env_file or Path(__file__).resolve().parent.parent / "app" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, raw = line.partition("=")
            if key.strip() == name:
                return raw.strip().strip("'\"")
    return ""


def load_access_key() -> str:
    return load_env_var("BLUEZOO_ACCESS_KEY")


def run_sql(probe: BlueZooProbe, sql: str) -> str:
    """One guarded SELECT, rendered as JSON for the terminal."""
    return json.dumps(probe.query(sql), indent=2, default=str)
```

In `main()`, change the `--base-url` default and add `--sql`:

```python
    parser.add_argument(
        "--base-url",
        default=load_env_var("BLUEZOO_BASE_URL") or DEFAULT_BASE_URL,
        help="Cluster-specific Data Warehouse base URL (env or app/.env BLUEZOO_BASE_URL)",
    )
    parser.add_argument(
        "--sql",
        help="Run one SELECT (read-only + time-constraint guards apply) and print rows as JSON",
    )
```

And in the body, inside the existing `try` block, before the scan:

```python
    try:
        probe = BlueZooProbe(load_access_key(), args.base_url)
        if args.sql:
            print(run_sql(probe, args.sql))
            return 0
        result = scan(probe, window=FULL_HISTORY if args.full_history else None)
```

Also update the module docstring's Environment section: `BLUEZOO_BASE_URL` is now read from `app/.env` too.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_bluezoo_probe.py -v`
Expected: all PASS (existing tests too — `load_access_key` behavior unchanged).

- [ ] **Step 5: Full gate + commit**

Run: `make test-unit && make lint`
Expected: PASS / clean.

```bash
git add scripts/bluezoo_probe.py tests/unit/test_bluezoo_probe.py
git commit -m "probe: read BLUEZOO_BASE_URL from app/.env; add guarded --sql runner"
```

---

### Task 2: Preflight — credentials present, cluster reachable, entitlements unchanged

**Files:** none modified. Evidence: `findings.md` skeleton created.

**Interfaces:**
- Consumes: Task 1's `--sql`; `BLUEZOO_ACCESS_KEY` + `BLUEZOO_BASE_URL` in `app/.env` (owner-provided — if `grep -c '^BLUEZOO_ACCESS_KEY=..*' app/.env` returns 0, STOP and ask the owner; do not proceed).
- Produces: confirmed working connection; `findings.md` created with a Preflight section.

- [ ] **Step 1: Verify credentials present (presence only, never print values)**

```bash
grep -c '^BLUEZOO_ACCESS_KEY=..*' app/.env && grep -c '^BLUEZOO_BASE_URL=..*' app/.env
```
Expected: `1` and `1`. If not: stop, ask owner.

- [ ] **Step 2: Metadata round-trip (quota-exempt)**

```bash
mkdir -p /tmp/bluezoo-semantics
python3 - << 'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location("bp", "scripts/bluezoo_probe.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
probe = m.BlueZooProbe(m.load_access_key(), m.load_env_var("BLUEZOO_BASE_URL") or m.DEFAULT_BASE_URL)
tables = probe.list_tables()
print(len(tables), "tables")
print("\n".join(tables))
EOF
```
Expected: `19 tables`, same set as `scan-mo92/scan.md` (includes `sensor_pulses`, no `group_dwell`). If `BAD_TOKEN`: wrong cluster/key — stop, ask owner.

- [ ] **Step 3: Create findings skeleton + WORK_LOG entry, commit**

Create `.docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md` with title, the customer-data redaction note (copy the note verbatim from `bluezoo-live-verification/findings.md` Part 5 preamble), and empty sections: Preflight, Test 0–Test 5, Recommended `valid` rule, Outreach drafts pointer. Record preflight result (table count only).

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md
git commit -m "semantics: findings skeleton + preflight (19 tables confirmed on MO_92)"
```

---

### Task 3: Test 0 — is `sensor_pulses` populated, and at what cadence?

**Files:** `findings.md` Test 0 section. Evidence to `/tmp/bluezoo-semantics/test0*.json`.

**Interfaces:**
- Produces: verdict `POPULATED(cadence=X)` or `EMPTY` → gates Task 6 (Test 2) and its join shape.

- [ ] **Step 1: 30-day count (≤ ~2 MB: timestamp 8 B + sensor_id 8 B per row, row count unknown)**

```bash
python scripts/bluezoo_probe.py --sql "select count(*) as n, min(timestamp) as first_ts, max(timestamp) as last_ts, count(distinct sensor_id) as sensors from sensor_pulses where timestamp >= '2026-06-27' and timestamp < '2026-07-28'" | tee /tmp/bluezoo-semantics/test0-window.json
```
Expected: one row. Interpret:
- `n > 0` → populated; go to Step 2.
- `n = 0` → Step 1b full-history count (`timestamp >= '2020-01-01' and timestamp < '2030-12-31'`, reads timestamp only, ~8 B × unknown rows — if this is 0 too, **Test 2 is dead**: record "EMPTY — health-correlation test impossible; hypothesis stays a client question" in findings.md and skip Task 6).

- [ ] **Step 2: Cadence — rows per sensor per day**

```bash
python scripts/bluezoo_probe.py --sql "select sensor_id, count(*) as rows_per_day from sensor_pulses where timestamp >= '2026-07-26' and timestamp < '2026-07-27' group by sensor_id order by rows_per_day desc limit 10" | tee /tmp/bluezoo-semantics/test0-cadence.json
```
(If Step 1 showed the last row predates 2026-07-26, shift this one-day window to end at `last_ts`.)
Interpret: `rows_per_day` ≈ 96 → 15-minute grid (Test 2 equi-joins on `(sensor_id, timestamp)`); ≈ 1440 → per-minute; ≈ 24 → hourly (Test 2 buckets both sides with `timestamp_trunc(timestamp, hour)`).

- [ ] **Step 3: Record + commit**

Write verdict, cadence, and byte cost into findings.md Test 0; mirror one line to WORK_LOG.

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 0: sensor_pulses population + cadence"
```

---

### Task 4: Test 1 — the shape of the `valid` flip, and what `null` is

**Files:** `findings.md` Test 1 section.

**Interfaces:**
- Produces: per-sensor flip classification (one-way commissioning vs interleaved health) + `null` timing verdict → primary evidence for the recommended rule (Task 9) and for Test 3's join (Task 7: the per-sensor latest `valid` state).

- [ ] **Step 1: Full-history grouped scan (~87 MB: sensor_id 8 + valid 1 + timestamp 8 = 17 B × 5.1 M rows — the one deliberately full-history read on a wide table; scope doc budgets it)**

```bash
python scripts/bluezoo_probe.py --sql "select sensor_id, valid, min(timestamp) as first_seen, max(timestamp) as last_seen, count(*) as slots from sensor_visits where timestamp >= '2021-01-01' and timestamp < '2026-07-28' group by sensor_id, valid order by sensor_id" | tee /tmp/bluezoo-semantics/test1.json
```
Expected: ~128 rows (the 128 sensor×valid appearances findings 5.3 counted).

- [ ] **Step 2: Classify client-side (no further scan cost)**

For each sensor with both `false` and `true` rows: if `max(ts|false) < min(ts|true)` (or symmetric) → one-way flip; if ranges overlap → interleaved. For `null`: check whether `max(ts|null)` per sensor (and globally) predates all non-null `min(ts)` → "column added later," else a real third state. Compute: #sensors always-false / always-true / one-way-flipped / interleaved / with-null.

- [ ] **Step 3: Record + commit** (aggregate counts and date shapes only — no sensor names were selected)

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 1: valid flip shape + null timing"
```

---

### Task 5: Test 4 — are invalid counts implausible? (distribution shape)

**Files:** `findings.md` Test 4 section.

**Interfaces:**
- Produces: per-state distribution (mean/p50/p99/max of `incoming_inner_count`) → distinguishes "miscalibrated over-counting" from "fine but unverified" in the recommendation.

- [ ] **Step 1: 30-day windowed distribution (~1.7 MB: valid 1 + timestamp 8 + incoming_inner_count 8 = 17 B × ~98 K rows)**

```bash
python scripts/bluezoo_probe.py --sql "select valid, count(*) as slots, avg(incoming_inner_count) as mean, approx_quantiles(incoming_inner_count, 100)[offset(50)] as p50, approx_quantiles(incoming_inner_count, 100)[offset(99)] as p99, max(incoming_inner_count) as max from sensor_visits where timestamp >= '2026-06-27' and timestamp < '2026-07-28' group by valid" | tee /tmp/bluezoo-semantics/test4-window.json
```
Expected: up to 3 rows (false/true/null). If the window's shape is ambiguous (e.g., too few invalid slots recently), re-run over full history (~87 MB, same columns) — widen-only-if-ambiguous rule.

- [ ] **Step 2: Record + commit**

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 4: count distribution by valid state"
```

---

### Task 6: Test 2 — does `valid` track sensor health? (CONDITIONAL on Test 0)

Skip entirely (documented, not silent) if Test 0 returned EMPTY.

**Files:** `findings.md` Test 2 section.

**Interfaces:**
- Consumes: Test 0's cadence verdict (join shape).
- Produces: `health_when_valid` vs `health_when_invalid` → the test that could *name* the semantics.

- [ ] **Step 1: Windowed join (30 days; visits side 17 B × ~98 K + pulses side 32 B × Test-0 count — single-digit MB)**

If cadence = 96/day (15-min grid), run the scope doc's SQL verbatim with the window filled in:

```bash
python scripts/bluezoo_probe.py --sql "select v.sensor_id, countif(v.valid) as valid_slots, countif(not v.valid) as invalid_slots, avg(if(v.valid, safe_divide(p.pulse_count, p.expected_pulse_count), null)) as health_when_valid, avg(if(not v.valid, safe_divide(p.pulse_count, p.expected_pulse_count), null)) as health_when_invalid from sensor_visits v join sensor_pulses p on p.sensor_id = v.sensor_id and p.timestamp = v.timestamp where v.timestamp >= '2026-06-27' and v.timestamp < '2026-07-28' and p.timestamp >= '2026-06-27' and p.timestamp < '2026-07-28' group by 1 order by 1" | tee /tmp/bluezoo-semantics/test2.json
```

If cadence ≠ 96/day, replace the join condition with hour buckets:
`on p.sensor_id = v.sensor_id and timestamp_trunc(p.timestamp, hour) = timestamp_trunc(v.timestamp, hour)` (and note in findings that the ratio is hour-averaged).

If the 30-day window contains only one `valid` state (plausible per Test 1 — the flag is per-sensor), widen to a window Test 1 showed contains flips, or scope to specific flipped sensors' ids: `and v.sensor_id in (…)` — per-sensor scoping is quota-cheaper anyway.

- [ ] **Step 2: Secondary corroboration only if Step 1 is inconclusive** (`avg(p.mac_count_global)`, `avg(p.rssi_wifi_avg)` by valid state, same join, same window).

- [ ] **Step 3: Record + commit**

Interpretation: `health_when_invalid` materially lower → `valid` ≈ "sensor reporting properly." Similar ratios → `valid` is NOT pulse-health; say so plainly.

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 2: valid vs pulse-health correlation"
```

---

### Task 7: Test 3 — what BlueZoo themselves do with invalid sensors

**Files:** `findings.md` Test 3 section.

**Interfaces:**
- Consumes: Test 1's per-sensor latest `valid` state (from `/tmp/bluezoo-semantics/test1.json`, client-side).
- Produces: are invalid sensors in current/any group revisions → the "BlueZoo's own products exclude them" evidence.

- [ ] **Step 1: Full-history membership pull (~28 KB: group_id 8 + sensor_id 8 + timestamp 8 = 24 B × 1,181 rows). IDs only — deliberately no `group_name`/`sensor_name` (redaction by construction). Full history is REQUIRED here: kickoff research confirmed 0 rows in any 30-day window (revisions end 2025-12).**

```bash
python scripts/bluezoo_probe.py --sql "select group_id, sensor_id, timestamp from group_sensor_history where timestamp >= '2021-01-01' and timestamp < '2026-07-28' order by timestamp, group_id, sensor_id" | tee /tmp/bluezoo-semantics/test3.json
```
Expected: 1,181 rows, revisions 2021-08 → 2025-12.

- [ ] **Step 2: Client-side join** — latest revision per group (`max(timestamp)` per group_id → its sensor set); compare against Test 1's sensors by latest `valid` state. Compute: of currently-invalid sensors, how many appear in the latest revision of any group; same for valid sensors; and historically, whether sensors dropped out of groups around their `valid` flip dates (compare revision timestamps with Test 1 flip boundaries).

- [ ] **Step 3: Record + commit**

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 3: group membership vs valid state"
```

---

### Task 8: Test 5 — UTC vs sensor-local (the testable half)

**Files:** `findings.md` Test 5 section.

**Interfaces:**
- Consumes: nothing from other tests.
- Produces: verdict on what the raw `timestamp` column IS (UTC vs local) → governs our own bucketing; BlueZoo's own daily bucketing stays an outreach question.

- [ ] **Step 1: Which zones are populated, and pick candidate sensors (~3.5 MB: time_zone ~20 + sensor_id 8 + timestamp 8 ≈ 36 B × ~98 K rows)**

```bash
python scripts/bluezoo_probe.py --sql "select time_zone, count(distinct sensor_id) as sensors, count(*) as slots from sensor_visits where timestamp >= '2026-06-27' and timestamp < '2026-07-28' group by time_zone order by slots desc" | tee /tmp/bluezoo-semantics/test5-zones.json
```
Pick the two most-populated **distinct** zones with different UTC offsets (findings 5.9 says the tenant spans `-08:00`…`+03:00`). If only one non-null zone has traffic in the window, fall back to `time_offset` groups instead; if even that fails, document Test 5 as impossible on current data.

- [ ] **Step 2: One busiest sensor id per zone (~3.5 MB, same columns + incoming_inner_count)**

```bash
python scripts/bluezoo_probe.py --sql "select sensor_id, any_value(time_zone) as tz, sum(incoming_inner_count) as vol from sensor_visits where timestamp >= '2026-06-27' and timestamp < '2026-07-28' and time_zone in ('<ZONE_A>', '<ZONE_B>') group by sensor_id order by vol desc limit 10" | tee /tmp/bluezoo-semantics/test5-sensors.json
```

- [ ] **Step 3: Diurnal curve per chosen sensor (14 days; ~1.6 MB each: sensor_id 8 + timestamp 8 + two counts 16 ≈ 32 B × ~46 K window rows)**

For each of the two sensor ids:

```bash
python scripts/bluezoo_probe.py --sql "select extract(hour from timestamp) as utc_hour, avg(incoming_inner_count + incoming_outer_count) as traffic from sensor_visits where timestamp >= '2026-07-13' and timestamp < '2026-07-27' and sensor_id = <ID> group by utc_hour order by utc_hour" | tee /tmp/bluezoo-semantics/test5-diurnal-<ID>.json
```
Interpret: locate each curve's overnight trough (minimum contiguous hours). Same UTC trough hour across different zones → **timestamps are sensor-local** (every venue is quiet at "local 3am" = same clock value). Troughs offset by exactly the zones' UTC-offset difference → **timestamps are UTC**. (One venue type caveat: hospitality venues may run late; use the trough *center*, not edges.)

- [ ] **Step 4: Record + commit** (zone names are IANA strings, not customer identifiers — safe to commit; sensor ids committed, names never selected)

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics Test 5: diurnal UTC-vs-local verdict"
```

---

### Task 9: Synthesize — the recommended `valid` rule

**Files:** `findings.md` — "Recommended rule" section + summary table.

**Interfaces:**
- Consumes: Tests 0–5 results.
- Produces: a rule stated implementably for 11b, e.g. the shape: *"Exclude rows where `valid = false`; treat `valid IS NULL` as `<include|exclude>` because `<evidence>`; confidence `<level>` because `<what data cannot settle>`"* — the actual content comes from the evidence, not this plan.

- [ ] **Step 1: Write the synthesis.** Must contain: (a) one-paragraph answer per scope-doc validation bullet — every test produced a result or is documented impossible with the reason; (b) the recommended rule in implementable terms (which SQL predicate, which state handling for `null`); (c) honest confidence + the confirmation question for BlueZoo phrased exactly as the scope doc's template: "We observe that `valid=false` coincides with X, that invalid sensors are/aren't in groups, and that the flag is/isn't one-way. We therefore plan to apply rule E. Confirm?"; (d) the Test 5 verdict on `timestamp` and what stays a client question.

- [ ] **Step 2: Self-check against scope-doc "Validation" checklist** (all 7 boxes addressable), commit:

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/findings.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics: findings synthesis + recommended valid rule"
```

---

### Task 10: Amendments with provenance

**Files:**
- Modify: `.docs/version2-plan/11-live-bluezoo-adapter.md` (append to its Part 5 amendment chain)
- Modify: `.docs/version2-plan/99-open-questions.md` (Q18)
- Modify: `docs/METRICS.md` (the `valid` appendix row at ~line 81, which currently says "Unresolved and high-stakes")

**Interfaces:**
- Consumes: Task 9's rule + evidence.

- [ ] **Step 1: Amend all three docs**, each edit prefixed with the provenance marker per `tracking-workstream-progress`:

```markdown
> **Amended (workstream bluezoo-semantics-resolution, 2026-07-XX):** <what the evidence showed; the recommended rule; what remains BlueZoo's to confirm — 1–3 lines each>
```

For `99-open-questions.md` Q18: state which sub-bullets closed empirically (flip shape, null meaning, health correlation, group-exclusion evidence, timestamp basis) and which remain (BlueZoo's intent confirmation, their own daily bucketing). For `METRICS.md:81`: replace "Unresolved" framing with "recommended rule R pending BlueZoo confirmation — see workstream findings" (keep the row, don't delete history). If any test contradicted a prior plan assumption, also log a `DISCOVERY` entry in WORK_LOG per the skill.

- [ ] **Step 2: Commit**

```bash
git add .docs/version2-plan/11-live-bluezoo-adapter.md .docs/version2-plan/99-open-questions.md docs/METRICS.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics: provenance amendments to 11b doc, Q18, METRICS.md valid row"
```

---

### Task 11: Client-outreach drafts

**Files:**
- Create: `.docs/version2-plan/working-docs/bluezoo-semantics-resolution/outreach-drafts.md`

**Interfaces:**
- Consumes: Task 9's rule and every "remaining ask" from `bluezoo-live-verification/findings.md`'s "Remaining asks" section (items 1–7).

- [ ] **Step 1: Write two drafts** (email-ready prose, no placeholders except recipient names):

**Draft A — to BlueZoo:** (1) the `valid` rule as a confirm-or-correct ("we observe X, we plan rule E — confirm?" — from Task 9, with the one-paragraph evidence summary); (2) quota accounting per sensor location (is a multi-location query charged per location?) + is the 500 GB ceiling month-scoped or persistent + any way to check remaining allowance; (3) day-cut: our Test 5 verdict on what `timestamp` is, asking them to confirm and to state which of `time_zone` (sparse) / `time_offset` (DST-varying) a consumer should trust for *their* daily aggregates; (4) `group_uv_daily.campaign_id` = UV-measurement campaign, never an advertiser campaign — confirm; (5) `sensor_visitors_per_minute` dormant since 2025 — GA, opt-in, or retired?; (6) docs bug report: every `run_query` requires a time constraint (undocumented) and the published example `select * from sensor_visitors limit 1` fails live.

**Draft B — to the retailer/PoS side:** Q3 (which PoS system, what API/export) and Q4 (product↔SKU join key), phrased with the context that these gate revenue attribution (Phase 12).

- [ ] **Step 2: Redaction pass on the drafts** (they quote evidence — ensure `⟨venue⟩` style, no key material, no operator names), then commit:

```bash
git add .docs/version2-plan/working-docs/bluezoo-semantics-resolution/outreach-drafts.md .docs/version2-plan/working-docs/bluezoo-semantics-resolution/WORK_LOG.md
git commit -m "semantics: client outreach drafts (BlueZoo + retailer)"
```

---

### Task 12: Sweep, gates, review, finish

**Files:** none new (fixes only if the sweep finds something).

- [ ] **Step 1: Credential/PII sweep over the whole branch diff**

```bash
git diff version_2...HEAD | grep -iE "accesskey|access_key.*=.{8,}|bearer" | grep -v "BLUEZOO_ACCESS_KEY" ; echo "---"
git diff version_2...HEAD > /tmp/bluezoo-semantics/branch.diff
# Manually grep branch.diff for: any operator/venue/campaign name observed during queries
# (keep the observed-names list ONLY in /tmp, never committed), plus "hermes.morpheus" context lines.
```
Expected: no key material; base URL appearances only in docs/plan contexts already public in the repo (it's in the scope doc). Any name hit → redact, amend the commit that introduced it.

- [ ] **Step 2: Test + lint gates**

```bash
make test && make lint
```
Expected: green / clean (only `scripts/` + docs changed; unit tests from Task 1 included in `make test-unit`).

- [ ] **Step 3: Demo-scenario justification** — append to WORK_LOG (checkpoint 5 position): "Demo scenario skipped by design: zero agent-visible change (no tools/prompts/routing/instructions touched; scripts/ + docs only), per bluezoo-live-verification precedent." Also confirm no `DEMO_GUIDE.md` journey is invalidated (none should be — no behavior change).

- [ ] **Step 4: Final review + finish** — dispatch `requesting-code-review` on the whole branch (most capable model), fix findings via one fix subagent if any, then `finishing-a-development-branch`: PR into `version_2` (body: link scope doc, summarize evidence + rule, state verification = make test + sweep + per-test evidence; **no AI-attribution trailer**), owner-confirmed self-merge, STATUS.md → `merged` (main checkout), WORK_LOG checkpoint 6.

---

## Self-review notes

- **Spec coverage:** scope-doc Tests 0–5 → Tasks 3–8; deliverable 1 (findings + rule) → Tasks 2/9; deliverable 2 (amendments) → Task 10; deliverable 3 (outreach) → Task 11; deliverable 4 (probe capability) → Task 1; validation checklist → Tasks 9/12. Constraints carried in Global Constraints.
- **Ordering note:** Tasks 4/5 (Tests 1/4) before Task 6 (Test 2) so flip-window knowledge can scope the join; Task 7 (Test 3) after Task 4 because it consumes Test 1's per-sensor state. Task 8 (Test 5) is independent and can run any time after Task 2.
- **Placeholders check:** `<ZONE_A>`/`<ID>` in Task 8 and the rule shape in Task 9 are data-dependent by nature (filled from prior steps' outputs at run time, per the inline-execution model) — not spec gaps. Every SQL statement is otherwise complete and byte-budgeted.
- **Type consistency:** `load_env_var`/`run_sql` signatures match between Task 1's tests and implementation; all query tasks consume Task 1's `--sql` flag.
