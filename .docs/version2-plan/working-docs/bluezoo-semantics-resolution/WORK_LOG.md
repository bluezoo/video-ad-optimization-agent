# WORK_LOG — bluezoo-semantics-resolution

Non-numbered research workstream (precedent: `bluezoo-live-verification`). Scope doc: `.docs/version2-plan/bluezoo-semantics-resolution.md`. Branch `version_2_bluezoo-semantics-resolution` off `version_2`.

## 2026-07-27 — checkpoint 1: kickoff — worktree created
Worktree at `.claude/worktrees/version_2_bluezoo-semantics-resolution`, branch `version_2_bluezoo-semantics-resolution`, base verified == `version_2` (cc0dfa8). Phase-doc research pending (this entry will be amended when Step 2 completes).

Owner directives at kickoff (verbatim intent, from the kickoff message):
- Read-only: `list_tables`, `desc_table`, SELECT only.
- MO_92 carries a real hospitality operator's data — redact all customer identifiers, never commit a key.
- Run kickoff and get owner approval on the working doc **before any plan or queries**.
- `app/.env` needs `BLUEZOO_ACCESS_KEY` (Morpheus) + `BLUEZOO_BASE_URL=https://hermes.morpheus.bluezoo.io/v2/dwh` — owner adds directly to the file, never via chat. Both keys have been in conversation before → **rotation still worth doing** (owner note).
- First check once queries are allowed: Test 0 — does `sensor_pulses` have rows on MO_92? (Scan covered only 6/19 tables; Test 2 dies if empty.)

## 2026-07-27 — checkpoint 1 amendment: phase-doc research done
Scope-doc claims re-verified against current branch: probe guards/quota model/window defaults confirmed (scripts/bluezoo_probe.py); `sensor_pulses` NOT in COUNT_TABLES → row count unknown, Test 0 stands; `sensor_pulses` schema confirmed in scan-mo92 (`expected_pulse_count`/`pulse_count`/`timestamp` + mac/rssi corroboration cols). New findings: (a) `pulse_rssi_distribution` 128-field STRUCT makes the probe's width estimate for `sensor_pulses` (208 B/row) a bad undercount (~1 KB/row actual) — name columns, don't trust that figure; (b) `group_sensor_history` has 0 rows in a 30-day window (revisions end 2025-12) → Test 3 must span full history (still ~trivial bytes); (c) probe reads `BLUEZOO_ACCESS_KEY` from app/.env but `BLUEZOO_BASE_URL` only from shell env/flag → small probe extension needed (scope deliverable 4); (d) `BLUEZOO_ACCESS_KEY` not yet present in app/.env — owner to add directly. Working doc drafted; awaiting owner approval (checkpoint 2 gate). No queries run.

## 2026-07-27 — checkpoint 2: working doc approved
Owner: "lgtm" to the six-dimension restatement (outcome/user/why-now/success/constraints/out-of-scope as stated in working-doc.md). Blocker noted at approval time: BLUEZOO_ACCESS_KEY + BLUEZOO_BASE_URL still to be added to app/.env by owner before live queries. Proceeding to writing-plans.

## 2026-07-27 — checkpoint 3: plan approved
Owner: "approve" — 12-task plan (plan.md), INCLUDING the execution-mode exception: Task 1 via subagent-driven-development; Tasks 2–11 (live research vs metered customer-confidential MO_92, result-gated query shapes) run inline in the controlling session; Task 12 via requesting-code-review + finishing-a-development-branch. Live tasks stop-and-wait if BLUEZOO_ACCESS_KEY/BLUEZOO_BASE_URL absent from app/.env.

## 2026-07-27 — Task 1 complete (mirrors .superpowers/sdd/progress.md)
Probe extension: load_env_var (BLUEZOO_BASE_URL now read from app/.env, env wins) + guarded --sql runner. commits 365cf79..def074f, 31/31 probe tests, make test-unit 350 pass, lint clean, review approved (spec ✅, zero findings).

## 2026-07-27 — Task 2 (preflight) + Task 3 (Test 0) complete
Preflight: creds present, list_tables = 19 (sensor_pulses entitled, group_dwell absent — matches scan). Test 0: sensor_pulses POPULATED — 101,136 rows/30d, 34 sensors, cadence exactly 96/sensor/day (15-min grid) → Test 2 viable, equi-join on (sensor_id,timestamp). Caveat: pulses cover 34 currently-reporting sensors vs 101 historical. ~2 MB scanned.
