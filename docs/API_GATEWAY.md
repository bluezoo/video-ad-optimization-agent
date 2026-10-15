# UX API Gateway Reference (`app/api_gateway.py`)

This document is the frontend integration guide for porting the **Ad Video Optimization Agent** foundation into a web application UX. Every feature and 6-step workflow depicted in [`assets/use-case-poster.jpeg`](../assets/use-case-poster.jpeg), all **15+ configurable video generation components** (subjects, settings, tone/mood, lighting, camera, props, audio), and all **12 dataset views** are exposed under `/api/v1/*`.

---

## Quick Start

```bash
# Run the API Gateway on http://localhost:8000
make api

# Or run directly with a custom port:
python -m app.api_gateway --port 8000
```

- **Interactive Swagger UI** (when `fastapi` is installed): `http://localhost:8000/docs`
- **OpenAPI JSON Spec**: `http://localhost:8000/openapi.json`
- **Zero-Dependency Fallback**: If `fastapi`/`uvicorn` are not installed in the active Python environment, `python -m app.api_gateway` automatically runs a built-in multi-threaded HTTP server with full CORS support (`Access-Control-Allow-Origin: *`) and identical JSON routing.

---

## Poster Use-Case Mapping (`assets/use-case-poster.jpeg` -> UX Routes)

| Poster Section / Step | Agent Badge | Sample Poster Prompt | Primary UX Endpoints |
|---|---|---|---|
| **Hero / Outcome Banner** | All Agents | — | `GET /api/v1/overview`, `GET /api/v1/use-cases`, `GET /api/v1/health` |
| **1. Discover Your AI Team** | `All Agents` | *"What agents are available and what are our current campaigns?"* | `GET /api/v1/discover`, `GET /api/v1/agents`, `GET /api/v1/campaigns`, `GET /api/v1/products`, `POST /api/v1/agents/chat` |
| **2. Generate Creative at Scale** | `Media Agent` | *"Generate a video with a European model on a rooftop at sunset, sophisticated mood"* | `GET /api/v1/videos/options`, `GET /api/v1/videos/presets`, `POST /api/v1/videos/prompts/preview`, `POST /api/v1/videos/generate`, `POST /api/v1/videos/generate/batch` |
| **3. You Stay in Control (HITL)** | `Review Agent` | *"Activate videos 5 and 7"* | `GET /api/v1/review/table`, `GET /api/v1/review/pending`, `GET /api/v1/review/summary`, `POST /api/v1/videos/{id}/activate`, `POST /api/v1/videos/activate-batch`, `POST /api/v1/videos/{id}/pause`, `POST /api/v1/videos/{id}/archive`, `POST /api/v1/videos/{id}/edit` |
| **4. Measure What Matters** | `Analytics Agent` | *"Which videos have the highest RPI?"* | `GET /api/v1/analytics/overview`, `GET /api/v1/analytics/top-ads?metric=rpi`, `GET /api/v1/analytics/campaigns/{id}/metrics`, `GET /api/v1/analytics/campaigns/{id}/insights`, `GET /api/v1/analytics/campaigns/{id}/creatives`, `POST /api/v1/analytics/campaigns/{id}/creatives/chart` |
| **5. See the Big Picture** | `Analytics Agent` | *"Compare West Coast vs East Coast performance"* | `GET /api/v1/maps/regions`, `GET /api/v1/maps/campaigns`, `GET /api/v1/maps/locations`, `POST /api/v1/maps/static`, `GET /api/v1/maps/demographics` |
| **6. Scale What Works** | `Media Agent` | *"Apply the winning formula from video 5 to campaign 3"* | `GET /api/v1/optimization/winning-formula`, `POST /api/v1/optimization/apply-winning-formula` |
| **Dataset Explorer** | System / Data | — | `GET /api/v1/datasets`, `GET /api/v1/datasets/{dataset_name}`, `POST /api/v1/datasets/seed`, `POST /api/v1/datasets/reset` |

---

## Detailed Endpoint Reference

### 1. Overview, Health & Workflow Blueprint

