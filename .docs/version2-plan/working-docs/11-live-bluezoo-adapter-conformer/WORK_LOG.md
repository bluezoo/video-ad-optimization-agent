# WORK_LOG — 11b live-bluezoo-adapter (conformer)

Phase 11b, doc `11-live-bluezoo-adapter.md`. Branch `version_2_live-bluezoo-adapter-conformer` off `version_2` (23b0dfe).

## 2026-07-27 — checkpoint 1: kickoff — worktree created
Worktree `.claude/worktrees/version_2_live-bluezoo-adapter-conformer`, base verified == version_2. Research pending (this entry amended when Step 2 completes).

Owner directives at kickoff (binding):
- Honour the three pre-kickoff scoping decisions at the foot of 11-*.md — do NOT reopen: (1) REST-first behind the 11a seam (OUR assumption — surface in working doc, get explicit yes); (2) ONE class implementing ONE method, no registry/plugin framework/second abstraction — growing layers = stop and re-scope; (3) CachedBlueZooAudienceDataSource OPTIONAL, designated trim — if dropped, say so and amend Exit criteria.
- Rule R (WHERE valid, exclusion logged) is a recommendation NOT confirmed by BlueZoo — explicit, logged, CONFIGURABLE policy, never baked in.
- Read-only against BlueZoo, no writes ever. MO_92 = real customer data: redact identifiers, never commit a key, sweep branch pre-PR.
- This workstream CHANGES agent-visible behavior — demo-scenario verification + DEMO_GUIDE.md journeys are MANDATORY before PR (unlike the two research predecessors; do not cite their skip precedent).
- make test stays network-free (350 tests / ~32s protected); live conformer tests go in the live tier (make test-live) so test runs never bill customer quota.
- Credentials already in app/.env (Morpheus/MO_92).

## 2026-07-27 — checkpoint 1 amendment: research done
Seam verified as scoping amendment describes: app/audience = 143 lines/3 files; datasource.py 27 lines, ONE abstract method get_visit_intervals(screen_ids, date_from, date_to) -> list[BlueZooVisitInterval]; factory has _BUILTIN_SOURCES dict with the AppMode.CONNECTED slot explicitly reserved for 11b (fail-closed RuntimeError until then); one consumer (demo_data/attribution.py:170 join). KEY RESEARCH FINDING: the DTO's six occupancy fields (min/max/avg visitors_inner/outer — the sensor_visitors drift, findings Part 3) have ZERO consumers anywhere; join reads only incoming_inner_count + outgoing_outer_count; float→int policy already explicit at attribution.py:209 int(round()). So the "two queries + client-side join" the drift note assumed is avoidable: make the six fields optional (None) and query sensor_visits ONLY — half the scan cost, no second query, honest nulls instead of fake zeros. Also verified: google-adk floor 1.21.0 (SecretManagerClient needs 1.29.0 — step 6 decision to surface); live tier fixtures reusable (tests/live/conftest.py re-registers tests/integration env fixtures); probe's BlueZooProbe/QuotaExceeded pattern is scripts/-side (not importable from app/ — conformer gets its own thin HTTP layer, same guards).

## 2026-07-27 — DISCOVERY: the phase doc's "two queries + client-side join" premise is wrong
Assumed (11-live-bluezoo-adapter.md, live-verification drift note): a conformer populating today's DTO must query both sensor_visits and sensor_visitors and join client-side on (sensor_id, timestamp).
Actual: the six occupancy fields (minimum_/maximum_/average_visitors_inner/outer) have ZERO consumers — writers only (app/demo_data/seed.py:155-159) plus one presence-assertion in test_demo_seed.py; the attribution join reads only incoming_inner_count + outgoing_outer_count. Owner verified independently and confirmed. The second query would double metered scan cost to populate values nothing reads.
Resolution (approved): six fields become `float | None = None` (demo still populates; connected rows carry None, divergence documented IN THE MODEL per owner condition); live conformer queries sensor_visits only. Circulation safe — demo derivation uses outgoing_outer_count (sensor_visits, live-populated).
Blast radius amended with provenance: 11-live-bluezoo-adapter.md (drift note), docs/METRICS.md (circulation entry), 99-open-questions.md (Q5).

## 2026-07-27 — checkpoint 2: working doc approved (with conditions)
Owner approved the six-dimension restatement and all three flagged decisions:
1. REST-first — confirmed; recorded as OUR assumption, not client instruction; BigQuery later = second class behind same one-method interface.
2. Drop CachedBlueZooAudienceDataSource — confirmed; redacted real MO_92 response as fast-tier fixture replaces it ("real-payload validation in the fast tier, which the cached provider never would"); Exit criteria amended with provenance, not left silently unmet.
3. Secrets: app/.env + documented deploy-time injection — confirmed; GSM/ADK SDK stays Phase 13 (already Tier B there, not a launch blocker). CONDITION: Phase 13's amendment must require secrets to hold a {base_url, access_key} PAIR per tenant, not a lone key (separating them turns "wrong host" into a support ticket reading "auth is broken"); SETUP_INSTRUCTIONS must document the pair explicitly with a CONCRETE `gcloud run deploy --set-secrets` line, not prose.
Two conditions on the DTO change (owner-added): (a) the demo-vs-connected divergence documented in the model itself (field comments/docstring: demo-populated, None in connected mode, because populating costs a second table scan for values nothing reads); (b) DISCOVERY protocol run — done, see entry above.
Reminder restated: demo-scenario verification + DEMO_GUIDE.md journeys are mandatory.

