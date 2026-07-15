# Demo Scenarios — Fashion (current default vertical)

Scenario files under `docs/demo-scenarios/` are executable scripts for the
`demo-scenario-verifier` subagent (see `.claude/agents/`), driven through a
local `make dev` instance (adk web, port 8501) via chrome-devtools MCP.
Modeled on `DEMO_GUIDE.md` (which stays the fashion-specific, client-facing
walkthrough — this file is the automation-facing distillation).

Prereqs for all scenarios: `app/.env` configured (Vertex path, location
`global`), `make dev` running on :8501, demo DB populated (delete
`campaigns.db` and restart `make dev` to repopulate).

## Scenario F1: End-to-end video generation (Stage 1 + Stage 2)

**Purpose:** Proves the media pipeline works against the configured
image/video models — the release gate for any model-config change.

**Scene 1 — campaign listing (routing sanity check)**

- Query: `Show me all campaigns`
- Expected tool call: `list_campaigns` (Campaign Agent; coordinator must route
  there, not answer from memory). Arguments: none/defaults.
- Expected response: a campaign list including `sage-satin-camisole - The Grove`
  (4 demo campaigns total), no tool errors in the trace.

**Scene 2 — two-stage video generation (the release gate)**

- Query: `Generate 1 new video for the sage-satin-camisole product using the
  two-stage pipeline. Use a studio setting with an elegant mood.`
- Expected tool call: `generate_video_from_product` (Media Agent; primary
  two-stage pipeline — `generate_video_with_variation` is also acceptable).
  Arguments: product identifying `sage-satin-camisole`; variation parameters
  reflecting studio/elegant.
- Expected trace: Stage 1 scene-image generation, then Stage 2 Veo animation
  (polling debug lines are normal; Stage 2 takes ~1-4 minutes).
- Expected response: success referencing a generated video (filename matching
  `sage-satin-camisole-<MMDDYY>-<variation>.mp4`), video registered with
  status `generated`/pending review, and no exception text anywhere in the
  response or trace.

**Pass:** both scenes' expected tools fired with sane arguments and responses
match. **Fail:** wrong/no tool fired, any stage errors, timeout (>10 min), or
a model-not-found / permission error anywhere.
