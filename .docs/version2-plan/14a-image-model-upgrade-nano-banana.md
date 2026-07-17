# Phase 14a — Image Model Upgrade (Nano Banana 2 Lite)

## Goal

Add a provider-neutral image-generation contract, and evaluate/adopt Nano Banana 2 Lite (`gemini-3.1-flash-lite-image`) as a Stage-1 backend option, without breaking the Phase 1 GA baseline (`gemini-3-pro-image`).

## Decoupled from everything else

This phase (and 14b) can be done any time after Phase 1, independent of the generalization/live-mode track (Phases 2-13). It's listed last only because it's the most speculative/evaluative of the phases, not because it's lower priority than, say, Phase 10.

## Current state

- Stage 1 image generation lives in `generate_scene_image()` (`app/tools/video_tools.py`, ~lines 191-259), calling whatever model `config.py`'s `IMAGE_GENERATION` points at — after Phase 1, `gemini-3-pro-image` (GA).
- `gemini-3.1-flash-lite-image` ("Nano Banana 2 Lite") — model ID, GA date (2026-06-30), and 1K/1120-output-token cap independently confirmed against Google's official model page. Its approximate per-image cost depends on current token pricing and can change — treat any specific dollar figure as a framing estimate to re-check at evaluation time (link the live pricing page), not a fixed number to design around. Google's own materials pair it with Gemini Omni Flash (Phase 14b) as a matched fast/cheap pipeline, rather than treating it as a drop-in replacement for the higher-resolution default in all cases.
- No provider-neutral abstraction exists today — `generate_scene_image()` already calls a configured model ID through the `generate_content(model=IMAGE_GENERATION)` call at `app/tools/video_tools.py:236-237` (client init at `:216`); the model ID itself is already config-driven via `IMAGE_GENERATION`, it just isn't exposed as an easily-swappable "backend" concept yet.

## Steps (scoped down from the first draft — correction from review)

The first draft of this phase jumped straight to a new `IMAGE_MODEL_BACKEND` config value plus an `ImageGenerator` protocol. Review correctly pointed out that both models are called through the same existing `client.models.generate_content()` surface — introducing a new backend abstraction for what is, today, just a second model *ID* through the same call shape is unnecessary indirection. Start simpler:

1. Confirm `IMAGE_GENERATION` (`app/config.py`) can already be pointed at `gemini-3.1-flash-lite-image` and compare it against `gemini-3-pro-image` through the existing call path, with no new abstraction — this alone is enough to run the side-by-side evaluation in step 3.
2. Only introduce an `ImageGenerator` protocol / distinct backend abstraction if the evaluation in step 3 reveals the two models actually need materially different request/response handling (different parameters, different response shapes, different error handling) — or once there's a genuine second *provider* (not just a second model ID from the same provider) to support. Don't build the abstraction speculatively ahead of that need.
3. Run a side-by-side quality comparison between the two model IDs. **This comparison should cover both the existing fashion catalog and Phase 8's non-fashion fixture catalog** — the two are independent efforts (this phase depends only on Phase 1 for its core backend-swap work), but a genericity-aware comparison needs Phase 8's fixture data to exist, so treat that specific part of step 3 as conditional on Phase 8 being done, not as a hard dependency for the rest of this phase.

## Validation

- [ ] `IMAGE_GENERATION=gemini-3.1-flash-lite-image` produces a working image through the existing `generate_scene_image()` call path with no code changes beyond config.

  > **Amended (workstream 01, 2026-07-14):** pre-verified early — with Phase 1's env overrides in place, `IMAGE_GENERATION_MODEL=gemini-3.1-flash-lite-image` produced an on-brief scene image through the unmodified call path (sage satin camisole, studio, elegant; 102 KB output vs ~1.2-1.5 MB from `gemini-3-pro-image`, consistent with the 1K-output-token cap noted above). This validation item is effectively done; this phase's remaining work is the side-by-side quality/cost comparison.
- [ ] Existing tests referencing `IMAGE_GENERATION`/Stage 1 image generation still pass unchanged with the default model ID.
- [ ] A manual side-by-side comparison (step 3) is documented (even informally) before recommending a default-model change — including the non-fashion fixture comparison once Phase 8 exists.

## Exit criteria

`gemini-3.1-flash-lite-image` is confirmed to work as a drop-in `IMAGE_GENERATION` value through the existing call path; a documented comparison exists; a backend abstraction is added only if the comparison shows it's actually needed.

## Dependencies

Phase 1 (GA model baseline must already be in place) for the core backend-swap work. The non-fashion half of the step-3 comparison additionally depends on Phase 8's fixture catalog — note this is a validation-scope dependency, not a blocker on starting the rest of this phase.

## Open questions

Is 1K resolution acceptable for this app's actual display/demo use case (in-store screens, dashboard previews), or does the current higher-resolution default matter for a specific use case this plan hasn't accounted for? Worth a quick check rather than assuming either way.
