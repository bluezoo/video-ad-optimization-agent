# Stage 4 — Owner calibration gate (Tasks 6-10, Step 1+2)

Recorded actuals for all 5 eval sets via `record_actuals.py` against the real
Coordinator (Vertex, `app/.env` project), one live run per set, no retries
needed — every case returned `inference_ok: true`. Raw recordings:
`calibration/{coordinator,campaign_agent,media_agent,analytics_agent,review_agent}-actual.json`.

**Recorder status: no fix needed.** `eval_harness.py` and `record_actuals.py`
ran cleanly for all 5 sets / 16 cases on the first try. No code change made.

## Top-line findings (read this first)

1. **`transfer_to_agent` shape confirmed** exactly as the plan predicted:
   `{"name": "transfer_to_agent", "args": {"agent_name": "<agent>"}}` as an
   ordinary `tool_uses` entry, always first (or interspersed on multi-hop
   turns). Consistent across all 16 cases.
2. **Surprising calibration nuance:** the `tools`/`trajectory` dimensions
   (ANY_ORDER / IN_ORDER, threshold 1.0) already **pass today** on 10 of 16
   cases even against the OLD reference (no `transfer_to_agent`, no updated
   args) — the ADK trajectory evaluator treats the reference as a required
   *subsequence*, so extra actual calls (like the routing hop) don't fail it.
   Adding `transfer_to_agent` to the pinned reference is therefore about
   **documentation accuracy**, not about making these 10 cases pass — they
   already pass. The 6 that fail today fail for other, more interesting
   reasons (below), not because of the missing `transfer_to_agent` entry.
3. **Real bug — duplicate product on cold-start create-campaign**
   (`campaign_agent` / `create-campaign-beverage`): asking to create a
   campaign for "the Aurora cold brew" (a SEEDED product, id 23) makes the
   agent bounce `campaign_agent → media_agent → campaign_agent`, then call
   `create_product` for a brand-new "Aurora Cold Brew 330ml" (id **399**) and
   `generate_product_image`, then `create_campaign(product_id=399)` — instead
   of resolving the existing product 23. This is the same failure mode ws14's
   WORK_LOG documented as a candidate regression (Task 11). Needs an owner
   call: fix the agent now vs. pin as a documented regression.
4. **Real bug — Google Maps query misrouted away from `analytics_agent`**
   (`analytics_agent` / `get-map-data`): the query "Show me all campaign
   locations with Google Maps links" is textbook language from
   `analytics_agent`'s own instructions ("Use this when users ask 'show me
   campaign locations'"), and `get_campaign_map_data` (the tool that actually
   produces Google Maps links) lives only on `analytics_agent`
   (`app/agent.py:417`). But live routing sent it to `campaign_agent`
   instead, which called `get_campaign_locations` + `list_campaigns` — plain
   store addresses, **zero Google Maps links**, i.e. it didn't even answer
   what was asked. This looks like a genuine Coordinator routing bug, not a
   calibration nuance.
5. **Answer-dimension (LLM judge) is inconsistent against empty-string
   references.** 5 of 16 cases have `final_response` pinned as `""` in the
   current eval sets. Against that empty reference, the live judge scored
   1.0 on some cases and 0.0 on others with no discernible difference in
   answer quality (e.g. coordinator's `route-to-media-agent-products` passed
   1.0, `route-to-campaign-agent-list` failed 0.0 — both are well-formed,
   on-topic answers). Empty-string references are not a safe passthrough;
   real "must contain" bullets are needed everywhere (proposed below).
6. **Legacy-tool avoidance surfaced one case** (`review_agent` /
   `list-pending-videos`): the agent's own instruction text
   (`app/agent.py:482`) tells it `list_pending_videos` is "Legacy... use
   get_video_review_table instead", so it never calls the tool the eval set
   pins. It answers correctly, but via 3 tool calls including
   `get_video_review_table` twice (once filtered, once unfiltered) — flagged
   below as a possible tightening opportunity.

