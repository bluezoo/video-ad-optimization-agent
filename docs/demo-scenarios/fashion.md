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

**Steps:**
1. Open `http://localhost:8501`, select the `app` agent.
2. Send: `Show me all campaigns`.
   - **Expect:** a campaign list including `sage-satin-camisole - The Grove`
     (4 demo campaigns total), no tool errors.
3. Send: `Generate 1 new video variation for the sage-satin-camisole campaign.
   Use a studio setting with an elegant mood.`
   - **Expect:** the Media Agent runs the two-stage pipeline — trace shows a
     Stage 1 scene-image generation followed by a Stage 2 Veo animation
     (polling messages are normal; Stage 2 takes ~1-4 minutes).
4. Wait for completion.
   - **Expect:** a success response referencing a generated video (filename
     matching `sage-satin-camisole-<MMDDYY>-<variation>.mp4`), with the video
     stored and registered for review (pending_review status), and no
     exception text anywhere in the response or trace.

**Pass:** all expectations met. **Fail:** any stage errors, times out
(>10 min), or the response contains a model-not-found / permission error.
