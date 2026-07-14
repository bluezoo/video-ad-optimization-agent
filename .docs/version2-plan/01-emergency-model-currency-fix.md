# Phase 0 — Emergency Model Currency Fix

**Do this before anything else in this plan.** It has nothing to do with the client's two requests and everything to do with the app continuing to function at all.

## Goal

Stop pointing production config at Gemini/Veo model IDs that are deprecated or about to be, on the Vertex AI surface this repo actually deploys to (Cloud Run, Agent Engine).

## Why this is Phase 0, not part of the media-upgrade workstream

This was not in the original plan (`.docs/2026-07-12-version2-review-and-plan.md`) at all — it surfaced during re-grounding against current Vertex AI model documentation (2026-07-13). It is:

- **Independent** of everything else in this plan (doesn't touch generalization, data sources, or metrics).
- **Trivial to fix** (two config string changes).
- **Time-critical**, unlike anything else here.

Do not bundle this with Phase 13a/13b (the Nano Banana / Omni Flash upgrade). Those are a deliberate architectural upgrade to a new generation paradigm and deserve their own careful rollout. This phase is a like-for-like swap to keep the lights on with the *current* architecture.

## Current state (verified against Vertex AI model documentation, 2026-07-13)

`app/config.py:27-28`:
```python
IMAGE_GENERATION = "gemini-3-pro-image-preview"
VEO_MODEL = "veo-3.1-generate-preview"
```

- `gemini-3-pro-image-preview` — preview model ID, scheduled for retirement from Vertex AI's model garden on **2026-07-17** (4 days from today). After that date, calls using this model ID will fail.
- `veo-3.1-generate-preview` — preview model ID that Vertex AI's own release notes list as **already deprecated as of 2026-04-02**, with `veo-3.1-generate-001` as the documented replacement. This app may already be experiencing generation failures in any environment hitting Vertex AI directly (as opposed to AI Studio / `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, which may use a different model registry and not yet be affected — this asymmetry needs to be confirmed in Step 1 below, not assumed). Note: "silent fallback" is not the actual risk here — `generate_scene_image()` (`app/tools/video_tools.py`) already re-raises on failure rather than swallowing it, so a broken model ID should surface as a clear error, not a quiet placeholder. The real risk is simply generation failing outright.

GA replacement IDs (confirmed present in the current Vertex AI model garden as of 2026-07-13):
```python
IMAGE_GENERATION = "gemini-3-pro-image"
VEO_MODEL = "veo-3.1-generate-001"
```

These are drop-in replacements at the config level — no call-site changes to `app/tools/video_tools.py` are required, since both existing functions (`generate_scene_image()`, `animate_scene_with_veo()`, `generate_video_from_product()`) already read the model ID from `config.py` rather than hardcoding it.

## Steps

1. **Confirm current breakage, don't assume it.** Before changing anything, run one real Stage 1 (image) and one real Stage 2 (video) generation against whichever backend your environment is actually configured for (`GOOGLE_GENAI_USE_VERTEXAI=TRUE` vs `FALSE`, per `app/.env`). Record whether it currently succeeds, fails outright, or fails silently (e.g., falls back to a placeholder image without raising). This tells you whether Veo's April 2 deprecation is already biting in your environment or whether Vertex is still tolerating the preview ID with a deprecation warning.
2. Update `app/config.py:27-28` to the GA IDs shown above.
3. Grep the repo for any other hardcoded reference to the two preview IDs or their now-stale descriptions, in case a test fixture, doc, comment, or script duplicates them instead of importing from `config.py`:
   ```bash
   grep -rn "gemini-3-pro-image-preview\|veo-3.1-generate-preview" --include="*.py" --include="*.md" --include="*.sh" .
   ```
   Confirmed hits to fix as part of this step (found during review, not hypothetical): a hardcoded old Veo ID inside a comment at `app/tools/video_tools.py:966`, and a stale "Gemini 2.0" comment describing the Stage-1 model at `app/tools/video_tools.py:218` (this is a comment near the call site, distinct from the `MEDIA_AGENT_INSTRUCTION` text fixed in Phase 1, item 6 — fix both). Also check `README.md` and `app/agent_engine_app.py`.
4. Re-run the same Stage 1 + Stage 2 smoke test from Step 1 against the new IDs and confirm both succeed.
5. Run `make test-unit` and `make test-integration` to confirm nothing else references the old IDs in a way that breaks mocking/assertions.

## Validation

- [ ] `grep -n 'IMAGE_GENERATION\s*=\|VEO_MODEL\s*=' app/config.py` shows the two GA IDs, not the old preview IDs. (Do not grep for the bare word "preview" in `config.py` — it will also match the unrelated main orchestration model, `MODEL = "gemini-3-flash-preview"` at `app/config.py:24`, which is intentionally out of scope for this phase per the open question below, and a broad grep would produce a false failure.)
- [ ] A real Stage 1 image generation call succeeds against the new `IMAGE_GENERATION` ID — this is the actual release gate, not the config grep.
- [ ] A real Stage 2 video generation call succeeds against the new `VEO_MODEL` ID — the actual release gate.
- [ ] `make test-unit` and `make test-integration` pass unchanged.
- [ ] The exact-ID grep from Step 3 (`gemini-3-pro-image-preview\|veo-3.1-generate-preview`) returns nothing, including the confirmed `video_tools.py:966` and `:218` hits.

## Exit criteria

Both models in `app/config.py` point at GA (non-preview) IDs, and a real end-to-end video generation (Stage 1 → Stage 2) succeeds in whatever environment (`GOOGLE_GENAI_USE_VERTEXAI=TRUE` or `FALSE`) is used for demos.

## Dependencies

None. Do this first, independent of every other phase.

## Open questions

- Is `MODEL = "gemini-3-flash-preview"` (`app/config.py:24`, the main agent orchestration model) also on a deprecation timeline? It was not flagged in this pass — confirm it's still GA-track or preview-with-no-near-term-cutoff before treating it as settled. If in doubt, check Vertex's model garden page directly rather than assuming.
- Confirm whether `GOOGLE_GENAI_USE_VERTEXAI=FALSE` (AI Studio / `GOOGLE_API_KEY`) path uses the same model ID registry as Vertex, or a separate one with different deprecation timing — this determines whether local/demo development was ever actually affected by the Veo April 2 deprecation, or only Vertex-backed deployments (Cloud Run, Agent Engine).