Per-set arg-drift (legitimate calls, just need refreshed `args`, no behavior
bug): `list_products(include_urls=true)` (media, case 1),
`get_campaign_metrics(days=30, campaign_id=2)` (analytics, case 1),
`get_top_performing_ads(metric=..., limit=5)` (analytics, case 2).

---

## coordinator.test.json (4 cases)

### `route-to-campaign-agent-list` — "List all campaigns"
- **Actual tools:** `transfer_to_agent(campaign_agent)` → `list_campaigns({})`
- **Actual answer:** "We currently have 4 active product-centric ad
  campaigns: 1. Blue Floral Maxi Dress - Westfield Century City (ID 1,
  product Blue Floral Maxi Dress ID 4, Los Angeles CA, Summer, Active, 3
  videos) 2. Elegant Black Cocktail Dress - Bloomingdale's 59th Street (ID 2,
  ...) 3. Black High Waist Trousers - Water Tower Place (ID 3, ...) 4. Sage
  Satin Camisole - The Grove (ID 4, ...) [...] What would you like to do
  next: view details, create a campaign, or view locations on a map."
- **Dims today:** tools 1.0 pass, trajectory 1.0 pass, answer 0.0 **fail**
  (against empty-string reference — see finding 5).
- **Proposed repaired `tool_uses`:**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "list_campaigns", "args": {}}
  ]
  ```
- **Proposed expected-answer bullets:** lists all 4 campaigns; each entry
  names product + store location (e.g. "Blue Floral Maxi Dress - Westfield
  Century City"); all shown as Active status.
- **Ambiguity:** none on trajectory. Answer-dimension reliability (finding 5)
  applies.

### `route-to-media-agent-products` — "Show me all available products"
- **Actual tools:** `transfer_to_agent(media_agent)` → `list_products({})`
- **Actual answer:** "Here are the available products in the catalog (28
  total): Dresses (6), Tops (5), Pants (5), Outerwear (3), Skirts (3),
  Beverages & Food (3: Aurora Cold Brew, Citrus Grove Sparkling Water, Smoky
  Brisket Stack Sandwich), Electronics & Home (3: earbuds, lounge chair, air
  fryer). [...] Let me know if you'd like to generate a video ad."
- **Dims today:** tools 1.0 pass, trajectory 1.0 pass, answer 1.0 pass.
- **Proposed repaired `tool_uses`:** `transfer_to_agent(media_agent)` →
  `list_products({})` (matches actual exactly, no arg change).
- **Proposed expected-answer bullets:** states 28 total products; groups by
  category (fashion, beverages/food, electronics/home).
- **Ambiguity:** none — already fully green; repair is documentation only.

### `route-to-review-agent-table` — "Show me the video review table"
- **Actual tools:** `transfer_to_agent(review_agent)` →
  `get_video_review_table({})`
- **Actual answer:** Full per-video table (10 videos, each with product,
  location, variation, model/setting/mood, duration, created timestamp).
  "Summary: Pending Activation: 0, Live/Activated: 10, Total Shown: 10."
- **Dims today:** tools 1.0 pass, trajectory 1.0 pass, answer 1.0 pass.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** shows a per-video table; summary line
  states 0 pending / 10 live.
- **Ambiguity:** none.

### `route-to-analytics-agent-metrics` — "Get metrics for campaign 1"
- **Actual tools:** `transfer_to_agent(analytics_agent)` →
  `get_campaign_metrics({campaign_id: 1})`
- **Actual answer:** "Campaign 1: Blue Floral Maxi Dress - Westfield Century
  City, last 30 days: RPI $0.0596 ($59.60/1,000 impressions), Total Revenue
  $8,154.15, Total Impressions 136,728, Total Circulation 648,463, Avg Dwell
  Time 8.1s, 3 active creatives. [...] Next steps: compare creatives,
  generate charts, view locations."
- **Dims today:** tools 1.0 pass, trajectory 1.0 pass, answer 0.0 **fail**
  (empty-string reference — finding 5).
- **Proposed repaired `tool_uses`:** matches actual, no arg change (query
  doesn't specify a day window, so no `days` arg — differs from the
  analytics-set case below which does specify "last 30 days").
- **Proposed expected-answer bullets:** reports RPI for campaign 1 (~$0.0596);
  includes total revenue (~$8,154.15) and impressions (~136,728).
- **Ambiguity:** answer-dimension reliability (finding 5).

---

## campaign_agent.test.json (4 cases)

### `list-all-campaigns` — "What campaigns do we have?"
- **Actual tools:** `transfer_to_agent(campaign_agent)` → `list_campaigns({})`
- **Actual answer:** Same 4-campaign list as coordinator's
  `route-to-campaign-agent-list`, plus a "What would you like to do next"
  footer.
- **Dims today:** tools 1.0, trajectory 1.0, answer 0.0 **fail**.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** lists 4 active campaigns; campaign
  IDs 1-4 all present.
- **Ambiguity:** answer-dimension reliability (finding 5).

### `get-campaign-details` — "Show me the details of campaign 2"
- **Actual tools:** `transfer_to_agent(campaign_agent)` →
  `get_campaign({campaign_id: 2})`
- **Actual answer:** "Campaign #2: Elegant Black Cocktail Dress -
  Bloomingdale's 59th Street, Active, Formal, New York NY, created July 23
  2026. Product: elegant-black-cocktail-dress (ID 12), Dress, Classic Black,
  Fitted cocktail dress. Performance (30 days): 45,627 impressions, 217,016
  circulation, $2,103.43 revenue, $46.10 RPM, 8.2s dwell. Videos (1): Video
  ID 4, diverse-rooftop-sophisticated, Activated, 8s."
- **Dims today:** tools 1.0, trajectory 1.0, answer 0.0 **fail**.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** identifies campaign 2 as "Elegant
  Black Cocktail Dress - Bloomingdale's 59th Street"; includes 30-day
  performance metrics (RPI/RPM ~$46.10 per 1,000, revenue ~$2,103.43).
- **Ambiguity:** answer-dimension reliability (finding 5). Note the answer
  bundles metrics into a campaign_agent response even though
  `get_campaign_metrics` (the metrics tool) lives on `analytics_agent` — the
  campaign detail must already embed metrics server-side (not a routing
  issue, just worth the owner knowing metrics appear here too).

### `get-campaign-locations` — "Show me all store locations"
- **Actual tools:** `transfer_to_agent(campaign_agent)` →
  `get_campaign_locations({})` → `list_campaigns({})` (extra call not in the
  current reference)
- **Actual answer:** All 4 store locations with city/state, campaign name,
  product, status — plus an "expand?" footer.
- **Dims today:** tools 1.0 pass, trajectory 1.0 pass (subsequence match
  tolerates the extra `list_campaigns` call), answer 1.0 pass.
- **Proposed repaired `tool_uses`** (documents the real trajectory
  including the extra call):
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "get_campaign_locations", "args": {}},
    {"name": "list_campaigns", "args": {}}
  ]
  ```