- **`GET /api/v1/health`**
  Returns gateway version, `app_mode` (`demo` or `connected`), `demo_dataset` (`fashion` or `none`), active Gemini/Veo model IDs, and live row counts.
- **`GET /api/v1/overview`**
  Returns the poster's hero highlights (`10x Faster Creative Production`, `100s of Personalized Videos`, `4 AI Agents Working Together`), Old Way (`4-6 weeks`) vs. New Way (`<10 minutes`), live KPI totals (`overall_rpi`, `total_revenue`, `total_impressions`, `avg_dwell_time_seconds`, `total_circulation`), and the 6 workflow steps.
- **`GET /api/v1/use-cases`** (alias `GET /api/v1/workflow/steps`)
  Returns the 6 structured workflow steps from the poster, including their badges, highlights, sample prompts, and UX route bindings.

---

### 2. Step 1: Discover Your AI Team (`All Agents`), Campaigns & Products

- **`GET /api/v1/discover`**
  Single-request bootstrap payload for Step 1: returns all 4 specialized agents + coordinator, active campaigns, product catalog breakdown by category, and starter prompts.
- **`GET /api/v1/agents`** & **`GET /api/v1/agents/{agent_name}`**
  Metadata, capabilities, model IDs, sample prompts, and tools for `root_agent`, `campaign_agent`, `media_agent`, `review_agent`, and `analytics_agent`.
- **`POST /api/v1/agents/chat`** (and **`POST /api/v1/agents/{agent_name}/chat`**)
  Natural-language prompt router supporting all poster prompts and free-form queries:
  ```json
  {
    "prompt": "Generate a video with a European model on a rooftop at sunset, sophisticated mood",
    "dry_run_media": true,
    "prefer_live_agent": false
  }
  ```
  Returns `routed_agent`, `tools_invoked`, conversational `reply`, and structured `data`.
- **Campaigns CRUD**:
  - `GET /api/v1/campaigns?status=active&category=promotional&state=CA&product_id=1`
  - `POST /api/v1/campaigns` (`{"product_id": 1, "store_name": "SoHo Flagship", "city": "New York", "state": "NY", "category": "seasonal"}`)
  - `GET /api/v1/campaigns/{campaign_id}`
  - `PATCH /api/v1/campaigns/{campaign_id}`
- **Products & Multi-Category Onboarding**:
  - `GET /api/v1/products?category=fashion&season=summer&search=floral&catalog_source=all` (`catalog_source`: `all` | `fashion` | `retail_core`)
  - `GET /api/v1/products/categories` (7 categories: `fashion`, `beverage`, `electronics`, `beauty`, `homeware`, `footwear`, `grocery` and their default presentation modes: `model`, `lifestyle`, `product-hero`)
  - `GET /api/v1/products/{product_id}`
  - `POST /api/v1/products`
  - `POST /api/v1/products/import-folder`
  - `POST /api/v1/products/{product_id}/generate-image`
  - `POST /api/v1/products/{product_id}/upload-image`

---

### 3. Step 2: Configurable Video Generation (`Media Agent`)

