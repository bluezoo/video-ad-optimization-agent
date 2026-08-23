# Phase 14c — Omni-Based Post-Generation Video Editing (Visual Edits Only)

## Goal

Add an experimental, opt-in Review Agent tool that lets a human reviewer request a targeted **visual** edit (recolor an object/garment, remove/replace a background element, adjust an on-screen prop, etc.) to an already-generated video, using Gemini Omni Flash's `interactions.create(..., video_config.task="edit")` path — without touching the default Veo 3.1 generation pipeline.

## Relationship to Phase 14b

Phase 14b (merged, PR #14, 2026-07-23) evaluated Omni Flash for *generation* and issued a **NO-GO** specifically because the one differentiating capability it wanted — chained revision via `previous_interaction_id` — was server-rejected on Vertex AI (`400: "gemini-omni-flash-preview on this path do not support previous_interaction_id"`). That NO-GO stands for the *revision-via-lineage* mechanic. 14b did not test the separate, simpler `edit`-task flow (attach an existing video + a one-shot text instruction, no `previous_interaction_id` involved).

> **Discovery (workstream 14c, 2026-08-23):** a live-tested exploration this session probed exactly that simpler `edit`-task flow, from scratch, on Vertex AI (`gemini-omni-flash-preview`, `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_LOCATION=global`) using an isolated venv with `google-genai==2.19.0` (the repo pins `google-genai==2.12.1`, below the ≥2.14.0 floor the typed Interactions API needs). **Result: a real, verified, single-attribute visual edit (white blouse → red) succeeded**, confirmed by frame-level before/after comparison — everything else in the frame (face, hair, other garments, background, pose, lighting) was pixel-stable. This is a narrower, different finding from 14b's: **"revision via `previous_interaction_id` lineage": still NO-GO. "Single-shot visual edit via the `edit` task": now GO, narrowly.** 14b's blanket "steps 4-6 deferred" note is superseded for this one narrow capability only — see 14b's own amendment marker for the cross-reference.
>
> The same exploration also live-tested EN→ES dialogue translation via the identical `edit`-task mechanism (a plausible-looking but ungrounded idea floated before this workstream): the API call succeeded transport-wise, but the output was a code-switched Spanglish transcript ("This fridge keeps **tus comestibles** fresh **toda la semana**") with lip movements independently judged **not synchronized** to the new audio — consistent with Google's own current docs, which state plainly **"Voice editing is not supported"** for this model. **Translation/dubbing is explicitly out of scope for this phase** — see "Out of scope" below.

## Current state (post-exploration findings)

- Omni Flash (`gemini-omni-flash-preview`) is reached via a dedicated **Interactions API** (`client.interactions.create()`/`client.interactions.get()`), not Gemini's `generateContent` or Veo's `generate_videos`/long-running-operation surface. It is Preview status on Vertex AI (Vertex model card: release 2026-06-30, retirement 2027-06-30 — a defined sunset, not a GA promotion date), reachable from this app's standard Vertex AI auth path (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`, project + `GOOGLE_CLOUD_LOCATION=global`) with no special allowlist documented.
- The repo's pinned `google-genai==2.12.1` (`app/requirements.txt`) is below the working floor — every successful probe (14b's and this session's) used ≥2.14.0 (14b used 2.14.0; this session used 2.19.0 in an isolated venv, not the repo's own `.venv`).
- Two real API contract details were discovered live, undocumented in Google's own docs, and must be encoded in the implementation:
  1. `VideoContent.data` in the SDK's typed `interactions` module only auto-base64-encodes `os.PathLike`/`IO[bytes]` inputs — a bare `str` file path is passed through as literal (corrupt) "base64 data" and only fails server-side with a 400 (`"Expected string, corrupt base64"`), not client-side. Must always wrap file paths in `pathlib.Path(...)`.
  2. For `video_config.task="edit"`, `response_format.aspect_ratio` **must be omitted** — the server derives it from the input video and 400s (`"Aspect ratio cannot be set in response format for edit task"`) if it's set explicitly.