- **Proposed expected-answer bullets:** lists all 4 store locations with
  city/state; names the campaign/product running at each store.
- **Ambiguity — owner decides:** is the trailing `list_campaigns()` call
  legitimate (cross-referencing names) or superfluous chatter that could
  vary run-to-run? If pinned exactly, a future run that skips it would fail
  `trajectory` (EXACT-order dependent on this extra call being present) —
  recommend pinning only the 2-call minimal reference
  (`get_campaign_locations` alone) unless the owner wants the extra call
  locked in.

### `create-campaign-beverage` — "Create a campaign for the Aurora cold brew at Target Downtown in Austin, Texas"
- **Actual tools (7 calls, DB-mutating):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "list_campaigns", "args": {}},
    {"name": "transfer_to_agent", "args": {"agent_name": "media_agent"}},
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "create_product", "args": {"name": "Aurora Cold Brew 330ml", "description": "Cold brew coffee 330ml", "category": "beverage", "attributes": {"volume_ml": 330}}},
    {"name": "generate_product_image", "args": {"product_id": 399}},
    {"name": "create_campaign", "args": {"product_id": 399, "store_name": "Target Downtown", "city": "Austin", "state": "Texas"}}
  ]
  ```
- **Actual answer:** "The campaign for Aurora Cold Brew 330ml at Target
  Downtown in Austin, Texas has been created successfully! Product Onboarded:
  Aurora Cold Brew 330ml (Product ID 399), Beverage, reference image
  generated. Campaign Created: Campaign ID 5, 'Aurora Cold Brew 330Ml -
  Target Downtown', Austin TX, status draft, category always-on. [...] Next
  steps: generate ad videos, activate via Review Agent."
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `create_campaign(product_id=23, ...)` directly — the actual
  run never calls that), answer 1.0 pass (user-facing text reads fine
  either way).
- **THIS IS FINDING 3 (duplicate product bug).** Product id 23
  (`aurora-cold-brew-330ml`) already exists in seed data (confirmed via the
  `list_products` responses above, e.g. media_agent's
  `list-products-beverage` case). The agent never looked it up by name/
  category before creating a near-duplicate (id 399, name "Aurora Cold Brew
  330ml" vs seeded "Aurora Cold Brew (330ml)").
- **Proposed repaired `tool_uses` — OPTION A (fix agent, pin correct
  behavior):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "list_products", "args": {"category": "beverage"}},
    {"name": "create_campaign", "args": {"product_id": 23, "store_name": "Target Downtown", "city": "Austin", "state": "Texas"}}
  ]
  ```
