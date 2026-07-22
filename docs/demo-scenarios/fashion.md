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
number the agent reports must be internally consistent under the revenue model
(revenue = impressions × a deterministic per-creative RPI in [0.03, 0.07] (base `DEMO_RPI` × seeded factor — workstream 07), so each creative's ratio is one stable constant).

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

**Pass criteria (the workstream-05/07 assertion — check the arithmetic, don't
trust prose):**
- For every ad row reported: `revenue ≈ impressions × its reported RPI`
  (within cent rounding), and that RPI lies within [0.03, 0.07] (per-creative
  deterministic band — workstream 07 replaced the flat 0.05 with a seeded
  per-creative constant).
- In a multi-creative campaign, the reported RPIs are NOT all identical
  (at least two distinct values) — all-identical ratios would mean the
  per-creative factor regressed to flat.
- Impressions are non-zero for the activated video.
- FAIL if any row's revenue/impressions ratio disagrees with its own reported
  RPI beyond rounding — that would mean a non-deterministic or legacy
  generator path survived.

## Scenario F4: Creative comparison chart (workstream 07)

Covers Phase 7: creative-level RPI comparison and the deterministic
(matplotlib, not AI-drawn) chart tool.

### Scene F4.1 — which creative is winning

**Query:** "Which of the creatives in the Sage Satin Camisole campaign is
winning? Show me a comparison chart."

**Expected tool calls:**
- `compare_creatives_within_campaign(campaign_id=<resolved id>)` and/or
  `generate_creative_comparison_chart(campaign_id=<resolved id>)` — the chart
  tool embeds the comparison payload, so either order (or the chart tool
  alone) is acceptable, but the CHART tool must fire since a chart was asked
  for.

**Pass criteria (check the arithmetic):**
- A chart artifact renders in the UI (PNG; screenshot as evidence) and the
  tool response has `artifact_saved: true`.
- The response names a winner whose RPI is the maximum of the reported
  per-creative RPIs.
- Every reported creative satisfies `revenue ≈ impressions × RPI` (cent
  rounding), RPIs lie in [0.03, 0.07], and are not all identical.
- `chart.chart_data.labels`/`rpi_values` in the tool response match the
  `comparison.creatives` payload exactly (same order, same numbers).

## Scenario F5: Non-fashion product campaign (workstream 08)

Covers Phase 8: the typed vertical-agnostic Product model and the deliberate
campaign-category behavior, exercised through the multi-vertical retail core
test set (seeded at startup alongside the fashion catalog).

### Scene F5.1 — browse and create a campaign for a beverage product

**Query 1:** "List the beverage products"

**Query 2 (follow-up turn):** "Create a campaign for the Aurora cold brew at
Target Downtown in Austin, Texas"

**Expected tool calls:**
- Query 1: `list_products(category="beverage")` → includes
  `aurora-cold-brew-330ml` (and `citrus-grove-sparkling-water-500ml`); no
  crash on the non-fashion rows (style/color/fabric are null for them).
- Query 2: `create_campaign(product_id=<resolved id>, store_name="Target
  Downtown", city="Austin", state="Texas"|"TX")` (explicit `category` may be
  present only if it is a valid theme value).

**Pass criteria (check the values, not prose):**
- Campaign created with `status: "success"`, `category: "always-on"` (the
  deliberate non-fashion default — FAIL if it is "essentials", which would
  mean the old silent fallback survived).
- The campaign description mentions the product (e.g. "Aurora Cold Brew")
  and does NOT contain "fashion item" or "classic".
- No traceback anywhere; product fields in responses are populated from the
  typed model (name/category present; no literal "None" strings).

### Scene F5.2 — non-fashion video generation (workstream 09)

**Query:** "Generate a video for the Aurora cold brew using a studio setting"

**Expected tool calls:**
- `generate_video_from_product` or `generate_video_with_variation` for the
  aurora-cold-brew-330ml product (campaign resolved from F5.1's campaign or
  created on the fly). Stage 1 + Stage 2 run (~1-4 min).

**Pass criteria (check the trace, not prose):**
- The scene/creative prompt visible in the trace (or the tool's debug output)
  contains NONE of: "fashion", "garment", "wearing", "model wearing",
  "she is" (case-insensitive) — it must read as a product-centric hero shot
  (condensation/appetite cues for the beverage archetype).
- The tool response surfaces `reference_image_used: false` with a warning that
  no product image exists (retail SKUs ship without images until Phase 14a/15)
  — generation still succeeds from the text description.
- Video registered with status generated/pending review; filename derives from
  a product-centric variation name (e.g. `beverage-studio-elegant`), NOT an
  ethnicity-prefixed name.
- FAIL if: a human model appears in the prompt text, any exception in the
  trace, or the old fashion preamble ("model wearing this exact garment")
  appears anywhere.

## Scenario F6: Attribution windows (Phase 10)

Covers Phase 10's playout attribution: activating a video opens deterministic
`video_attribution` windows on the campaign's real screens (2–3, `screen_id !=
ad_campaign_id`), and pausing it closes them.

### Scene F6.1 — activation opens attribution windows

**Setup (required):** the seeded demo DB ships every video already
`activated`, so a fresh-activation path needs a pending video created first.
Before starting the server, insert one synthetic pending video (same fixture
shape the unit tests use — this is scenario setup, not an assertion-time
mutation):

```bash
sqlite3 campaigns.db "INSERT INTO campaign_videos \
  (campaign_id, product_id, video_filename, status) \
  VALUES (1, (SELECT product_id FROM campaigns WHERE id = 1), \
  'f6-scenario-pending.mp4', 'generated');"
```

**Query:** "Show me the pending videos for campaign 1, then activate the
first one."

**Expected tool calls:** `list_pending_videos` (or `get_video_review_table`)
then `activate_video` (for the setup video's id).

**Checks:**
- The activation response reports metrics generated for a 30-day window.
- **DB assertion** (verifier runs via Bash against the local `campaigns.db`):
  `SELECT screen_id, active_to FROM video_attribution WHERE video_id = <id>`
  returns 2–3 rows, every `screen_id != campaign_id`, every `active_to` NULL.

### Scene F6.2 — pausing closes the windows

**Query:** "Pause that video."

**Expected tool call:** `pause_video`.

**Checks:**
- Success response.
- DB assertion: the same rows from F6.1 now all have `active_to` NOT NULL.
