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