- **Proposed repaired `tool_uses` — OPTION B (pin today's buggy behavior as
  a documented regression, xfail):** the 7-call sequence recorded above,
  verbatim.
- **Proposed expected-answer bullets (either option):** confirms a campaign
  was created for Aurora Cold Brew at Target Downtown, Austin, Texas.
- **OWNER GATE (per plan Task 11's cold-start case, same bug family):**
  (a) fix the campaign_agent/coordinator instructions now to resolve
  existing products before creating one, and pin Option A; or (b) pin Option
  B as a documented regression here and let Task 11's cold-start case (which
  covers the identical bug for a different product) carry the fix decision.
  Recommend NOT fixing twice — whichever this workstream decides here should
  also settle Task 11's open question the same way.

---

## media_agent.test.json (5 cases)

### `list-all-products` — "Show me all available products with their image links"
- **Actual tools:** `transfer_to_agent(media_agent)` →
  `list_products({include_urls: true})`
- **Actual answer:** "Here are all 28 available products in the catalog:"
  followed by category-grouped list, each entry showing an Image Filename
  and Status (Available/Missing) — e.g. "ID 23: aurora-cold-brew-330ml,
  Beverage, aurora-cold-brew-330ml.png (Available)". [...]
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `list_products({})`, no `include_urls`), answer 1.0 pass.
- **Proposed repaired `tool_uses`:**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "media_agent"}},
    {"name": "list_products", "args": {"include_urls": true}}
  ]
  ```
- **Proposed expected-answer bullets:** lists all 28 products; each entry
  includes an image filename and availability status.
- **Ambiguity:** none — this is a straightforward arg-drift fix. The query
  explicitly says "with their image links", so `include_urls: true` is the
  correct call; the original reference was simply under-specified.

### `list-products-by-category` — "List all dress products"
- **Actual tools:** `transfer_to_agent(media_agent)` →
  `list_products({category: "dress"})`
- **Actual answer:** Lists the 6 dress products (Blue Floral Maxi Dress,
  Blue Floral Summer Dress, Elegant Black Cocktail Dress, Emerald Satin Slip
  Dress, Floral Midi Wrap Dress, Rust Boho Peasant Dress) each with style/
  color/fabric.
- **Dims today:** tools 1.0, trajectory 1.0, answer 1.0 — all pass.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** lists the 6 dress products by name;
  each includes style/color/fabric detail.
- **Ambiguity:** none.

### `get-variation-presets` — "What variation presets are available for video generation?"
- **Actual tools:** `transfer_to_agent(media_agent)` →
  `get_variation_presets({})`
- **Actual answer:** Diversity presets (5), Settings presets (5), Moods
  presets (5), plus a "Custom Parameter Options" section listing
  presentation mode, ethnicity, setting, mood, lighting, activity, camera
  movement, time of day, visual style, energy.
- **Dims today:** tools 1.0, trajectory 1.0, answer 1.0 — all pass.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** lists diversity/settings/mood preset
  categories; mentions customizable parameters (model ethnicity, setting,
  mood, lighting, activity).
- **Ambiguity:** none.

### `list-campaign-videos` — "List all videos for campaign 1"
- **Actual tools:** `transfer_to_agent(media_agent)` →
  `list_campaign_videos({campaign_id: 1})`
- **Actual answer:** Lists 3 videos for campaign 1 (Blue Floral Maxi Dress -
  Westfield Century City), each with variation name (asian-beach-romantic,
  european-urban-bold, latina-beach-romantic), model/setting/mood, status
  "activated", 8s duration, filename.
- **Dims today:** tools 1.0, trajectory 1.0, answer 1.0 — all pass.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** lists 3 videos for campaign 1; each
  shows a variation name and "activated" status.
- **Ambiguity:** none.

### `list-products-beverage` — "List the beverage products"
- **Actual tools:** `transfer_to_agent(media_agent)` →
  `list_products({category: "beverage"})`
- **Actual answer:** "Aurora Cold Brew (330ml), Product ID 23, filename
  aurora-cold-brew-330ml.png, Available. Citrus Grove Sparkling Water
  (500ml), Product ID 24, filename citrus-grove-sparkling-water-500ml.png,
  Missing."
- **Dims today:** tools 1.0, trajectory 1.0, answer 1.0 — all pass.
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** lists 2 beverage products (Aurora
  Cold Brew, product id 23; Citrus Grove Sparkling Water, product id 24).
- **Ambiguity:** none. (Confirms product id 23 for Aurora Cold Brew is
  correctly seeded — supports Option A of the `create-campaign-beverage`
  fix above.)

---

## analytics_agent.test.json (4 cases)

### `get-campaign-metrics` — "Get metrics for campaign 2 over the last 30 days"
- **Actual tools:** `transfer_to_agent(analytics_agent)` →
  `get_campaign_metrics({campaign_id: 2, days: 30})`
- **Actual answer:** "Campaign 2: Elegant Black Cocktail Dress -
  Bloomingdale's 59th Street, last 30 days: RPI $0.0461, Total Revenue
  $2,103.43. [...]"
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `{campaign_id: 2}` only, missing `days`), answer 0.0
  **fail** (empty-string reference — finding 5).
- **Proposed repaired `tool_uses`:**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "analytics_agent"}},
    {"name": "get_campaign_metrics", "args": {"campaign_id": 2, "days": 30}}
  ]
  ```
