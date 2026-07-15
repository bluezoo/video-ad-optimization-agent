# Work Log — Workstream 01: emergency-model-currency-fix

Append-only, newest at the bottom. Owned by the `tracking-workstream-progress` skill.

## 2026-07-14 17:44 — kickoff: worktree created
Branch `version_2_model-currency-fix` created off `version_2` (e23ca66), worktree at `.claude/worktrees/version_2_model-currency-fix`. Base verified (`git merge-base HEAD version_2` == `git rev-parse version_2`). STATUS.md row set to "kickoff in progress" in main checkout. Phase doc research: done (same session) — all file:line claims in `01-emergency-model-currency-fix.md` confirmed against current code; GA replacement IDs re-verified externally (gemini-3-pro-image stable since 2026-05-28; veo-3.1-generate-001 GA since 2025-11-17, no retirement announced); two additional stale-ID doc hits found (`DEMO_GUIDE.md:439`, `DEPLOYMENT.md:465-467`); no `app/.env` exists in this checkout (smoke tests need env bootstrap); tests reference no model IDs; phase-doc open question 1 answered (gemini-3-flash-preview: deprecated on AI Studio surface 2025-12-17 but "no shutdown date announced" — no near-term cutoff, stays out of scope). Details in working-doc.md.

## 2026-07-14 17:55 — working doc approved (checkpoint 2)
Owner approved the six-dimension summary with one scope addition: media-model config values become env-overridable (`IMAGE_GENERATION_MODEL`/`VEO_MODEL` env vars, GA IDs as defaults) so preview models can be swapped in for pipeline testing; evaluation of Omni Flash / Nano Banana stays Phase 13a/13b. Also confirmed: env bootstrap on `kaggle-on-gcp` (Vertex path, location global), and updating both DEMO_GUIDE.md and DEPLOYMENT.md stale model-ID rows. See working-doc.md "Approval addendum".