## 2026-07-27 — checkpoint 3: plan approved (with amendments)
Owner approved the 11-task plan ("Live cost is fine, proceed") with two plan amendments + one property to preserve, all folded in before execution:
1. Condition (b) DISCOVERY protocol: ALREADY EXECUTED at working-doc approval (commit ffdfb43 — WORK_LOG DISCOVERY entry + provenance amendments in 11-*.md drift note + Exit criteria, METRICS.md circulation, Q5). Added Task 11 Step 1b verifying all amendments are in the branch diff pre-PR, per owner's "add it to the task list explicitly."
2. BLUEZOO_SENSOR_MAP sensors chosen from EVIDENCE (new Task 6 Step 0): MO_92 recent grid coverage ~34%, 19 live sensors valid=false — select top valid-row producers over the last 7 days via a group-by query (~20 KB), record ids/counts/rationale in the fixture provenance note; Task 7 + Task 9 consume the verified ids.
3. Singleton must not cache construction failure (owner-named property): new factory test test_construction_failure_is_not_cached — failed connected construction, then fixed env, succeeds WITHOUT reset.
Plan: working-docs/11-live-bluezoo-adapter-conformer/plan.md. Execution: subagent-driven-development.

## 2026-07-27 — Task 3 complete (mirrors .superpowers/sdd/progress.md)
live_bluezoo foundations (typed errors, sensor map, guarded SQL builder, coercers). commit 06be2ad, review clean, 19 helper tests. Minor (no action): _TIME_CONSTRAINT_COLUMNS substring redundancy — inherited verbatim from the probe's proven constant.

## 2026-07-27 — Task 4 complete (mirrors .superpowers/sdd/progress.md)
Transport: _classify_http_error, fail-closed constructor, _call (sole networked method), _query single-retry wrapper. commit f8176db, review clean, 388 unit tests green.

## 2026-07-27 — Task 5 complete (mirrors .superpowers/sdd/progress.md)
get_visit_intervals + _to_interval; AppMode.CONNECTED registered; live source passes the 11a contract battery (stubbed transport); TestConnectedFailsClosed rewritten (fail-closed now at construction, naming missing config; construction failure NOT cached by singleton — owner property tested). commit f0a31bb, review clean, 405 unit tests green. Two disclosed deviations adjudicated acceptable by reviewer: battery slot-grain override (48→8 stamps, keeps 15-min delta property — 48 was a synthetic-day artifact) and rule-scoped noqa B017.

## 2026-07-28 — Task 6 complete (mirrors .superpowers/sdd/progress.md)
Real MO_92 payload fixture (192 rows, seven named columns, sensors 77+80 chosen from evidence — top valid-row producers, n=672 each over 7 days) + provenance note + network-free replay test. commit b402247, review clean; controller independently re-verified redaction (only timestamp string-valued). Serialization verified: timestamp ISO+ms+offset, valid native bool, counts native float — no coercer fixes needed. NOTE for Tasks 7/9: verified sensors are 77/80, NOT the plan's 87/433 placeholders. Also: 77/80 show FULL grid coverage (96/day), so scene-2 join has dense data.

## 2026-07-28 — Task 7 complete (mirrors .superpowers/sdd/progress.md)
Live-tier MO_92 test (sensors 77/80, yesterday-UTC window, valid-only + include-all superset): 2/2 PASS against real MO_92 (~25 KB scanned). Fast-tier non-collection independently re-verified by reviewer. commit 4b539a4, review clean. Minor noted for Task 8: SETUP_INSTRUCTIONS live-tier section doesn't yet mention the BlueZoo test — Task 8 adds it.

## 2026-07-28 — Task 8 complete (mirrors .superpowers/sdd/progress.md)
SETUP_INSTRUCTIONS connected-mode section: env table, {base_url, access_key} pair rule, concrete gcloud secrets/deploy block (owner condition), ops notes, watchlist line (sensors 77/80). commit 4c41710, review clean — reviewer independently re-verified every claim against code. Minor items for final review triage: watchlist addendum formatting (paragraph vs bullet); pre-existing probe-section wording "BLUEZOO_BASE_URL optional, defaults to Apollo" reads oddly next to the new no-default rule (predates this task).

## 2026-07-28 — Task 9 complete (mirrors .superpowers/sdd/progress.md)
connected-bluezoo scenario doc (3 scenes, map 101:77,102:80,103:89 from evidence) + DEMO_GUIDE Workstream 11b journeys. commits 0f534f2 + c4fbc50 + 246644f, review approved after two fixes. DISCOVERY-adjacent plan correction: the plan's "prune nothing" claim was wrong — Journeys 11a.2 and 11a.3 asserted the pre-11b connected RuntimeError and were both updated to the real BlueZooConfigError fail-closed behavior (CLAUDE.md's prune-invalidated-journeys rule governs). Reviewer independently verified error/log fragments against code, sensor provenance, make dev env shape, and the F3→F6 substitution.