- **Proposed expected-answer bullets:** reports RPI for campaign 2
  (~$0.0461); includes 30-day revenue (~$2,103.43) and impressions
  (~45,627).
- **Ambiguity:** none on the arg fix (query explicitly says "over the last
  30 days"). Answer-dimension reliability (finding 5) applies.

### `get-top-performers` — "Show me the top 5 performing videos by RPI"
- **Actual tools:** `transfer_to_agent(analytics_agent)` →
  `get_top_performing_ads({metric: "revenue_per_impression", limit: 5})`
- **Actual answer:** Ranked table of top 5 videos by RPI, columns: Rank,
  Video/Product, Campaign & Location, Variation Traits, RPI, Impressions,
  Total Revenue, Dwell Time.
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `{}`), answer 1.0 pass.
- **Proposed repaired `tool_uses`:**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "analytics_agent"}},
    {"name": "get_top_performing_ads", "args": {"metric": "revenue_per_impression", "limit": 5}}
  ]
  ```
- **Proposed expected-answer bullets:** returns a ranked table of the top 5
  videos by RPI; includes campaign/location and variation traits per row.
- **Ambiguity:** none — `metric`/`limit` are the tool's own defaults made
  explicit by the model; harmless arg drift.

### `compare-campaigns` — "Compare campaigns 1, 2, 3, and 4"
- **Actual tools:** `transfer_to_agent(analytics_agent)` →
  `compare_campaigns({campaign_ids: [1, 2, 3, 4]})`
- **Actual answer:** Ranked comparison table across campaigns 1-4 by RPI,
  identifying "Blue Floral Maxi Dress - Westfield Century City" as the best
  performer.
- **Dims today:** tools 1.0, trajectory 1.0, answer 1.0 — all pass.
- **Proposed repaired `tool_uses`:** matches actual exactly (already
  correctly pinned today).
- **Proposed expected-answer bullets:** compares campaigns 1, 2, 3, 4 ranked
  by RPI; names the best performer.
- **Ambiguity:** none.

### `get-map-data` — "Show me all campaign locations with Google Maps links"
- **Actual tools (MISROUTED — see finding 4):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
    {"name": "get_campaign_locations", "args": {}},
    {"name": "list_campaigns", "args": {}}
  ]
  ```
