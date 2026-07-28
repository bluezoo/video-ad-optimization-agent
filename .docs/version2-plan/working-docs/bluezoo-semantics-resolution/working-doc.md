# Workstream: bluezoo-semantics-resolution

**Branch:** `version_2_bluezoo-semantics-resolution` (off `version_2` @ cc0dfa8)
**Scope doc:** `.docs/version2-plan/bluezoo-semantics-resolution.md`
**Type:** non-numbered research workstream (precedent: `bluezoo-live-verification`). Runs before Phase 11b.

## Research findings

Every concrete claim in the scope doc was re-verified against the current branch (2026-07-27):

1. **`scripts/bluezoo_probe.py` is as described.** SELECT-only guard (`query()`, line 174), best-effort time-constraint guard (line 176), `QuotaExceeded` modeled as a distinct exception (line 95), 30-day default count window (`DEFAULT_WINDOW_DAYS`, line 68), `--full-history` opt-in. Key loaded from env or `app/.env`, never printed.
2. **`sensor_pulses` row count is genuinely unknown.** It is not in the probe's `COUNT_TABLES` (line 79) — the MO_92 scan counted only the 6 listed tables. Test 0 is necessary, exactly as the scope doc says.
3. **`sensor_pulses` schema confirmed** from `scan-mo92/scan.json`: `expected_pulse_count` INT64, `pulse_count` INT64, `timestamp` TIMESTAMP — Test 2's health ratio is computable if rows exist. Secondary corroboration columns also present: `mac_count_global`, `mac_count_local`, `rssi_cellular_avg`, `rssi_wifi_avg`.
4. **Cost caveat found (new):** `sensor_pulses` carries a 128-field `pulse_rssi_distribution` STRUCT. The probe's `select_star_bytes_per_row` estimate (208 B) badly undercounts it — the struct alone is ~1 KB/row (unknown types priced at 20 B by `row_width_bytes`). Harmless for us (all queries name columns), but the artifact's width figure for this table must not be trusted for budgeting.
5. **Test 3 needs a full-history window.** `group_sensor_history` shows **0 rows in the scan's 30-day window** — its 1,181 rows span 2021-08-02 → 2025-12-02 (findings 5.5). The mandatory time constraint must therefore span ~2021→now. Still trivially cheap: 5 narrow columns × 1,181 rows.
6. **Bounded windows are viable for Tests 1/2/4:** `sensor_visits` has 97,868 rows in the last 30 days (scan artifact) → Test 1's 17 B/row read is ~1.7 MB windowed. Full history (~5.1 M rows, ~87 MB) stays the escalation path, not the default.
7. **Amendment targets all exist:** Q18 in `.docs/version2-plan/99-open-questions.md` (with the live-verification amendment chain), the `valid` appendix row at `docs/METRICS.md:81` (says "see open question 18"), and `11-live-bluezoo-adapter.md`'s Part 5 amendment.
8. **Gap (owner action):** `BLUEZOO_ACCESS_KEY` is **not currently in `app/.env`**, and `BLUEZOO_BASE_URL` is read by the probe **only from the shell env / `--base-url` flag** — `load_access_key()` reads `app/.env` for the key alone. Owner will add both to `app/.env` directly (never chat); the probe needs a small extension to honor `BLUEZOO_BASE_URL` from `app/.env` too (covered by scope-doc deliverable 4). Owner has also noted both keys appeared in conversation historically → **rotation recommended** regardless.
9. **findings.md Part 5 facts** this builds on re-read and internally consistent: `valid` split (2.54 M false / 2.50 M true / 63 K null; 72% of counts on false; per-sensor not per-slot; `(sensor_id,timestamp)` unique), quota mechanics (per-location accounting suspicion, no remaining-allowance endpoint), day-cut still open with `time_zone` sparse.

## Implementation approach

No genuine design fork — the scope doc prescribes the five tests, their SQL shapes, and the cost discipline. Execution details:

- **Order:** Test 0 first (gates Test 2), then 1 → 4 → 3 → 5, with Test 2 whenever Test 0 confirms pulses exist. Tests 1 and 4 share a window and can share a probe session.
- **Windowing policy:** start every `sensor_visits`/`sensor_pulses` query on a bounded window (30 days, or a deliberately chosen slice per test — e.g. Test 1 needs enough history to see flips, so it may use per-sensor `min/max` over full history, which is exactly the scope doc's ~87 MB worst case but scoped to 17 B/row columns only). Widen only if the bounded answer is ambiguous, and prefer per-sensor/per-group scoping given the per-location accounting suspicion (findings 5.1).
- **Test 2 join contingency:** if Test 0 shows pulse cadence ≠ the 15-minute visit grid, bucket both sides (e.g. `timestamp_trunc(..., hour)`) instead of equi-joining, per the scope doc.
- **Probe extension (deliverable 4):** teach `scripts/bluezoo_probe.py` to read `BLUEZOO_BASE_URL` from `app/.env` (same precedence as the key: env wins), plus whatever minimal query-runner capability the tests need (likely a small `--sql`/module-level reuse rather than a new script). Tested code, unit tests included, no live calls in tests.
- **Evidence handling:** every query, its byte estimate, and its result (redacted) goes into `working-docs/bluezoo-semantics-resolution/findings.md` as it lands — same shape as the live-verification findings doc. Customer identifiers redacted at capture time (`⟨venue A⟩` style), never written to disk unredacted.
- **Deliverables** per scope doc: findings.md with a **recommended `valid` rule stated implementably for 11b**; provenance amendments to `11-live-bluezoo-adapter.md`, `99-open-questions.md` (Q18), `docs/METRICS.md:81`; client-outreach drafts (BlueZoo: valid rule, quota accounting, ceiling persistence, day-cut, campaign_id, per-minute feed status, docs bug; retailer: Q3/Q4) sharpened by the evidence; probe extension code.

## Test plan

- `make test-unit` and `make test` green throughout (probe extension gets unit tests with mocked HTTP; zero live calls in the suite — same pattern as the existing probe, which has no live-test dependency).
- `make lint` clean.
- Live evidence is the research output itself, not a test-suite artifact: each of Tests 0–5 either produces a recorded result in findings.md or is documented impossible with the reason (scope-doc validation checklist).
- **Demo scenario: skipped by design** — this workstream changes no agent-visible behavior (no tools, prompts, routing, or instructions touched; only `scripts/` + docs). Justification recorded in WORK_LOG per the `bluezoo-live-verification` precedent. If any finding turns out to demand app-code change, stop and re-scope per the scope doc's constraint.
- Pre-PR: credential/PII sweep of the whole branch diff (no keys, no customer identifiers — grep for the operator/venue names seen during queries, the key prefix, and `hermes.morpheus` URL contexts that could leak identifiers).

## Out of scope

- **Any app behavior change.** If a finding demands one, stop and re-scope — that's 11b's work.
- Implementing the `valid` exclusion rule in code (11b consumes the recommendation).
- The REST-vs-BigQuery transport decision (client's).
- **Sending** the outreach — drafts only; owner sends.
- Settling BlueZoo's *intent* for `valid` or their own daily-aggregate bucketing — explicitly what data cannot settle; the deliverable converts open questions into confirmable ones.
- Key rotation itself (owner action; recommended, not performed here).
