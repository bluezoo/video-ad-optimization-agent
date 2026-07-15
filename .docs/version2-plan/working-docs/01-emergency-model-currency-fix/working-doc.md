# Workstream 01: emergency-model-currency-fix

**Branch:** version_2_model-currency-fix
**Phase doc:** .docs/version2-plan/01-emergency-model-currency-fix.md

## Research findings

All of the phase doc's concrete claims were re-verified against the current code (2026-07-14, branch base `e23ca66`):

**Confirmed as written:**

- `app/config.py:27-28` still holds the two stale preview IDs exactly as cited: `IMAGE_GENERATION = "gemini-3-pro-image-preview"`, `VEO_MODEL = "veo-3.1-generate-preview"`.
- `app/tools/video_tools.py:966` — stale `veo-3.1-generate-preview` inside a comment, confirmed.
- `app/tools/video_tools.py:218` — stale "Gemini 2.0 Flash Exp" comment at the Stage-1 call site, confirmed (Phase 0 scope). The other two stale "Gemini 2.0" texts (`video_tools.py:18` module docstring, `agent.py:200` instruction) confirmed present and remain Phase 1's, per the phase doc.
- Drop-in swap claim confirmed: every call site reads the model ID from config — `video_tools.py:237,299,581,960` plus two consumers the phase doc didn't enumerate, `maps_tools.py:1279` and `metrics_tools.py:981` (chart/map image generation also uses `IMAGE_GENERATION`, so the swap covers those too; no code change needed there).
- `README.md` and `app/agent_engine_app.py` contain no hardcoded model IDs (README's "Veo3" mentions are prose; README stays untouched per repo policy).
- `tests/` contains zero references to either model ID or to `IMAGE_GENERATION`/`VEO_MODEL` — the swap cannot break test mocks/assertions.

**External re-verification of model status (phase doc asked for this at implementation time):**

- `gemini-3-pro-image` — confirmed stable on Vertex: released 2026-05-28, "available for at least 12 months after release" (docs.cloud.google.com model-versions page).
- `veo-3.1-generate-001` — confirmed GA on Vertex: released 2025-11-17, "no retirement date announced".
- `gemini-3-pro-image-preview` — deprecation confirmed; the AI Studio surface shutdown (2026-06-25) has already passed. The exact Vertex-side retirement date (phase doc said "reported 2026-07-17, re-verify") still could not be pinned to a primary source — but this doesn't change the action: the swap is overdue regardless.
- **Phase-doc open question 1 answered:** `MODEL = "gemini-3-flash-preview"` (orchestration model) shows "deprecated 2025-12-17, **no shutdown date announced**" on Google's deprecations page (successor: `gemini-3.5-flash`). No near-term cutoff → correctly out of scope for Phase 0. The phase doc will be amended with this finding (provenance-marked) as part of this branch.

**New findings (not in the phase doc):**

1. **Two more stale-ID doc hits:** `DEMO_GUIDE.md:439` (`veo-3.1-generate-preview`) and `DEPLOYMENT.md:465-467` (both preview IDs). The phase doc's own grep (Step 3) surfaces them and instructs fixing doc hits. Proposal: update both. Caveat flagged for approval: CLAUDE.md says DEMO_GUIDE.md "stays fashion-specific and untouched," but that rule is about not de-fashioning it in demo-scenario work — a stale model-ID table row correction is in the spirit of Phase 0's Step 3. (~80% confident this is fine; explicitly confirming below.)
2. **No `app/.env` exists** in the main checkout or worktree, and no `GOOGLE_*` vars are exported in the shell. The smoke tests (phase Steps 1 and 4) need environment bootstrap. gcloud is authenticated with ADC present; active project is `kaggle-on-gcp`, which matches `DEFAULT_GCS_BUCKET = "kaggle-on-gcp-ad-campaign-assets"` in config.py. Proposal: create `app/.env` (gitignored) with `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT=kaggle-on-gcp`, `GOOGLE_CLOUD_LOCATION=global`, `GCS_BUCKET=kaggle-on-gcp-ad-campaign-assets`. (~85% confident this is the intended demo environment; confirming below.)
3. **`docs/demo-scenarios/` does not exist yet** — this is the first workstream to reach the verify step, so it creates the first scenario file (see Test plan).

## Implementation approach

Mechanical, like-for-like swap (Step 3 of `starting-a-workstream` skipped — no genuine design choice):

1. **Baseline smoke test (before changing anything):** with the environment bootstrapped (finding 2), run one real Stage 1 (`generate_scene_image()`) and one real Stage 2 (`animate_scene_with_veo()`) call against the *current* preview IDs and record succeed/fail. This documents whether the deprecation is already biting on the Vertex path.
2. Edit `app/config.py:27-28` to `IMAGE_GENERATION = "gemini-3-pro-image"` and `VEO_MODEL = "veo-3.1-generate-001"`.
3. Fix the confirmed stale references: `video_tools.py:966` comment (preview ID), `video_tools.py:218` comment ("Gemini 2.0 Flash Exp" → describe the config-driven Gemini 3 Pro Image model), `DEMO_GUIDE.md:439`, `DEPLOYMENT.md:465-467` (pending approval of finding 1).
4. Amend the phase doc's open question 1 with the `gemini-3-flash-preview` finding (provenance note per the Discoveries convention).
5. Re-run the same Stage 1 + Stage 2 smoke test against the new IDs — both must succeed.
6. `make test-unit`, `make test-e2e`, `make test-integration`.

Per CLAUDE.md's trivial-phase fast path, the implement step runs inline (one-task plan) instead of per-task subagent dispatch — everything else (plan approval, verification, WORK_LOG/STATUS checkpoints, PR) stays standard.

## Approval addendum (owner, 2026-07-14)

Approved with one addition: **GA models are the defaults, but the two media-model config values become env-overridable** (`IMAGE_GENERATION_MODEL` / `VIDEO_GEN_MODEL` env vars, falling back to the GA IDs), so preview models (e.g. Gemini Omni Flash, Nano Banana 2 Lite) can be swapped in for pipeline testing without code changes. The actual evaluation of those preview models remains Phase 13a/13b scope. Owner also confirmed: env bootstrap on project `kaggle-on-gcp` (Vertex path), and updating both `DEMO_GUIDE.md` and `DEPLOYMENT.md` model-ID rows.

**Plan-approval amendment (owner, 2026-07-14):** rename the video constant/env var `VEO_MODEL` → `VIDEO_GEN_MODEL` — model-agnostic naming since Omni and Veo are both video-generation backends, aligning with the image-side naming. `video_tools.py` is the only consumer; renamed in the same commit as the config change.

## Test plan

- `make test-unit` and `make test-e2e` pass (already model-ID-free, so these guard against regressions elsewhere).
- `make test-integration` passes (uses the orchestration model, untouched by this phase).
- **Release gate (per phase doc):** a real Stage 1 image generation and a real Stage 2 Veo animation succeed against the new GA IDs on the Vertex path (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`, location `global`).
- **Demo scenario:** create `docs/demo-scenarios/fashion.md` with one scenario — "generate a video ad for an existing demo campaign product, through Stage 1 and Stage 2" — and run it via `verifying-with-demo-scenarios` (adk web on :8501, driven by the `demo-scenario-verifier` subagent). This doubles as the end-to-end proof the phase doc's exit criteria require, and seeds the scenario file later workstreams reuse.
- Validation greps from the phase doc: exact-ID grep returns nothing; `grep -n 'IMAGE_GENERATION\s*=\|VEO_MODEL\s*=' app/config.py` shows only GA IDs; `grep -rn "Gemini 2.0 Flash Exp" app/` returns only the two Phase-1-owned hits (`video_tools.py:18`, `agent.py:200`).

## Out of scope

- `MODEL = "gemini-3-flash-preview"` (config.py:24) — confirmed no near-term cutoff; any move to `gemini-3.5-flash` is a future decision, not this phase.
- Phase 13a/13b media-model upgrades (Nano Banana 2 Lite, Omni Flash) — this is a like-for-like swap only.
- The `video_tools.py:18` docstring and `agent.py:200` "Gemini 2.0" texts — Phase 1, item 6.
- `README.md` — client-facing, untouched (contains no model IDs anyway).
- Any change to video duration/aspect config, prompt builders, or call-site code.