- **Actual answer:** "Here are all the current campaign locations along with
  direct Google Maps links: 1. Blue Floral Maxi Dress - Westfield Century
  City, Los Angeles CA, Summer, Google Maps Link: [Westfield Century City
  on Google Maps] [...]" — **the answer TEXT claims Maps links exist, but
  neither `get_campaign_locations` nor `list_campaigns` returns Maps URLs**;
  worth the owner double-checking whether the link is a real URL or a
  fabricated-looking placeholder, since the correct tool
  (`get_campaign_map_data`) was never called.
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `get_campaign_map_data({})` on presumably `analytics_agent`
  routing), answer 1.0 pass (the judge didn't catch the missing-tool issue
  since the text still mentions "Google Maps Link").
- **Proposed repaired `tool_uses` — OPTION A (fix routing, pin correct
  behavior; matches `analytics_agent`'s own instructions and the tool's
  actual owner):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "analytics_agent"}},
    {"name": "get_campaign_map_data", "args": {}}
  ]
  ```
- **Proposed repaired `tool_uses` — OPTION B (pin today's misrouted
  behavior as a documented regression, xfail):** the 3-call
  `campaign_agent` sequence recorded above.
- **Proposed expected-answer bullets (Option A):** lists all 4 campaign
  locations; each includes a clickable Google Maps URL.
- **OWNER GATE:** this is the most consequential finding in the batch — a
  live, reproducible Coordinator routing miss on a query that matches
  `analytics_agent`'s own documented trigger phrase almost verbatim. Needs a
  decision: (a) fix the Coordinator/`campaign_agent` instructions now (likely
  a real product bug worth fixing regardless of this eval set), or (b) pin
  Option B as a known regression and open a follow-up issue. Recommend (a)
  if in scope for this workstream, since users asking for "Maps links" today
  silently get a worse answer with no Maps links at all.

---

## review_agent.test.json (3 cases)

### `show-review-table` — "Show me the video review table with public links"
- **Actual tools:** `transfer_to_agent(review_agent)` →
  `get_video_review_table({})`
- **Actual answer:** Same per-video table as coordinator's
  `route-to-review-agent-table` case (10 videos, 0 pending / 10 live
  summary).
- **Dims today:** tools 1.0, trajectory 1.0, answer 0.0 **fail**
  (empty-string reference — finding 5).
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** shows a per-video table; summary
  states 0 pending / 10 live.
- **Ambiguity:** query says "with public links" but no URLs appear in the
  visible table header/columns shown in the truncated answer — worth the
  owner confirming the full table (not shown here in full) actually includes
  public link columns; not verifiable from the truncated excerpt alone.

### `get-activation-summary` — "What's the activation summary?"
- **Actual tools:** `transfer_to_agent(review_agent)` →
  `get_activation_summary({})`
- **Actual answer:** "Total Videos: 10, Live/Activated: 10, Pending Review:
  0, Paused: 0, Archived: 0. All generated videos are currently live and
  active."
- **Dims today:** tools 1.0, trajectory 1.0, answer 0.0 **fail**
  (empty-string reference — finding 5).
- **Proposed repaired `tool_uses`:** matches actual, no arg change.
- **Proposed expected-answer bullets:** reports 10 total videos, 10 live, 0
  pending, 0 paused, 0 archived.
- **Ambiguity:** answer-dimension reliability (finding 5).

### `list-pending-videos` — "Show me all pending videos"
- **Actual tools (3 calls, NOT `list_pending_videos` — see finding 6):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "review_agent"}},
    {"name": "get_video_review_table", "args": {"status": "generated"}},
    {"name": "get_activation_summary", "args": {}},
    {"name": "get_video_review_table", "args": {}}
  ]
  ```
