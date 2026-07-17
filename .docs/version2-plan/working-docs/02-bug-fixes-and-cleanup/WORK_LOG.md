# Work Log — Workstream 02: bug-fixes-and-cleanup

Append-only, newest at the bottom. Owned by the `tracking-workstream-progress` skill.

## 2026-07-14 19:29 — kickoff: worktree created
Branch `version_2_bug-fixes-and-cleanup` created off `version_2` (7d3c866, post-Phase-0 merge), worktree at `.claude/worktrees/version_2_bug-fixes-and-cleanup`. Base verified. STATUS.md row set to "kickoff in progress" in main checkout. Phase doc research: pending.

**Amended 2026-07-14 — phase doc research done.** All 9 items re-verified against current code; every claim holds. Highlights beyond the phase doc:
- Item 1: daily row dicts lack a raw `revenue` key (only date/impressions/dwell_time/circulation/revenue_per_impression), though raw revenue is computed inside the loop. Both bad defaults confirmed (metrics_tools.py `generate_metrics_visualization`, maps_tools.py `generate_map_visualization`).
- Item 2: `get_campaign_metrics` returns `summary=None` with `status="success"` whenever no rows have impressions (metrics_tools.py ~246) — the debug f-string `summary['total_impressions']` before the guard is a live `TypeError: 'NoneType' object is not subscriptable`.
- Item 5: `CAMPAIGN_CATEGORIES` (config.py:89) is **dead config** — zero consumers in app/ or tests/. DB CHECK (db.py:70) has 5 values incl. `holiday`; config has 4. `create_campaign` (campaign_tools.py ~66-73) never touches either — hardcoded product→campaign mapping with silent `"essentials"` fallback.
- Item 6: campaign 4 is `sage-satin-camisole` at The Grove (mock_data.py:63-64); stale texts confirmed at agent.py:152, 539 (Emerald Satin), agent.py:310 (90 days; mock data generates 30), agent.py:200 + video_tools.py:18 (Gemini 2.0 Flash Exp). README:66 BigQuery correction **already recorded** in SETUP_INSTRUCTIONS.md:81 — that bullet needs no new work.
- Item 7: identical broad `except ImportError: pytest.skip` + `except Exception: pytest.xfail` in all 6 integration tests (test_agents.py:65-69 et al.).
- Item 9: all 3 e2e failures reproduce on this branch (3 failed, 22 passed, 1 skipped). Root causes: `generate_video_from_product` is `async def` taking `variation: Optional[dict]` (test passes stale `model_ethnicity=`/`setting=`/etc. kwargs, no `product_id`, no await); chart/map tools are `async def` called sync → "coroutine is not iterable". Chart test also passes invalid `metric="rpi"`. pytest is `asyncio_mode = auto`, so async test fns just work. All 3 are `slow`-marked but `make test-e2e` runs without deselecting slow, so they fail on every e2e run.
- Worktree env set up: `app/.env` copied from main checkout, `.venv` built with python3.12, `google-adk[eval]` installed.

## 2026-07-14 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement: 7 fixes (metric defaults, null-deref guard, legacy-table repoint, category alignment, stale texts, loud integration import failure, 3 e2e repairs), e2e suite to fully green, README/DEMO_GUIDE untouched, weekly-aggregation + raw-revenue deferred to Phase 3. Design choice confirmed: default → revenue_per_impression only, no raw-revenue metric key this phase. Next: writing-plans.

