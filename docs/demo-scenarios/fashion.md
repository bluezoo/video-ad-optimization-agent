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

Covers the Phase 2 fixes: valid default metric and the no-data guard.

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

## Scenario F3: Deterministic activation metrics (workstream 05 regression)

Covers Phase 5's deterministic demo data: activating a video seeds a full
30-day metrics window from the seeded generator (`app/demo_data/`), and every
number the agent reports must be internally consistent under the flat demo
revenue model (`revenue = impressions × 0.05`, so RPI is exactly 0.05
everywhere by construction).

### Scene F3.1 — deterministic 30-day window and anchor extension

> Note: the seeded demo DB activates all its videos up front (base behavior,
> `app/database/mock_data.py`), so there is nothing pending to activate in a
> fresh DB — HITL activation seeding is covered by unit tests
> (`tests/unit/test_review_tools.py::TestDeterministicActivation`) and only
> occurs live after a real Veo generation (Scenario F1). This scene instead
> asserts the seeded window and the anchor-advancing extension path.

**Query 1:** "What's the status of video 1, including how many days of
metrics it has?"

**Query 2 (follow-up turn):** "Generate 3 more days of metrics for video 1"

**Query 3 (follow-up turn):** "Check video 1's status again — how many days
of metrics now?"

**Expected tool calls:**
- Query 1: `get_video_status(video_id=1)` or `get_video_details(1)` (the
  latter returns a superset — either is acceptable) → status "activated",
  30 metric days (`metrics_count`/`days_tracked` — must be 30, not 7).
- Query 2: `generate_additional_metrics(video_id=1, days=3)` →
  `status: "success"`, `days_generated: 3`.
- Query 3: same status tool again → 33 metric days.

**Pass criteria:**
- The counts are exactly 30 → +3 → 33; no response mentions random
  generation; no crash/traceback in any response.

### Scene F3.2 — reported numbers are internally consistent (RPI = 0.05)

**Query:** "Give me the top performing ads for that campaign, with their
impressions, revenue and RPI" (same campaign as video 1 from F3.1 — its
campaign name/id comes back in the Query 1 response there).

**Expected tool calls:**
- `get_top_performing_ads` (or `get_campaign_metrics`/`get_campaign_insights`
  for the same campaign — any of these is acceptable so long as per-ad or
  campaign totals with impressions + revenue + RPI come back).

**Pass criteria (the workstream-05 assertion — check the arithmetic, don't
trust prose):**
- For every ad/total row reported: `revenue ≈ impressions × 0.05` (within
  rounding to cents) and any reported RPI value is 0.05 (±0.001).
- Impressions are non-zero for the activated video.
- FAIL if any row's revenue/impressions ratio deviates from 0.05 beyond
  rounding — that would mean a non-deterministic or legacy generator path
  survived.
