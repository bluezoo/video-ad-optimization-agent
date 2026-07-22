# Scenario F1 verification report — fashion regression gate (workstream 09)

- Date: 2026-07-22
- Scenario doc: `docs/demo-scenarios/fashion.md`, Scenario F1 (Scenes 1 + 2)
- Worktree: `.claude/worktrees/version_2_prompt-generalization` (branch `version_2`, ws09 changes present: `app/tools/prompt_archetypes.py` + refactored `app/tools/prompt_builders.py`)
- Server: `make dev` on :8501, fresh DB (campaigns.db deleted before start; log shows `[DB] Populated 22 products`)
- Session: `c6cadc66-72f0-4a73-9d21-edce17a33c57` (adk web UI, evidence cross-checked against the session-events API)

## Scene 1 — campaign listing (routing sanity check)

- Query: `Show me all campaigns`
- Expected: coordinator routes to Campaign Agent; `list_campaigns` fires with no args; response lists the 4 seeded campaigns incl. `sage-satin-camisole - The Grove`; no tool errors.
- Observed tool calls (from session events):
  1. `transfer_to_agent(agent_name="campaign_agent")`
  2. `list_campaigns()` — args `{}` → response `{"status": "success", "total_count": 4, ...}` with campaigns:
     Blue Floral Maxi Dress - Westfield Century City (id 1), Elegant Black Cocktail Dress - Bloomingdale's 59th Street (id 2), Black High Waist Trousers - Water Tower Place (id 3), **Sage Satin Camisole - The Grove (id 4, product sage-satin-camisole, product_id 21)**.
- No extra leftover campaigns (fresh DB). No error strings in any tool response; no tracebacks in the server log.
- **Result: PASS**
- Evidence: `F1-scene1-trace-listcampaigns.png` (Events trace: transfer + list_campaigns() call/response), `F1-scene1-response.png` (final agent reply incl. Sage Satin Camisole entry).

## Scene 2 — two-stage video generation (release gate + ws09 fashion-prompt regression)

- Query: `Generate 1 new video for the sage-satin-camisole product using the two-stage pipeline. Use a studio setting with an elegant mood.`
- Expected: `generate_video_from_product` or `generate_video_with_variation` (Media Agent) with product = sage-satin-camisole, studio/elegant variation; Stage 1 scene image then Stage 2 Veo; success with filename `sage-satin-camisole-<MMDDYY>-<variation>.mp4`, status generated/pending review, no exceptions. ws09 addition: Stage-1 scene prompt must still be the fashion **with-model** prompt (model/garment language).
- Observed tool calls:
  1. `transfer_to_agent(agent_name="media_agent")`
  2. `generate_video_with_variation(product_id=21, campaign_id=4, setting="studio", mood="elegant")` — the doc's explicitly acceptable alternative to `generate_video_from_product` (and internally it drives `generate_video_from_product`, per the debug log).
- Observed tool response (key fields): `status: "success"`, video id 11, `video_filename: "sage-satin-camisole-072226-diverse-studio-elegant.mp4"` (matches `sage-satin-camisole-<MMDDYY>-<variation>.mp4`, MMDDYY=072226), `variation: "diverse-studio-elegant"`, `pipeline: "two-stage"`, `duration_seconds: 8`, `generation_time_seconds: 165`, `status: "generated"`, `artifact_saved: true`, `reference_image_used: true`.
- Observed pipeline in server log: Stage 1 `gemini-3-pro-image:generateContent` 200 OK (scene image 1,224,399 bytes, product reference image included) → Stage 2 `veo-3.1-generate-001:predictLongRunning` + `fetchPredictOperation` polling, operation completed after 80s, video 2,650,264 bytes, saved to `gs://kaggle-on-gcp-ad-campaign-assets/generated/sage-satin-camisole-072226-diverse-studio-elegant.mp4`. No exception text anywhere in the response, trace, or server log.

### ws09 regression check — Stage-1 prompt is still the fashion with-model prompt

Scene prompt as observed in the runtime trace/tool response (tool truncates at 200 chars):

> "Cinematic fashion photography of a confident, radiant **woman** with a warm, engaging presence **wearing** a stunning soft sage green silky satin drapey **camisole**.\n\nShe is mid-stride in an elegant walking pose..."

Video prompt (runtime excerpt):

> "The **model** walks gracefully forward, the **garment** flowing with each step. Camera slowly orbits around the model, showcasing the garment's movement, drape, and fabric flow..."

Contains the required model/garment language ("woman", "wearing", "she is", "model", "garment") — the wearable path did NOT become a product-only prompt. Full prompts (rebuilt deterministically via `app.tools.prompt_builders.build_scene_image_prompt`/`build_video_animation_prompt` with the exact runtime inputs — product_id 21, `CreativeVariation(name="diverse-studio-elegant", setting="studio", mood="elegant")` — first 200 chars byte-identical to the runtime excerpt) are in `F1-scene2-prompts.txt`; they include the studio setting language ("minimalist professional photography studio") and the with-model preamble. The Stage-1 scene image visible in the trace (see `F1-scene2-trace-toolcall.png`) shows a model wearing the sage camisole in a studio — visual confirmation.

- **Result: PASS** (including the ws09 regression assertion)
- Evidence: `F1-scene2-trace-toolcall.png` (function-call args tooltip: setting/product_id/mood/campaign_id + Stage-1 scene image), `F1-scene2-response.png` (final reply: variation, two-stage pipeline, status generated/pending review, GCS paths, video artifact rendered in UI), `F1-scene2-prompts.txt` (runtime prompt excerpts + full rebuilt prompts).

## Verdict

**Scenario F1: 2/2 scenes PASS.** Fashion (wearable) path behaviorally unchanged post-archetype-registry refactor; two-stage pipeline succeeded end to end (Stage 1 ~30s, Stage 2 Veo 80s, total 165s). No anomalies in the server log. Server left running on :8501 for the next scenario.