## 2026-07-14 — DISCOVERY: 5 vacuous async unit tests (never awaited)
Assumed: unit suite meaningfully covers the visualization tools. Actual: `tests/unit/test_metrics_tools.py` (2 tests) and `tests/unit/test_maps_tools.py` (3 tests) call the `async def` visualization tools without `await` — they assert on a coroutine object (always truthy), execute nothing, and emit `RuntimeWarning: coroutine ... was never awaited` on every unit run. Same root cause as the 3 e2e failures (phase item 9): tools went async, tests didn't follow — but these 5 "pass" silently instead of failing.
Blast radius: this workstream only — added as plan Task 7 (de-vacuate: await + deterministic raising-mock asserting the tools' graceful error path). No downstream phase doc claims depend on these tests; no amendments needed elsewhere.

## 2026-07-14 — plan approved (checkpoint 3)
Owner approved the 9-task implementation plan (plan.md), including Task 7 scope addition (de-vacuate 5 async unit tests). Execution via subagent-driven-development, fresh implementer + reviewer per task.

## 2026-07-14 — Task 1 complete (mirrors .superpowers/sdd/progress.md)
Fix invalid metric defaults → revenue_per_impression in both visualization tools. Commits 1684501..2062f66, review clean (spec ✅, quality approved, no findings).

## 2026-07-14 — Task 2 complete (mirrors .superpowers/sdd/progress.md)
No-data guard moved above summary deref (covers summary=None on status="success"); weekly ratio-sum bug flag comment added for Phase 3. Commits 2062f66..b7f9a34, review clean.

## 2026-07-14 — Task 3 complete (mirrors .superpowers/sdd/progress.md)
get_campaign_locations repointed to campaign_videos/video_metrics (activated-only, JOIN-condition filter so zero-video campaigns still appear). Commits b7f9a34..a08d3f3, review clean.

## 2026-07-14 — Task 4 complete (mirrors .superpowers/sdd/progress.md)
CAMPAIGN_CATEGORIES aligned to DB CHECK (+holiday, source-of-truth comment); create_campaign mapping/fallback documented; parity test added. Commits a08d3f3..8a7be90, review clean (2 minor observations logged for final review).

## 2026-07-14 — Task 5 complete (mirrors .superpowers/sdd/progress.md)
Stale prompt/docstring texts fixed (Sage Satin Camisole, 30 days, config-var model references); grep for stale strings clean. Commits 8a7be90..91b05d5, review clean.

## 2026-07-14 — Task 6 complete (mirrors .superpowers/sdd/progress.md)
Missing google-adk[eval] now raises actionable ImportError at module import; 6 per-test ImportError-skip arms removed; live integration run 5 passed / 0 skipped. Commits 91b05d5..2054c3b, review clean.

## 2026-07-14 — Task 7 complete (mirrors .superpowers/sdd/progress.md)
5 vacuous async unit tests de-vacuated (await + raising-mock deterministic error path); -W error::RuntimeWarning proves zero unawaited coroutines. Commits 2054c3b..ba6c2a3, review clean.

## 2026-07-14 — DISCOVERY: DB test isolation is broken repo-wide (import-time DB_PATH binding)
Assumed (CLAUDE.md gotcha + tests/conftest.py design): tests run against a COPY of campaigns.db. Actual: app/database/db.py:19 does `from ..config import DB_PATH`, binding the value at import — conftest's `patch("app.config.DB_PATH", …)` never reaches `get_db_cursor`, so ALL test reads/writes hit the real campaigns.db. Evidence: worktree campaigns.db grew to 138 campaigns (69 with NULL product_id — Task 4's parity INSERTs leak 5 rows on every PostToolUse hook run; older "Test Store"/"New Test Store" rows show the leak predates this workstream). This is what broke test_campaign_product_consistency (the "4th e2e failure" in Task 8).
Blast radius: fix db.py to late-bind (`config.DB_PATH` at connect time) in this workstream — it's a bug of exactly this phase's class and our own new tests are actively polluting real DBs without it; reset polluted campaigns.db; note in SETUP_INSTRUCTIONS that pre-existing checkouts should `make reset-db` once. CLAUDE.md's gotcha line becomes true again (no edit needed). Owner will see this flagged at final review + PR.

