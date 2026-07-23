# Omni Flash Interactions API prototype — findings (Phase 14b step 3)

**Date:** 2026-07-23 (probe run ~02:14–02:18 UTC)
**Script:** `scripts/probe_omni_interactions.py` (committed version = round 2; run logs at `/tmp/omni-probe-round1.log`, `/tmp/omni-probe.log`, key evidence quoted inline below)
**Environment:** Vertex AI, `GOOGLE_CLOUD_LOCATION=global`, google-genai **2.14.0** (worktree venv), model `gemini-omni-flash-preview`
**Method:** two bounded live rounds. Round 1 ran the plan's shapes and surfaced three discoveries (sync completion, a confounded invalid-argument failure, "step_list not turn_list"). Round 2 isolated each variable; the committed script is the round-2 probe with round-1 discoveries baked into its docstring.

## Answers to the five questions

### 1. Does typed `interactions.create` accept a video-generation request, and with exactly which parameters?

**Yes.** The working request shape is minimal — the SDK's `create(*, request=None, ..., **body)` surface with plain body kwargs (this *is* the typed path in 2.14.0; body keys are validated against `google.genai.interactions.CreateModelInteractionParam`):

```python
client.interactions.create(
    model="gemini-omni-flash-preview",
    input="A 4-second product hero shot of a matte black cold brew can ...",
)
```

Evidence (round 2):

```
=== create: text_to_video, bare text input (known-good round-1 shape) ===
OK: Interaction(status='completed', model='gemini-omni-flash-preview', id='TnlhaoXMKISb9LsPv8Sv2A0'... 
latency: 28.5s
'output_video': {'mime_type': 'video/mp4', 'uri': None, 'data_bytes': 1338920}, 'total_output_tokens': 23168
```

**image_to_video also works**, but the list input MUST be step_list format, not turn/role format:

```python
client.interactions.create(
    model=MODEL,
    input=[{
        "type": "user_input",
        "content": [
            {"type": "image", "data": image_b64, "mime_type": "image/png"},
            {"type": "text", "text": "Animate this exact scene into a 4-second video ..."},
        ],
    }],
)
```

Round-1 evidence for the rejected turn format: `FAIL [BadRequestError]: Error code: 400 - {'error': {'message': 'When using the steps-based API version, use step_list input format instead of turn_list.'}}`. Round-2 step_list attempt: `status='completed'`, input tokens `image: 1100, text: 31`, output video saved (1,030,148 bytes). The output followed the reference image's portrait aspect (720x1280 vs 1280x720 for the text-only runs) — i.e. the reference image genuinely conditioned the generation.

Parameters that do NOT work:

- `response_modalities=["video"]` → `400 Request contains an invalid argument.` (isolated in round 2; this was the poison in round 1's confounded failures — video output is implicit in the model, not requested via modalities).
- Raw-dict `request={"body": ...}` — already proven broken in ws01 (`400: value 'UNKNOWN' is not supported for 'type'`); not re-tested.
- `previous_interaction_id` — see question 3.

Working optional parameter: `background=True` (see question 2).

### 2. What does polling look like?

Two distinct modes, both observed working end-to-end:

- **Synchronous (default):** `create()` blocks ~28.5s and returns `status='completed'` with the video **inline** — no polling at all. BUT `interactions.get(<sync id>)` afterwards returned `500 Internal error encountered.` — retrieval of sync-created interactions is broken server-side (relevant to any later lineage/re-fetch design).
- **Background (`background=True`):** returns immediately with an id of a different shape (`video-f5428b15-...` vs sync's `TnlhaoXMKISb9LsP...`), `status='in_progress'`. Poll via `client.interactions.get(id)` — note: **positional `id`**, not the plan's guessed `interaction_id=`. States seen: `in_progress` (x2) → `completed` at 30s. The completed object is fully populated (usage, steps, inline video).

Statuses defined by the SDK (`google.genai.interactions.InteractionStatus`): `in_progress, requires_action, completed, failed, cancelled, incomplete, budget_exceeded, queued`.

Output object shape (both modes): `Interaction.steps = [UserInputStep, ThoughtStep, ModelOutputStep(content=[VideoContent])]`, with the convenience accessor `Interaction.output_video` → `VideoContent(mime_type='video/mp4', data=<base64>, uri=None)`. Decoded outputs (ffprobe): **4.0s, 24fps, 1280x720** (text-to-video) / **720x1280** (image-to-video, following the reference), ~1.0–1.1 MB each. Every generation billed 23,168 video output tokens.

### 3. What does `previous_interaction_id` need for a meaningful edit?

**It is not supported at all on this path.** Text delta alone, on the minimal known-good shape, referencing a completed interaction's id:

```
=== edit via previous_interaction_id (text delta only) ===
FAIL [BadRequestError]: Error code: 400 - {'error': {'message': 'gemini-omni-flash-preview on this path do not support previous_interaction_id.', 'code': 'invalid_request'}}
```

(Round 1's edit attempt appeared to fail differently, but that failure was confounded with `response_modalities`/`background`; round 2 isolated it — the server rejects the parameter itself for this model.) A "revision" today therefore means a **from-scratch regeneration** with a manually re-composed prompt (and re-attached reference image for image_to_video) — no server-side lineage, which was the entire differentiator motivating the `omni_flash` backend and the Review-Agent revision tool (phase doc 14b steps 4–5).

### 4. Minimum working SDK version

**2.14.0 tested and sufficient** for everything that works above. Surface-stability notes: the interactions surface is Speakeasy-generated and clearly in motion — `google.genai.types` carries **no** interaction request types (only `ReplayInteraction*`; the real typed models live in the separate `google.genai.interactions` module, 440 symbols), `create` is an untyped `**body` passthrough validated server-side, error messages reference an internal "steps-based API version" migration (turn_list → step_list), and `get` 500s on sync-created ids. Treat any pin as a floor (`google-genai>=2.14.0`) and expect breakage across minor versions while the surface settles.

### 5. GO / NO-GO recommendation

**NO-GO** for building the `omni_flash` backend now (per the phase doc's "evaluate, not adopt" framing). Reasons:

1. **The value proposition is unavailable.** Conversational revision via `previous_interaction_id` — the reason to add an Omni backend plus a Review-Agent revision tool at all — is explicitly rejected: *"gemini-omni-flash-preview on this path do not support previous_interaction_id."* Without lineage, `omni_flash` is just a second text/image→video generator that duplicates what Veo 3.1 already does.
2. **Output quality ceiling below the incumbent:** fixed 4s / 24fps / 720p-class output vs Veo 3.1's longer, 1080p-capable output; no validated duration/aspect/config knobs (`response_modalities` rejected; `response_format`/`generation_config` untested in this bounded probe).
3. **Surface instability:** preview model, `get` 500s on sync interactions, mid-migration API ("steps-based" vs "turn_list"), request types not yet in `google.genai.types`.

What the prototype DID prove (bank this for the revisit): text_to_video and image_to_video both work today with trivially simple request shapes; background mode + `get` polling works and completed in ~30s (dramatically faster than Veo's minutes); reference images genuinely condition the output. **Unblocking condition to revisit:** `previous_interaction_id` (or an equivalent documented revision mechanism) supported for the Omni video path, ideally alongside GA/stabilization of the interactions surface — then 14b steps 4–6 become worth building on the shapes recorded here.