- Latency for a single edit call: 67.4s synchronous round-trip for an 8s 720p input — noticeably slower than the ~30s 14b's prototype cited for pure `text_to_video`/`image_to_video` generation with this model. Any UI-facing tool should default to background+poll, not sync-blocking.
- Not yet tested by any probe in this repo: `previous_interaction_id` combined with an `edit` task (chained/iterative edits — "no, make it darker" as a follow-up) — 14b's NO-GO was against `text_to_video`/`image_to_video` tasks, not `edit`; multi-attribute edits in one instruction; edits against a video that actually went through this app's real pipeline (`generate_video_ad`'s stored output — this session's probes all used one hand-picked throwaway clip); and behavior in GCS-storage mode (all probes ran local-mode, forcing `GCS_BUCKET=` empty).

## Implementation approach

**New tool module: `app/tools/video_edit_tools.py`.** Mirrors the signature/return-shape conventions of `generate_video_from_product()` in `app/tools/video_tools.py` (dict return with `success`, artifact path/URI, structured error fields on failure; `async def` since the underlying call is long-running/pollable):

```python
async def edit_video_with_omni(
    video_id: str,
    edit_instruction: str,
    *,
    max_wait_time: int = 300,
) -> dict:
    """Apply a targeted visual edit to an existing generated video via
    Gemini Omni Flash's Interactions API (video_config.task="edit").

    Args:
        video_id: DB id of a previously generated video.
        edit_instruction: natural-language edit request, e.g.
            "change the shirt color to red", "remove the coffee cup from
            the counter". Single-attribute edits are the verified case;
            multi-attribute instructions are unverified.
        max_wait_time: seconds to wait when the background+poll path is used.

    Returns:
        On success: {"success": True, "video_id": <new id>,
            "source_video_id": video_id, "video_path" | "gcs_uri": ...,
            "backend": "omni_flash", "interaction_id": ..., "duration_seconds": ...}
        On failure: {"success": False, "error": <message>,
            "error_type": "unsupported_edit" | "timeout" | "api_error"}.
    """
```

Internal helpers, parallel to `video_tools.py`'s `_wait_for_veo_operation`/`_extract_video_bytes` but **not sharing them** (interactions vs. operations are genuinely different primitives — 14b's step-2 note about the wrong shared-abstraction boundary applies here too):
- `_load_video_bytes_for_edit(video_id) -> bytes` — resolve the stored artifact (local path or GCS) to bytes for `VideoContent`, reusing the existing storage-layer read path.
- `_wait_for_omni_interaction(client, interaction_id, max_wait_time, poll_interval=10) -> Interaction` — background+poll loop against `client.interactions.get(id)` (positional, not `interaction_id=`), mirroring `_wait_for_veo_operation`'s timeout/failure semantics.
- `_extract_omni_video_bytes(interaction) -> bytes` — pull the `model_output` step's video content, base64-decode. Always wrap file-path inputs in `pathlib.Path(...)` (contract detail #1 above); never set `response_format.aspect_ratio` for an edit task (contract detail #2 above).

**Agent placement: extend the existing Review Agent — do not create a new Edit Agent.** Post-generation editing is a review-time action: a human reviewer is already looking at a generated video and deciding approve/reject — "request a targeted edit" is a natural third option, not a new pipeline stage. The Review Agent already owns the HITL context (which video is under review, its DB id/lineage, activation-gating logic); a new Edit Agent would duplicate that context and need a new Coordinator routing rule for one tool. A new Edit Agent would only be justified later if edit-related tools multiply — not for one opt-in tool now.

**Config additions (`app/config.py`):**
- `OMNI_EDIT_MODEL = os.environ.get("OMNI_EDIT_MODEL", "gemini-omni-flash-preview")` — separate from `VIDEO_GEN_MODEL`; Veo stays untouched and default.
- `ENABLE_OMNI_EDIT = os.environ.get("ENABLE_OMNI_EDIT", "false").lower() == "true"` — feature flag gating the tool's registration on the Review Agent, default off, given the model's Preview/sunset status.
- No new region variable — `GOOGLE_CLOUD_LOCATION=global` is already required repo-wide for Gemini 3.x/Veo and was confirmed sufficient for Omni Flash's Interactions API in every probe (14b and this session).
- `app/requirements.txt`: bump the `google-genai` floor to `>=2.14.0` (this session used 2.19.0 successfully) — the Interactions typed API used by every successful probe needs this floor; the repo's current pin (2.12.1) is below it.

## Test plan

