# Phase 13b — Video Model Upgrade (Gemini Omni Flash / Interactions API, Experimental)

## Goal

Evaluate Gemini Omni Flash, via the Interactions API, as an **optional, experimental** second video-generation backend alongside Veo 3.1 — not a replacement, and not something to treat as GA/default.

## Correction from review — the framing in the first draft was wrong, not just optimistic

The first draft of this phase (and the overview's "What changed" item 4) claimed the Interactions API is GA/stable and that "Omni Flash is the new default generation path." **This is contradicted by Google's own current primary sources**, checked directly during review:

- The official Interactions API reference itself labels the API **experimental**, on a **`v1beta1`** endpoint.
- The `python-genai` SDK repository labels Interactions **Beta/Preview** and explicitly warns that schemas may still break.
- Omni Flash's own model page and its launch blog post call it **public preview**, describing price/performance and conversational-editing capability — neither source states it's a default replacement for Veo.

**Corrected framing:** Omni Flash is an interesting, actively-evolving capability worth evaluating, not a settled upgrade path. Veo 3.1 (GA after Phase 0) remains the default for as long as Omni Flash and the Interactions API remain experimental. Do not build anything in this phase that assumes Omni Flash becomes load-bearing for the default pipeline.

## Current state

- Video generation today goes through Veo 3.1 (`veo-3.1-generate-preview` → `veo-3.1-generate-001` after Phase 0), called from three independently-duplicated blocking polling loops: `animate_scene_with_veo()` (`app/tools/video_tools.py:308`), `generate_video_from_product()` (`video_tools.py:590`), and `generate_video_ad()` (`video_tools.py:971`). All three poll `client.operations.get()` with a blocking `time.sleep()` inside an `async def` function — functionally working today, but duplicated three times with no shared helper, and blocking sleep inside async code is worth fixing regardless of which model backend is used.
- Gemini Omni Flash (`gemini-omni-flash-preview`) is accessed via the Interactions API (`client.interactions.create()`), supporting task types `text_to_video`, `image_to_video`, `reference_to_video`, and `edit`, at 3-10 seconds, 720p. It documents a `previous_interaction_id` field and describes conversational/iterative editing — but **the exact mechanics of using `previous_interaction_id` to request a specific video revision are not established by the docs alone** (does referencing a prior interaction alone supply enough context for a meaningful edit, or does it also need the prior video/a mask/a reference asset passed explicitly?). This needs a small real prototype before any schema/tool design is finalized, not an assumption from the field's existence.
- **The `google-genai>=1.55.0` floor in `app/requirements.txt:18` was not verified to include the Interactions surface at all** — the first draft of this phase asserted SDK version 2.11.0 as "confirmed current," but this checkout has no installed environment or lockfile to reproduce that claim against. Treat the minimum working SDK version as unverified until a real spike confirms it.
- The Review Agent's tool list today (`app/agent.py:462`) contains only review/activation/status tools — **there is no existing regeneration or revision tool of any kind**. "Wiring `previous_interaction_id` into the revision flow" is not a small addition to an existing flow; it requires a new tool, new schema/storage for the interaction ID and the resulting asset's lineage, and a new route from the Review Agent to the generation pipeline that doesn't exist today.
- **Wrong original abstraction: one shared polling helper across both backends does not fit.** Veo's three loops all poll a long-running *operation* via `client.operations.get()`. Omni Flash's Interactions API polls an *interaction* via a different method (`client.interactions.get()`, per the Interactions reference) — these are not the same operation type, and forcing them through one shared polling primitive would be the wrong abstraction boundary, not a simplification.

## Steps

1. **Consolidate Veo's three duplicated polling loops on their own, as a standalone cleanup, independent of Omni Flash.** Replace the blocking `time.sleep()` with `asyncio.sleep()` in one shared helper for Veo's `client.operations.get()` polling, used by all three current call sites. Do this regardless of whether Omni Flash is ever adopted — it's a real, low-risk bug fix (blocking sleep inside `async def`) on its own merits.
2. Define one shared **result contract** (e.g., a `GeneratedVideo` dataclass/model: output URI or bytes, duration, resolution, backend-used, and — for Omni Flash — the interaction ID) that both backends produce, rather than trying to share their polling mechanics. Veo's consolidated helper (step 1) and a separate Omni Flash polling path (step 4) both normalize into this one result shape; the polling implementations themselves stay separate because the underlying APIs are genuinely different.
3. **Before writing any Omni Flash integration code, run a small real prototype**: call `client.interactions.create()` with `image_to_video` for one sample product, record the actual request/response shape, confirm which SDK version actually supports it, and specifically test what `previous_interaction_id` requires for a meaningful edit (does it need the prior video re-attached, a mask, a text delta alone?). Document findings before finalizing any schema. This replaces "wire it in" with "prototype it, then wire it in," since the mechanics aren't fully known from documentation alone.
4. Extend the `VIDEO_MODEL_BACKEND` config toggle (parallel to Phase 13a) to support `"veo"` (default) and `"omni_flash"` (experimental, opt-in). Implement the Omni Flash path per the prototype's findings from step 3, normalizing its output into the shared `GeneratedVideo` contract from step 2.
5. **Add a genuinely new Review Agent tool** for revision requests (there is no existing one to extend) — including schema/storage for the interaction ID and the revised asset's lineage (which video is a revision of which). This only applies when `VIDEO_MODEL_BACKEND=omni_flash`; the Veo path keeps its current from-scratch-only regeneration behavior, since Veo has no equivalent primitive.
6. Pin and test the actual minimum `google-genai` SDK version this integration needs, based on the step-3 prototype — update `app/requirements.txt` explicitly rather than relying on the existing unpinned `>=1.55.0` floor.
7. Do not remove the Veo path, and do not change its default status. Keep both behind the config toggle. Revisit whether `omni_flash` should ever become the default only after both a real side-by-side quality/cost comparison (same spirit as Phase 13a) and the Interactions API/Omni Flash model moving off experimental/preview status.

## Validation

- [ ] The consolidated Veo polling helper (step 1) is used by all three former call sites, with a single test suite covering timeout, success, and failure cases instead of three separately-untested duplicates — this passes independent of anything else in this phase.
- [ ] The step-3 prototype's findings (actual request/response shape, working SDK version, `previous_interaction_id` semantics) are written down before any schema/tool code is finalized.
- [ ] `VIDEO_MODEL_BACKEND=omni_flash` produces a working video through the same public pipeline entry points as the Veo path, verified end-to-end at least once with a real API call (not just mocked) — clearly labeled as exercising an experimental backend.
- [ ] The new Review Agent revision tool, under `omni_flash`, produces a visibly-iterated result (not a from-scratch regeneration) when given a revision request — verified against the step-3 prototype's actual confirmed mechanics, not an assumed API shape.
- [ ] `VIDEO_MODEL_BACKEND=veo` (default) continues to work exactly as before — full regression pass on `make test-integration` / `make test-e2e` for the Veo path, unaffected by this phase.
- [ ] The pinned SDK version from step 6 is recorded in `app/requirements.txt` and the full test suite passes against it.

## Exit criteria

Veo's polling loops are consolidated regardless of the rest of this phase's outcome. Gemini Omni Flash is available as an explicitly experimental, opt-in second backend, evaluated against a real prototype rather than documentation assumptions, with a genuinely new (not retrofitted) Review Agent tool for its iterative-editing capability. Veo remains the default.

## Dependencies

Phase 0 (GA Veo baseline in place as the safety net). Not blocked on Phase 13a, though doing 13a first is convenient since Google pairs Omni Flash with Nano Banana 2 Lite in its own materials.

## Open questions

1. Given that both the Interactions API and the Omni Flash model are currently labeled experimental/preview by Google's own sources, is it worth investing in this integration now, or should this phase wait for either surface to reach GA? Worth an explicit decision rather than proceeding on the assumption (from the first draft of this plan) that it's already a stable, default-worthy path. [global #15 in `99-open-questions.md`, reframed]
2. Once (if) Omni Flash reaches GA, should it become the default `VIDEO_MODEL_BACKEND`, or does this app's specific needs (duration/resolution constraints — 3-10s/720p is more constrained than Veo's typical output) argue for keeping Veo as default regardless? Decide after both a side-by-side comparison and a GA status change, not before either.