- **Actual answer:** "There are currently 0 pending videos awaiting review
  or activation. All 10 existing videos in the system are currently LIVE
  (activated): Videos #1-3: Blue Floral Maxi Dress (Westfield Century City,
  Los Angeles) [...]"
- **Dims today:** tools 0.0 **fail**, trajectory 0.0 **fail** (current
  reference pins `list_pending_videos({})`, never called), answer 1.0 pass.
- **Root cause:** `app/agent.py:482` tells the model `list_pending_videos()`
  is "Legacy list (use get_video_review_table instead)" — the model is
  correctly following its own instructions by avoiding it.
- **Proposed repaired `tool_uses` — OPTION A (pin the real 4-call
  trajectory verbatim, including the redundant second
  `get_video_review_table()` call):** as recorded above.
- **Proposed repaired `tool_uses` — OPTION B (tighter, single-call
  reference, if the owner considers the double review-table call
  unnecessary verbosity worth instructing away):**
  ```json
  [
    {"name": "transfer_to_agent", "args": {"agent_name": "review_agent"}},
    {"name": "get_video_review_table", "args": {"status": "generated"}}
  ]
  ```
- **Proposed expected-answer bullets:** confirms 0 pending videos; notes all
  10 videos are currently live.
- **OWNER GATE:** (a) is calling `get_video_review_table` twice (filtered
  then unfiltered) and `get_activation_summary` in between acceptable/
  expected for this query, or should the agent instruction be tightened to
  make a single filtered call suffice? (b) should the eval set still
  reference `list_pending_videos` at all given the agent's own instructions
  now deprecate it — recommend dropping it from the pinned reference
  regardless of (a)'s answer, since re-adding the legacy tool call would
  fight the agent's own documented preference.

---

## Summary table (dims today, before any repair)

| Set | Case | tools | trajectory | answer |
|---|---|---|---|---|
| coordinator | route-to-campaign-agent-list | pass | pass | **fail** |
| coordinator | route-to-media-agent-products | pass | pass | pass |
| coordinator | route-to-review-agent-table | pass | pass | pass |
| coordinator | route-to-analytics-agent-metrics | pass | pass | **fail** |
| campaign_agent | list-all-campaigns | pass | pass | **fail** |
| campaign_agent | get-campaign-details | pass | pass | **fail** |
| campaign_agent | get-campaign-locations | pass | pass | pass |
| campaign_agent | create-campaign-beverage | **fail** | **fail** | pass |
| media_agent | list-all-products | **fail** | **fail** | pass |
| media_agent | list-products-by-category | pass | pass | pass |
| media_agent | get-variation-presets | pass | pass | pass |
| media_agent | list-campaign-videos | pass | pass | pass |
| media_agent | list-products-beverage | pass | pass | pass |
| analytics_agent | get-campaign-metrics | **fail** | **fail** | **fail** |
| analytics_agent | get-top-performers | **fail** | **fail** | pass |
| analytics_agent | compare-campaigns | pass | pass | pass |
| analytics_agent | get-map-data | **fail** | **fail** | pass |
| review_agent | show-review-table | pass | pass | **fail** |
| review_agent | get-activation-summary | pass | pass | **fail** |
| review_agent | list-pending-videos | **fail** | **fail** | pass |

16 cases, 6 tools/trajectory failures (all arg-drift or real bugs, none
caused by the missing `transfer_to_agent` entry), 7 answer-dimension
failures (all against empty-string references — finding 5).