## 2026-07-28 — checkpoint: Task 10 verification starting
STATUS → verify in progress (main checkout). Dispatch 1: F2+F3 fashion regression (demo mode). Dispatch 2: connected-bluezoo scenes 1-3. Sequential, port 8501.

## 2026-07-28 — DISCOVERY: misconfigured connected mode fails at STARTUP, and every connected startup scans BlueZoo
Assumed (Scene 1 as originally written, and the plan's Task 9): connected-mode fail-closed surfaces at the first tool call, visible in the adk web trace.
Actual (verified live, Task 10): `app/agent.py:117-118` runs `init_database()` + `seed_demo_data()` at module import; seeding derives metrics through `get_audience_datasource()`, so with `APP_MODE=connected` and missing/invalid BlueZoo config the process dies with `BlueZooConfigError` BEFORE adk web binds :8501 — the error surface is the startup log, not a tool response. Two corollaries:
1. ADK auto-loads `app/.env`, so demonstrating "missing vars" requires explicit empty overrides (`BLUEZOO_BASE_URL= BLUEZOO_ACCESS_KEY=` — empty fails the constructor's `.strip()` check).
2. `mock_data.py` "Step 4" regenerates active-campaign metrics unconditionally on EVERY `populate_mock_data()` call (confirmed at mock_data.py:316, outside the `campaign_count == 0` branch) — so connected mode scans BlueZoo (read-only, a few hundred KB) on every process (re)start, not just first boot. Flagged for Phase 12/13 awareness (deploy-time restarts have a small recurring metered cost).
Blast radius (all amended in this branch): connected-bluezoo.md Scene 1 rewritten to the startup surface (40c713e); DEMO_GUIDE 11b journey + 11a.2/11a.3 aligned (40c713e); SETUP_INSTRUCTIONS gained two ops notes — startup fail-fast (40c713e) and per-restart scan cost (9cdf73e, corrected from "fresh-DB only" per review); Scene 1 vestigial setup-video clauses pruned (9cdf73e).

## 2026-07-28 — checkpoint 5: demo-scenario verification PASS (all scenarios)
Fashion regression (demo mode, F2+F3): 4/4 PASS — demo-mode behavior byte-identical with live credentials present in app/.env (zero BlueZoo mentions in logs; credentials proven inert in demo mode). Evidence: .superpowers/sdd/verify-evidence-fashion/.
connected-bluezoo (3 scenes): 3/3 PASS. Scene 1: startup fail-closed (BlueZooConfigError in startup log, port 8501 never binds, DB unchanged). Scene 2: `bluezoo live read: policy=valid-only sensors=[77, 80, 89] window=2026-07-02..2026-07-31 rows=7560`; connected impressions clearly differ from demo baseline (69,690/71,269/62,660 vs 47,430/47,456/42,298). Scene 3: `policy=include-all … rows=7572` — positive row delta proves the `and valid` clause dropped. Evidence: .superpowers/sdd/verify-evidence-connected/.
Verifier note: chrome-devtools screenshots couldn't write to disk (workspace-roots rejection) — textual transcripts in the evidence dirs are the durable record. Scene-1 doc drift found during verification handled per the DISCOVERY entry above (fix commits 40c713e + 9cdf73e, reviewed).

## 2026-07-28 — Tasks 10+11 complete (mirrors .superpowers/sdd/progress.md)
Task 10: verification PASS (checkpoint 5 above); Scene-1 doc-drift fixes 40c713e + 9cdf73e reviewed and approved.
Task 11: pre-PR sweep CLEAN — credential/UUID grep over `git diff version_2...HEAD` matched only benign env-var-name text; no app/.env or scan artifacts in diff; fixture re-verified (192 rows, exactly 7 columns, only timestamp string-valued). Step 1b: all 4 DISCOVERY amendments in branch diff (grep count 3 + 1 with the `, owner-approved` marker variant the plan's pattern missed). Gates: make lint clean, make test green (fast tier, zero network). Residual worktree campaigns.db reset via make reset-db.

## 2026-07-28 — checkpoint 6: PR open
Final whole-branch review: "Ready to merge" after one Important doc fix (dangling Scene-1 INSERT pointers, fixed in 517b48a and re-verified end-to-end). Known Minors triaged note-for-later (read-phase retry classification → next transport-touching workstream; probe-section wording pre-dates branch; pytest.ini claim was itself mistaken — repo genuinely uses pytest.ini; _TIME_CONSTRAINT_COLUMNS redundancy kept deliberately probe-identical).
PR #18 into version_2: https://github.com/bluezoo/video-ad-optimization-agent/pull/18 — body links phase doc, summarizes, states verification evidence, and flags the provenance note's 15-sensor enumeration for explicit owner sign-off. Awaiting owner confirmation to self-merge.