#### A. Inspect All Configurable Video Components
- **`GET /api/v1/videos/options`** (alias `GET /api/v1/videos/components/schema`)
  Returns all configurable parameters organized into 6 UI form groups:
  1. **`subjects` (Subjects & Model Diversity)**:
     - `presentation_modes`: `model`, `lifestyle`, `product-hero`
     - `model_ethnicities`: `asian`, `european`, `latina`, `black`, `south_asian`, `middle_eastern`, `diverse`
     - `model_description`: custom subject description string
     - `activities`: `walking`, `standing`, `sitting`, `dancing`, `spinning`, `posing`
     - `subject_counts`: `none`, `single`, `couple`, `group`
     - `garment_visibility_options`: `full`, `partial`, `accent`
     - `suggested_props`: `sunglasses`, `handbag`, `coffee_cup`, `flowers`, `shopping_bags`, `umbrella`, `book`, `bicycle`, `headphones`, `champagne_flute` (plus custom string tags)
  2. **`settings` (Settings & Environment)**:
     - `settings`: `beach`, `urban`, `cafe`, `rooftop`, `studio`, `park`, `garden`, `street`, `boutique`
     - `setting_types`: `indoor`, `outdoor`, `studio`, `urban`, `nature`, `beach`, `architectural`
     - `location_detail`: custom scene detail string
     - `times_of_day`: `golden_hour`, `morning`, `midday`, `afternoon`, `sunset`, `blue_hour`, `night`
     - `weather_conditions`: `sunny`, `cloudy`, `overcast`, `rainy`, `windy`, `foggy`
     - `seasons`: `spring`, `summer`, `fall`, `winter`
     - `background_complexities`: `minimal`, `moderate`, `busy`
  3. **`tone` (Tone, Mood & Energy)**:
     - `moods`: `romantic`, `confident`, `playful`, `serene`, `energetic`, `sophisticated`, `mysterious`, `joyful` (+ `editorial`, `warm`, `nostalgic`, `luxurious`)
     - `mood_intensities`: `subtle`, `moderate`, `intense`
     - `has_warmth`: boolean
     - `energy_levels`: `calm`, `moderate`, `dynamic`, `high_energy`
     - `movement_amounts`: `static`, `minimal`, `moderate`, `high`
  4. **`visual_style` (Lighting, Visual Style & Color)**:
     - `lightings`: `natural_soft`, `golden_backlight`, `dramatic_side`, `bright_even`, `dappled`, `neon_ambient`, `studio_three_point`
     - `visual_styles`: `cinematic`, `editorial`, `commercial`, `lifestyle`, `artistic`, `documentary`, `retro`
     - `color_gradings`: `warm`, `neutral`, `cool`, `vibrant`, `desaturated`
     - `color_saturations`: `muted`, `natural`, `vibrant`, `hyper_saturated`
     - `dominant_colors` & `style_tags`: string arrays
  5. **`camera` (Camera Movement & Framing)**:
     - `camera_movements`: `orbit`, `pan`, `dolly_in`, `dolly_out`, `tracking`, `crane_up`, `crane_down`, `static`
     - `camera_angles`: `eye_level`, `low_angle`, `high_angle`, `dutch_angle`, `overhead`
     - `aspect_ratios`: `9:16`, `16:9`, `1:1`
  6. **`production` (Audio & Pipeline)**:
     - `durations_seconds`: `4`, `6`, `8`
     - `use_two_stage`: boolean (Stage 1 Gemini 3 Pro Image -> Stage 2 Veo 3.1 Video)
     - `audio_types`: `silent`, `music`, `ambient`, `voiceover`, `full_mix`
     - `music_tempos`: `slow`, `medium`, `upbeat`, `dynamic`

- **`GET /api/v1/videos/presets`**
  Returns 1-click preset configurations (`asian_beach_romantic`, `european_rooftop_sophisticated`, `latina_urban_confident`, `black_garden_playful`, `south_asian_cafe_warm`, `diverse_park_joyful`, `lifestyle_cafe_warm`, `product_hero_studio_dramatic`, `rooftop_sunset_editorial`).

#### B. Live Prompt Preview & Video Generation
- **`POST /api/v1/videos/prompts/preview`**
  Preview the exact Stage 1 (Gemini 3 Pro Image) and Stage 2 (Veo 3.1) prompts as the user adjusts components in the UI:
  ```json
  {
    "campaign_id": 1,
    "product_id": 1,
    "components": {
      "presentation_mode": "model",
      "model_ethnicity": "european",
      "setting": "rooftop",
      "time_of_day": "sunset",
      "mood": "sophisticated",
      "lighting": "golden_backlight",
      "camera_movement": "dolly_in",
      "activity": "standing",
      "props": ["sunglasses", "champagne_flute"],
      "visual_style": "editorial",
      "color_grading": "warm"
    }
  }
  ```
- **`POST /api/v1/videos/generate`**
  Generates a video with custom components (accepts either a nested `components` object or top-level fields). Set `"dry_run": true` during UX development to create pending DB rows immediately without billing Vertex Veo calls, or `"dry_run": false` for live Veo generation.