- **Fast tier stays network-free** (same rule as workstream 11b's BlueZoo live conformer): unit tests for `video_edit_tools.py` stub/mock the Omni interactions client, exercising `_wait_for_omni_interaction`'s timeout/success/failure branches and the two contract-detail guards (path-wrapping, no aspect_ratio on edit tasks) without a real network call.
- **Live tier** (`tests/live/`, `pytest.mark.live`, `make test-live`): one real end-to-end test — generate or reuse a real pipeline video, call `edit_video_with_omni` with a single-attribute instruction, assert success + a plausible output (duration/codec match, non-trivial file size). Mirrors 11b's `tests/live/test_live_bluezoo_datasource.py` pattern.
- **Demo scenario**: add a scene to a `docs/demo-scenarios/*.md` doc (fashion, since the Review Agent's existing HITL flow is fashion-first) driving the new tool through `adk web` via `verifying-with-demo-scenarios` + the `demo-scenario-verifier` subagent — a real edit request against a real reviewed video, confirming the tool call fires with sane arguments and the response references the edited artifact. `ENABLE_OMNI_EDIT=false` (default) must leave existing fashion scenarios byte-identical — regression-checked in the same pass.
- Add the journey to root `DEMO_GUIDE.md`'s "Workstream Testing Journeys" section per CLAUDE.md's ws11a rule (this changes agent-visible tool surface).

## Out of scope

- **EN→ES (or any) dialogue translation/dubbing/lip-sync.** Confirmed broken for this model both by Google's own docs ("Voice editing is not supported") and by this session's live test (code-switched partial translation, unsynced lips). `translate_video_dialogue()` is written as a documented `NotImplementedError` placeholder only — never wired into any agent. If this capability is still wanted, it needs a separate research spike into a different vendor/Google surface, not a retry against Omni Flash.
- **Chained/iterative revision via `previous_interaction_id`** for edit tasks specifically — 14b's NO-GO covered `text_to_video`/`image_to_video`; this phase's own probe only tested a single from-scratch edit, not a chain. Not probed, not built.
- **Multi-attribute edit instructions** (e.g. "change the shirt AND remove the cup") — only single-attribute edits were verified; behavior with compound instructions is unknown and not built against.
- **GCS-storage-mode edits** — every probe ran local-mode (`GCS_BUCKET=` forced empty). `_load_video_bytes_for_edit`'s GCS-read branch, if not exercised by the live test, should be flagged as unverified, not assumed correct.
- **Making Omni Flash a `VIDEO_GEN_MODEL` alternative or touching the default Veo pipeline in any way.** Veo 3.1 remains the sole default generation backend; this phase only adds a post-generation edit path.
- **Promoting `ENABLE_OMNI_EDIT` to default-on.** Stays opt-in given the model's Preview/sunset status.

## Validation

- [ ] `make test` passes after the `google-genai` bump alone, before any new tool code — isolates SDK-upgrade risk from feature risk (a major SDK bump could touch the existing Veo call path too).
- [ ] `edit_video_with_omni` produces a verified single-attribute edit against a real pipeline-generated video (not a throwaway clip), confirmed by frame-level before/after comparison — not just "the call returned success."
- [ ] The tool's failure paths (timeout, unsupported edit request, `interactions.get` 500s on sync-created ids — a real server bug hit in 14b's probe) map to clear `error_type` values, not raw exceptions leaking to the agent.
- [ ] `ENABLE_OMNI_EDIT=false` (default) leaves the Review Agent's tool list and behavior byte-for-byte unchanged from before this phase.
- [ ] A `DEMO_GUIDE.md` journey exists and was manually driven via `adk web` per `verifying-with-demo-scenarios`.

## Exit criteria

An opt-in, clearly-experimental visual-edit tool exists on the Review Agent, proven against a real generated artifact (not just a throwaway probe clip), with lineage tracked (`source_video_id`) and the default Veo/no-edit behavior completely unaffected when the feature flag is off.

## Dependencies

Phase 14b (merged) — Veo polling consolidation and the SDK/API groundwork this phase reuses.

## Open questions

1. Does `previous_interaction_id` work for `edit`-task chaining specifically (as opposed to the `text_to_video`/`image_to_video` generation tasks 14b tested it against)? Not probed by anyone in this repo — worth one bounded reprobe before ever proposing iterative "refine this edit" UX.
2. Multi-attribute edit instructions — untested; only single-attribute was verified. Could silently degrade quality or apply only one change.
3. Does the edit call behave identically when the source video is stored in GCS rather than read from a local path? `_load_video_bytes_for_edit` needs to handle both; only local was exercised in the exploration.
