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
  and the other 3 seeded demo campaigns; extra campaigns left over from prior
  local runs are tolerated (note them, don't fail on them). No tool errors in
  the trace.

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

## Scenario F2: Analytics chart with defaults (workstream 02 regression)

Covers the Phase 1 fixes: valid default metric and the no-data guard.

### Scene F2.1 — Chart with default metric

**Query:** "Show me a performance chart for the Blue Floral Maxi Dress campaign"

**Expected tool calls:**
- `generate_metrics_visualization` with `campaign_id` resolved to the Blue
  Floral Maxi Dress campaign; `metric` argument either omitted (default
  `revenue_per_impression`) or an explicit valid value — the response must
  NOT contain "Invalid metric".

**Pass criteria:**
- Tool response has `status: "success"` and a chart artifact is rendered
  in the UI (screenshot as evidence).

### Scene F2.2 — Campaign with no activated-video metrics

**Query 1:** "Create a campaign for product 1 at Test Mall in Austin, Texas,
then show me its performance chart"

**Query 2 (follow-up turn, required):** "Generate the trendline chart for that
campaign anyway"

**Expected tool calls:**
- `create_campaign(product_id=1, store_name="Test Mall", city="Austin", state="Texas"|"TX")`
- After Query 1 the analytics agent may legitimately short-circuit via
  `get_campaign_metrics` (sees 0 activated videos, relays guidance) without
  charting — that path is acceptable for Query 1.
- Query 2 must invoke `generate_metrics_visualization` for the new campaign's
  id — this is the regression guard under test.

**Pass criteria:**
- No crash/traceback in any tool response; `generate_metrics_visualization`
  returns the clean error ("No metrics data available … activate videos
  first") and the agent relays that guidance (e.g. pointing at
  review/activation).