- **`POST /api/v1/videos/generate/batch`**
  Generates a batch of video variations from an array of `variations`, `preset_names`, or a matrix of `model_ethnicities`, `settings`, `times_of_day`, `moods`, `lightings`, and `camera_movements`.

---

### 4. Step 3: You Stay in Control (`Review Agent` — HITL Approval)

- **`GET /api/v1/review/table?campaign_id=1&status=generated`** — Structured rows + markdown comparison table.
- **`GET /api/v1/review/pending?campaign_id=1`** — Videos in `generated` status awaiting human approval.
- **`GET /api/v1/review/summary`** — Counts by status (`generated`, `activated`, `paused`, `archived`).
- **`POST /api/v1/videos/{video_id}/activate`** — Transitions `generated -> activated` and generates 30 days of retail media metrics.
- **`POST /api/v1/videos/activate-batch`** — Batch activation:
  ```json
  {
    "video_ids": [5, 7],
    "days_of_metrics": 30
  }
  ```
- **`POST /api/v1/videos/{video_id}/pause`** — Transitions `activated -> paused`.
- **`POST /api/v1/videos/{video_id}/archive`** — Transitions `-> archived`.
- **`POST /api/v1/videos/{video_id}/extend-metrics`** — Extends metrics for an activated video (`{"additional_days": 7}`).
- **`POST /api/v1/videos/{video_id}/edit`** — Experimental Gemini Omni Flash post-generation video edit (`{"edit_instruction": "Add warm golden hour lens flare", "dry_run": true}`).

---

### 5. Step 4: Measure What Matters (`Analytics Agent`)

- **`GET /api/v1/analytics/overview`** — Cross-campaign KPI summary + `docs/METRICS.md` definitions (`rpi`, `dwell_time_seconds`, `circulation`, `impressions`, `revenue`).
- **`GET /api/v1/analytics/top-ads?metric=rpi&limit=10`** — Ranks top videos by `rpi` (primary KPI), `revenue`, `impressions`, `dwell_time`, or `circulation`.
- **`GET /api/v1/analytics/campaigns/{campaign_id}/metrics?days=30`** — Campaign metrics summary and daily breakdown.
- **`GET /api/v1/analytics/campaigns/{campaign_id}/insights`** — Automated optimization insights.
- **`GET /api/v1/analytics/campaigns/{campaign_id}/creatives`** — Creative variation comparison within a campaign.
- **`POST /api/v1/analytics/campaigns/{campaign_id}/creatives/chart`** — Generates a deterministic Matplotlib comparison chart.
- **`GET /api/v1/analytics/campaigns/compare?campaign_ids=1,2,3,4`** — Side-by-side multi-campaign comparison.

---

### 6. Step 5: See the Big Picture (`Analytics Agent` — Geographic Intelligence)

- **`GET /api/v1/maps/campaigns`** — Store markers, coordinates, `performance_tier` (`high`/`medium`/`low`), and Google Maps links.
- **`GET /api/v1/maps/regions`** — Regional performance comparison (`West Coast` vs. `East Coast` vs. `Midwest`), including `west_coast_vs_east_coast` deltas and `top_region_by_rpi`.
- **`GET /api/v1/maps/locations?campaign_id=1`** — Store addresses and coordinates.
- **`POST /api/v1/maps/static`** — Google Static Maps URL builder.
- **`GET /api/v1/maps/demographics?city=Los+Angeles&state=CA`** — Trade-area demographics.
- **`GET /api/v1/maps/nearby-stores?city=Los+Angeles&state=CA`** — Nearby retail stores.

---

### 7. Step 6: Scale What Works (`Media Agent` — Winning Formula)

- **`GET /api/v1/optimization/winning-formula?video_id=5`** (or omit `video_id` to auto-select the highest-RPI video)
  Extracts the winning DNA (`setting`, `time_of_day`, `mood`, `model_ethnicity`, `lighting`, `camera_movement`, `activity`, `props`, `rpi`, `dna_summary`).