## 2026-07-14 — DISCOVERY: pytest pins GOOGLE_CLOUD_PROJECT=test-project — e2e slow tests cannot make real API calls
Assumed (plan Task 8 steps 5-6): the slow e2e tests would run real Gemini/Veo generation. Actual: tests/conftest.py:60 deliberately sets GOOGLE_CLOUD_PROJECT="test-project" so pytest can never spend real API quota; the "live" runs completed in 1.4-3s because the tools returned their graceful 403-error dicts, which the tests' contract asserts (status in success/error) accept. This is the honest maximum for pytest under the harness — the REAL-generation release gate is scripts/smoke_media_models.py (proved in workstream 01) plus the demo scenarios via adk web (real env), which Task 9 runs.
Blast radius: plan.md Task 8 steps 5-6 expectations amended by this entry; no downstream phase docs claim pytest does real generation.

## 2026-07-14 — Task 8 complete (mirrors .superpowers/sdd/progress.md)
3 e2e tests repaired (async/await, current signatures, real return-shape asserts) + None-guard on product_id consistency test (schema-legit: ON DELETE SET NULL) + fix round: DB test isolation repaired repo-wide (db.py late-binds config.DB_PATH; polluted campaigns.db reset; leak-proof verified across repeated runs; one genuinely-broken review_tools assertion fixed; SETUP_INSTRUCTIONS reset-db note). Full e2e: 25 passed, 1 skipped, 0 failed (was 3 failed). Commits ba6c2a3..51cd452, re-review clean.

## 2026-07-14 — Task 9 complete + demo-scenario verification: PASS (checkpoint 5)
Scenario F2 added to docs/demo-scenarios/fashion.md; touched files lint-cleaned (114→0 ruff errors); suites green (unit 88 passed/1 skipped; e2e 25 passed/1 skipped/0 failed).
Demo verification via demo-scenario-verifier, sequential, worktree server on :8501:
- **F1: 2/2 PASS.** Scene 1 list_campaigns → exactly 4 seeded campaigns (clean DB confirms isolation fix). Scene 2 real two-stage generation: generate_video_with_variation(product 21, campaign 4, studio/elegant) → sage-satin-camisole-071426-elegant_studio_camisole.mp4, Stage 1 image 1.3MB + Stage 2 Veo 60s op, 122s total, artifact rendered. This is the real-generation release gate (pytest can't do it — see test-project DISCOVERY).
- **F2: 2/2 PASS.** F2.1 generate_metrics_visualization(campaign_id=1, trendline, metric=revenue_per_impression) → success, chart artifact rendered, no "Invalid metric". F2.2 create_campaign(Test Mall/Austin) then guard verified: clean "No metrics data available… activate videos first" error, no traceback. Scenario doc amended to two-turn script (agent legitimately short-circuits via get_campaign_metrics on turn 1 — observed 2/2).
Evidence: working-docs/02-bug-fixes-and-cleanup/evidence/f1-*.png, f1-scene2-server-log-two-stage.log, f2-*.png.

## 2026-07-14 — final whole-branch review: READY TO MERGE
0 Critical, 0 Important, 4 Minor. Reviewer independently re-ran suites and leak-proof DB checks. Minors 1/2/4 fixed (stale markers dropped, app/.adk/ gitignored, precondition assert de-vacuated) + Phase 3 doc amended re: get_campaign_metrics summary=None contract (commit dd7f887). Minor 3 (hardcoded model names in deeper docstrings/prints, currently accurate) deferred as future cleanup. Two carried per-task minors adjudicated acceptable (parity test happy-path-only; phrasing divergence plan-specified).

## 2026-07-14 — finish: PR open (checkpoint 6, pending merge)
PR #2 into version_2: https://github.com/bluezoo/video-ad-optimization-agent/pull/2 — owner chose to hold it open for review. Worktree and branch preserved for PR iteration. On merge: run finishing-a-development-branch Path A tail (merge → ExitWorktree remove → STATUS.md "merged" → final WORK_LOG line).

## 2026-07-16 — finish: MERGED (checkpoint 6 final)
PR #2 merged into version_2 (merge commit e0a0a52) on owner instruction. Worktree and local/remote branch removed. STATUS.md row → merged.