## 2026-07-14 18:05 — plan approved (checkpoint 3)
Owner approved plan.md with one amendment: rename `VEO_MODEL` → `VIDEO_GEN_MODEL` (constant + env var; model-agnostic since Omni/Veo are both video-gen backends, aligns with image-side naming). Plan updated in place (Tasks 2/3 carry the rename incl. video_tools.py's six refs, CLAUDE.md:70 gotcha, and a phase-doc validation-grep provenance note). Execution: inline, trivial-phase fast path.

## 2026-07-14 18:20 — Task 1: baseline smoke vs preview IDs
Env bootstrapped: app/.env created (gitignored, verified via git check-ignore) — Vertex path, project kaggle-on-gcp, location global. Worktree venv built with python3.12 (`make install` recipe assumes bare `python`, absent on this machine — replicated manually).
Stage 1 (gemini-3-pro-image-preview): **succeeded**, 1,352,070 bytes — Vertex still tolerates this ID for now.
Stage 2 (veo-3.1-generate-preview): **failed — 404 NOT_FOUND**: "Publisher model `projects/kaggle-on-gcp/locations/global/publishers/google/models/veo-3.1-generate-preview` was not found or your project does not have access to it." The April deprecation is already biting: video generation is currently broken on the Vertex path.
Note: `make lint` fails with 174 pre-existing ruff errors across untouched files (repo-wide condition, not introduced here — candidate for Phase 1 cleanup); the new smoke script itself lints clean.

## 2026-07-14 18:35 — DISCOVERY: tests/conftest.py DB path mismatch breaks make test-unit on fresh checkouts
Assumed: `make test-unit` passes unchanged (phase doc Validation; CLAUDE.md "~4s fastest feedback loop").
Actual: on any checkout without a leftover `app/campaigns.db` (this worktree AND the main checkout today), 77/83 unit tests error with FileNotFoundError — `conftest.py:43` copies `APP_DIR / "campaigns.db"` but `_ensure_main_db_exists()` populates `app.config.DB_PATH` (project root locally). Unrelated to the model swap (reproduced before/after).
Fix applied here (blocked this phase's validation): MAIN_DB_PATH now derives from `app.config.DB_PATH`. After fix: 82 passed, 1 skipped.
Blast radius: Phase 1 doc amended (new item 8, marked already-fixed, provenance note). No other phase doc references conftest paths.

## 2026-07-14 18:36 — Task 2 complete
GA swap + env overrides + VEO_MODEL→VIDEO_GEN_MODEL rename (config.py, video_tools.py ×6, tests/unit/test_config.py 3 tests TDD red→green). Commit 24913b1. Conftest discovery fix in follow-up commit. make test-unit: 82 passed, 1 skipped.

## 2026-07-14 19:05 — owner scope addition: orchestration model to GA
Mid-implementation the owner directed swapping `MODEL` too: now `gemini-3.5-flash` (verified GA on Vertex: released 2026-05-19, retirement "2027-05-19 or later", global supported), env-overridable as `AGENT_MODEL`. Supersedes the working doc's out-of-scope line for MODEL; working doc, phase doc, DEMO_GUIDE, DEPLOYMENT, CLAUDE.md, deploy-agent skill, deploy_ae_inline.py all updated. Commit a38e1d6.

## 2026-07-14 19:10 — DISCOVERY: 3 pre-existing tests/e2e failures (test/code drift)
Assumed: `make test-e2e` passes unchanged. Actual: 3 failures — `test_video_generation_flow` (stale `model_ethnicity` kwarg), `test_chart_generation` + `test_map_visualization` (async tools called without await). Verified pre-existing: identical failures reproduced at base commit e23ca66 (temp worktree, only the conftest fix applied). Not fixed here — amended into Phase 1 doc as new item 9.

## 2026-07-14 19:12 — DISCOVERY: make test-integration silently runs nothing without google-adk[eval]
Assumed: `make test-integration` runs real evals. Actual: `AgentEvaluator.evaluate` raises a lazy ImportError ("Eval module is not installed... google-adk[eval]") which the tests' broad `except ImportError` converts to all-skipped ("google.adk.evaluation not available") — looks green, runs nothing. Fixed locally by installing the extra; documented in SETUP_INSTRUCTIONS.md Test section; Phase 1 item 7 amended (its xfail-narrowing fix must also handle this).

## 2026-07-14 19:15 — Task 4 complete: post-swap release gate PASSED
Stage 1 (gemini-3-pro-image): OK, 1,218,671 bytes. Stage 2 (veo-3.1-generate-001): OK, 1,558,711 bytes (~40s generation). Env-override path verified live (IMAGE_GENERATION_MODEL → Stage 1 OK, 1,244,082 bytes).
Suites: test-unit 82 passed/1 skipped; test-integration 5 passed (live, now on gemini-3.5-flash, with google-adk[eval] installed); test-e2e 22 passed/3 pre-existing failures (see DISCOVERY above, owned by Phase 1 item 9).

## 2026-07-14 19:45 — demo scenario verification: PASS (checkpoint 5)
Scenario F1 (docs/demo-scenarios/fashion.md), 2/2 scenes PASS via demo-scenario-verifier subagent against this worktree's adk web on :8501.
Scene 1: coordinator routed via transfer_to_agent → campaign_agent, `list_campaigns` fired, target campaign present. (total_count was 14 not 4 — 10 leftover draft "Test Store" campaigns from prior test runs in the local DB; stale-DB state, not a code defect.)
Scene 2: media_agent → `generate_video_with_variation` (two-stage), server log shows gemini-3-pro-image generateContent 200 OK then veo-3.1-generate-001 predictLongRunning 200 OK (97s total); produced sage-satin-camisole-071426-elegant-studio-sage-camisole.mp4, status "generated", HITL pending review; zero errors in full session JSON.
Evidence: working-docs/01-emergency-model-currency-fix/evidence/ (trace + chat screenshots, session events JSON, server debug lines).
Verifier also observed the agent NARRATING "Gemini 2.0 Flash" in chat text while actually calling gemini-3-pro-image — that's the known stale MEDIA_AGENT_INSTRUCTION text at agent.py:200, already owned by Phase 1 item 6; no action here.

## 2026-07-14 20:00 — branch code review: READY TO MERGE
Whole-branch review (general-purpose reviewer, version_2..HEAD): zero Critical/Important issues, 4 Minor. Reviewer independently reproduced test results and validation greps. Minor fixes applied same session: test_config teardown now uses monkeypatch.undo() before reload (env-sync correctness); smoke script's pre-rename getattr shim removed (dead post-rename); scenario F1's campaign-count assertion softened (tolerate leftover local campaigns); phase-doc validation boxes ticked with evidence pointer (last box deliberately left open — closes with Phase 1's share of the Gemini 2.0 cleanup). Re-verified after fixes: unit 82 passed/1 skipped, ruff clean, Stage-1 smoke OK.