- **`POST /api/v1/optimization/apply-winning-formula`**
  Applies the winning formula from a source video/campaign to a target campaign's product:
  ```json
  {
    "source_video_id": 5,
    "target_campaign_id": 3,
    "override_components": {},
    "dry_run": true
  }
  ```

---

### 8. Datasets Explorer & Management

- **`GET /api/v1/datasets`**
  Lists all **12 available datasets** with row counts, schemas, and descriptions:
  1. `fashion_catalog` (22 in-memory fashion products)
  2. `retail_core_catalog` (6 in-memory multi-category retail products)
  3. `products` (SQLite `products` table)
  4. `campaigns` (SQLite `campaigns` table)
  5. `videos` (SQLite `campaign_videos` table)
  6. `video_metrics` (SQLite `video_metrics` daily time-series table)
  7. `video_attribution` (SQLite `video_attribution` schedule table)
  8. `ad_plays` (SQLite `ad_plays` log table)
  9. `audience_visits` (BlueZoo-shaped 15-min sensor visits from `AudienceDataSource`)
  10. `demo_meta` (SQLite `demo_meta` configuration table)
  11. `legacy_ads` (SQLite `campaign_ads` table)
  12. `assets` (Local media files in `product-images/`, `selected/`, `generated/`)
- **`GET /api/v1/datasets/{dataset_name}?limit=50&offset=0&q=...&campaign_id=...&category=...`**
  Paginated, filterable records for any dataset above.
- **`POST /api/v1/datasets/seed`** & **`POST /api/v1/datasets/reset`**
  Seed or reset the database (`{"dataset_mode": "fashion", "force_reseed": true}` or `{"dataset_mode": "none"}`).

---

### 9. UX Designer Object Model & `object.js` Specification

The API gateway natively supports the exact object specifications designed in [`object.js`](../object.js) for frontend web UX integration.

#### A. Status & Approval Enums (`GET /api/v1/ux/enums`)

- **Overall Campaign & Video Status (`Status`)**:
  - `0`: `NONE`
  - `1`: `GENERATING_ACTIVE`
  - `2`: `GENERATING_COMPLETE`
  - `3`: `GENERATING_FAILED`
  - `4`: `REVIEW_NEEDED` (pending human-in-the-loop review)
  - `5`: `APPROVAL_UPDATED` (paused / status updated)
  - `6`: `TESTING_ACTIVE` (activated and running in-store tests)
  - `7`: `TESTING_COMPLETE`
  - `8`: `TESTING_FAILED`

- **Video Approval Status (`ApprovalStatus`)**:
  - `0`: `NONE` (pending approval)
  - `1`: `APPROVED` (video live / activated)
  - `2`: `REJECTED` (video archived)

#### B. UX Campaign Object (`campaignExample`)

Exposed via `GET /api/v1/ux/campaigns`, `GET /api/v1/ux/campaigns/{id}`, or `GET /api/v1/campaigns?format=ux`:

```json
{
  "id": "000001",
  "name": "Spring/Summer Sport Sunglasses",
  "owner": "cid@domain.com",
  "shared_with": ["tommy@domain.com", "fred@domain.com"],
  "created_date": "2026-01-01T00:00:00Z",
  "modified_date": "2026-01-01T00:00:00Z",
  "is_template": false,
  "is_favorite": false,
  "is_archived": false,
  "status": 6,
  "status_meta": {
    "quantity": 10,
    "end_date": "2026-01-01T00:00:00Z"
  },
  "thumbnail": "/generated_assets/000001.jpg",
  "description": "Commercial retail video campaign.",
  "settings": {
    "overall": { "prompt": "...", "files": [] },
    "items": { "prompt": "...", "files": [] },
    "people": { "prompt": "...", "files": [] },
    "performance": { "prompt": "...", "files": [] },
    "setting": { "prompt": "...", "files": [] },
    "audio": { "prompt": "...", "files": [] },
    "languages": ["en-US"],
    "guidelines": [],
    "format": { "duration": 8, "aspect_ratios": ["16:9"], "resolution": "1080p" },
    "testing": { "variants_per_generation": 10, "rules": "...", "duration": 24 }
  },
  "videos": [ /* UXVideo objects */ ]
}
```

#### C. UX Video Object (`videoExample`)

Exposed via `GET /api/v1/ux/videos`, `GET /api/v1/ux/videos/{id}`, or `GET /api/v1/videos?format=ux`:

```json
{
  "id": "000001",
  "name": "000-000-001",
  "parent_id": "000000",
  "campaign_id": "000001",
  "created_date": "2026-01-01T00:00:00Z",
  "modified_date": "2026-01-01T00:00:00Z",
  "is_favorite": false,
  "is_archived": false,
  "approval_status": 1,
  "approval_date": "2026-01-01T00:00:00Z",
  "status": 6,
  "status_meta": { "quantity": 1, "end_date": "2026-01-01T00:00:00Z" },
  "thumbnail": "/generated_assets/000001_000001.jpg",
  "description": "Video ad variant prompt description.",
  "url": "/generated_assets/000001_000001.mp4",
  "testing_period": {
    "start_date": "2026-01-01T00:00:00Z",
    "end_date": "2026-01-01T00:00:00Z"
  },
  "duration": 8,
  "impressions": 1000,
  "impressions_id": "abcd1243",
  "revenue": 123.45,
  "revenue_id": "efgh5678",
  "rank": 1,
  "settings": { /* video-specific overrides */ }
}
```

#### D. UX Endpoints Reference

- **`GET /api/v1/ux/enums`**: Returns `Status` and `ApprovalStatus` enumeration dictionaries.
- **`GET /api/v1/ux/schema`**: Returns JSON Schema definitions for `UXCampaign` and `UXVideo`.
- **`GET /api/v1/ux/campaigns`**: Lists all campaigns formatted as `UXCampaign` objects with nested `videos`.
- **`POST /api/v1/ux/campaigns`**: Creates a new campaign using UX Designer payload.
- **`GET /api/v1/ux/campaigns/{id}`**: Returns a single `UXCampaign` with full `videos` collection.
- **`PATCH /api/v1/ux/campaigns/{id}`**: Updates campaign name, description, or status integer.
- **`GET /api/v1/ux/videos`**: Lists videos formatted as `UXVideo` objects.
- **`GET /api/v1/ux/videos/{id}`**: Returns a single `UXVideo`.
- **`PATCH /api/v1/ux/videos/{id}`**: Updates video status or properties.
- **`POST /api/v1/ux/videos/{id}/approval`**: 1-click approval/rejection (`{"approval_status": 1}` for APPROVED, `2` for REJECTED).
- **`?format=ux` Query Parameter**: Supported on standard `/api/v1/campaigns`, `/api/v1/campaigns/{id}`, `/api/v1/videos`, and `/api/v1/videos/{id}`.

---

### 10. Automated Testing & Verification

The API Gateway is covered by unit and contract tests in [`tests/unit/test_api_gateway.py`](../tests/unit/test_api_gateway.py):

```bash
# Run the API Gateway test suite (24 tests, no LLM calls required)
pytest tests/unit/test_api_gateway.py -v
```

The test suite validates:
1. **Overview & Poster Blueprint**: Health check, KPI totals, and 6-step workflow mapping.
2. **Step 1 Catalog & Agents**: Agent metadata, product listing/onboarding, campaign CRUD.
3. **Step 2 Creative Generation**: Configurable components schema, presets, live prompt preview, single & batch generation.
4. **Step 3 HITL Review**: Review queue, batch activation, pausing, archiving, and editing.
5. **Steps 4 & 5 Analytics & Maps**: Top ads by RPI, campaign metrics/insights, regional comparisons, and static maps.
6. **Step 6 Winning Formula & Chat Router**: Winning formula extraction/propagation, multi-agent chat intent routing for all poster prompts.
7. **Datasets Explorer**: Schema and pagination across all 12 datasets, database seed/reset.
8. **UX Designer Objects**: Exact conformance of `UXCampaign` and `UXVideo` against [`object.js`](../object.js), enum integrity, `?format=ux` query parameter, and approval state transitions.
