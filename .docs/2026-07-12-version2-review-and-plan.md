# Version 2 — Review & Plan

Status: **planning only** — no implementation has started. This document is the "current-state review + proposed approach" for what `version_2` needs to cover, for review before we write per-workstream specs/plans.

**Revision note (2026-07-13):** this doc was adversarially reviewed by Codex (`gpt-5.6-sol`, `xhigh` effort) against the actual codebase. Verdict: *"The plan identifies the right problem areas, but it is not yet implementation-spec ready. All five workstreams need revision; the largest architectural issue is that variant-level RPI attribution cannot be derived from BlueZoo audience data and PoS revenue alone."* Every workstream below has been corrected in place; a new Workstream 6 was added to cover the attribution gap; and the sequencing section was replaced with an incremental, testable phase plan.

## Source context

- Email thread `IMG_2787.PNG`: Lavi → Bill/Cid/Dave (Jul 10), proposing two changes for the weekend: (1) adapt the prompt/agent to support products beyond retail fashion, (2) align the demo more closely with BlueZoo's data schema, isolating the code that pulls outside data so demo-vs-real-world is a toggle.
- Bill Evans' reply (same thread, Jul 10): endorses both, adds detail —
  - Expanding beyond women's fashion is a "huge step forward" since most BlueZoo/Google customers aren't fashion-focused. Should support whatever products the retailer sells in their own stores.
  - Isolating the code that pulls **audience measurement data** (BlueZoo or cached demo data) and **PoS data** (live PoS system or cached demo data) is "the best way to clarify how to toggle from a demo environment to real-world environments."
  - The most important analytic is RPI compared **across a series of alternative advertising creatives** over a period — visualizing variation *over time* risks confusing customers and casting doubt on demo data.
- Verbal addition from Lavi (this session): also migrate video generation from Veo 3.1 to **Gemini Omni Flash**, and use the live BlueZoo API (`https://api.bluezoo.io`) as the reference for the data-source isolation work.
- Codex review (2026-07-13, `gpt-5.6-sol` at `xhigh`): read-only adversarial pass over this document against the live codebase. Findings folded into each workstream below.
- Verbal addition from Lavi (2026-07-13): confirmed the end state is **production launch**, with incremental milestones along the way that can be demoed to Bill (the sequencing table already produces these checkpoints — see Phase 2, Phase 5, Phase 8, and Phase 9b below — this doesn't change the structure, just makes the dual goal explicit). Also elevated **Workstream 4** from an exploratory/low-priority item to a core-priority upgrade covering *both* stages of the media pipeline: Stage 1 (scene image generation) should move from the current Pro-tier image model to **Nano Banana 2 Lite** for speed, and Stage 2 (video generation) should move from Veo 3.1 to **Gemini Omni Flash** specifically for its conversational editing capability, which serves the app's review-feedback → iterate → next-generation-round loop.

This resolves into **six workstreams** (five original + one surfaced by the review). Five touch a specific subsystem and can be spec'd/implemented independently; Workstream 5 (Demo vs. Live mode) is cross-cutting and wraps Workstreams 1 and 2; Workstream 6 (creative playout attribution) is a **prerequisite** for Workstreams 2 and 3, not an independent nice-to-have. **Confirmed goal:** all six workstreams converge on a production launch (Phase 8 in the sequencing below); several phases along the way (2, 5, 8, 9b) are also standalone, demoable milestones for Bill.

---

## Workstream 1 — Generalize beyond fashion retail

### Current state
Fashion is not a swappable value in an otherwise-generic schema — it's structurally embedded at every layer:

- `app/database/db.py:70`: `campaigns.category` has a SQL `CHECK` constraint hardcoded to `('summer','formal','professional','essentials','holiday')` — note this already disagrees with `config.py:86`'s `CAMPAIGN_CATEGORIES` (which lists only 4 of the 5 values); campaign taxonomy is its own inconsistency, separate from product type.
- `app/database/db.py:78`: the `products` table has fashion-typed columns (`style`, `color`, `fabric`, `occasion`).
- `app/database/products_data.py:35`: the seed catalog is all 22 fashion items (`dress`, `pants`, `skirt`, `top`, `outerwear`).
- `app/tools/prompt_builders.py:15,147,283`: prompt templates hardcode a human model wearing a garment (`ethnicity_map` → `"a beautiful woman"` / `"a graceful Asian woman"`, variables named `garment_desc`/`garment_type`). There's no code path for a product shown without a human model.
- `app/agent.py`: all agent instructions (Campaign, Media, Analytics, Review, Coordinator) explicitly say "for a fashion retail company." Two of these instructions also contain **stale facts unrelated to this refactor but that will be touched by it**: `agent.py:310` claims 90 days of metrics exist, but seed generation (`mock_data.py:168`) only produces 30; `agent.py:147` names a campaign "Emerald" that is actually "Sage" in the seed data (`mock_data.py:63`). Fix both while editing this file.
- `app/tools/maps_tools.py:229,761,1118`: `search_nearby_stores` defaults `business_type="fashion store"`, and `get_location_demographics` returns hardcoded fashion-market-index/style-preference data. This needs a deeper rewrite than "configurable defaults" — the simulated data, styling language, and category icons all encode fashion assumptions, not just one default string.
- **Corrected from earlier draft**: `CreativeVariation` (`app/models/variation.py:43,103,150`) and `VideoProperties` (`app/models/video_properties.py:167,252`) are **not** relatively reusable as previously claimed — their core fields and presets assume a human fashion model (ethnicity, model description/activity, poses, props, `garment_visibility`, outfit count).
- **New finding**: product rows already store the full seed object in a `metadata` JSON field (`db.py:367`). A new generic `attributes` JSON column would duplicate this without defined ownership.
- **New finding**: the schema change's blast radius is wider than originally scoped — direct fashion-column consumers also exist in `campaign_tools.py:120,232`, `review_tools.py:612,803`, `maps_tools.py:425`, `video_tools.py:1734`, and `image_tools.py:29`.
- **New finding**: "any product the user supplies ad hoc" (see Workstream 5) is **not supported today at all** — campaign creation requires an existing product ID, and there is no product CRUD/import workflow or general product-image upload path (products are expected to already exist in GCS, per `campaign_tools.py:30`, `storage.py:171`).
- **New finding**: tests hard-code the 22-product fashion catalog and human-model presets (`tests/unit/test_video_tools.py:33`, `tests/conftest.py:237`, `tests/e2e/test_demo_workflows.py:59`) and will need a non-fashion fixture to validate the generalization actually works.

### Proposed approach
**Revised per Codex review** — a raw JSON `attributes` blob (the original proposal) creates validation, indexing, schema-versioning, and queryability problems, and duplicates the existing `metadata` field. Use a **typed common core with versioned extensions** instead:

1. Define a versioned product envelope with stable typed fields (`product_type`, `display_name`, `presentation_mode`, image references, `attributes_schema_version`) plus validated extension attributes — not an untyped JSON-only model.
2. Preserve compatibility accessors for the existing fashion columns during migration rather than deleting them immediately; SQLite here only supports additive migrations today (`db.py:251`, no table-rebuild/versioning framework), so removing the `CHECK` constraint needs an explicit backfill/rollback/validation plan, not just a schema edit.
3. Treat **campaign taxonomy** (the category CHECK constraint) as a separate problem from **product type** — don't conflate them.
4. Separate **business vertical**, **product type**, **campaign category**, and **presentation mode** as four distinct concepts (a shoe can be worn or shown on a pedestal; electronics can be held, installed, or shown in use) — presentation behavior should be driven by product capability, not one template picked per vertical.
5. Parameterize `prompt_builders.py` around `presentation_mode` rather than a single "does this need a human model" flag.
6. Rewrite agent instructions to be vertical-agnostic, with vertical injected as context/config.
7. Add an actual **product ingestion workflow** (create/update/import + asset lifecycle) — this doesn't exist today and is required before "any product the user supplies" is possible.
8. Validate the whole design against at least one real non-fashion, no-human fixture (not just a schema that theoretically allows it).

**Alternative considered:** keep fashion-specific fields and add a parallel set of tables per vertical. Rejected — doesn't scale past 2 verticals and doesn't fix the prompt-builder/agent-instruction coupling.

**Alternative considered (raw JSON attributes):** proposed in the original draft of this doc; rejected on review — untyped JSON breaks validation/indexing/queryability that existing SQL tools rely on, and duplicates the existing `metadata` field.

### Open questions
- Does "any vertical" need to support products *not* modeled by a human (electronics, packaged goods)? Almost certainly yes — affects how deep the prompt-builder rework needs to go.
- Multi-tenant vertical support (one deployment serves multiple retailers/verticals) or single vertical per deployment? Affects whether config is build-time or runtime/per-campaign.
- What does the product ingestion workflow actually look like — bulk import, conversational creation via the Campaign Agent, or both?

---

## Workstream 2 — Isolate & toggle live vs. cached data sources (BlueZoo audience data + PoS)

### Current state
No live integration exists today. `README.md:66` doesn't just describe live BlueZoo connectivity as an aspiration — **it affirmatively claims the repo delivers it**, which currently contradicts the implementation and should be corrected or caveated. All impressions/revenue are `random.*`-synthesized in `mock_data.py:168-235`, written into `video_metrics(video_id, metric_date, impressions, dwell_time_seconds, circulation, revenue)`.

**New finding**: mock-data generation is not confined to `mock_data.py` as originally scoped — activating a video generates another independent 30-day random series (`review_tools.py:168,454`), and `generate_additional_metrics` creates more random rows (`review_tools.py:516`). A refactor that only touches startup seed generation would let demo data leak into Live Mode.

**New finding**: RPI duplication and direct `video_metrics` SQL access are wider than originally scoped — beyond `metrics_tools.py:219,496,660`, RPI is also recomputed in `campaign_tools.py:250` and `maps_tools.py:559,963`, and measurement SQL also appears in `campaign_tools.py:232` and `maps_tools.py:542,912`. **An adapter used only by `metrics_tools.py` would not actually isolate the data source** — every one of these call sites needs to go through the same abstraction.

The closest existing pattern to a "live vs. fallback" toggle is `app/tools/maps_tools.py`: each function does its own `if not api_key: return error/fallback` check. Reusable as a template, not as shared code (duplicated per function) — same critique as before.

### BlueZoo API (reference: `api.bluezoo.io`, BlueZoo Data Warehouse API)
- **Base URL / auth / endpoints** (`list_tables`, `desc_table`, `run_query` with `Authorization: AccessKey {key}`) are publicly documented and don't require a live key to discover.
- **Correction from earlier draft — field mapping was wrong.** BlueZoo's docs describe `sensor_visitors` as **occupancy snapshots**, while **visit counts** are exposed through a separate `sensor_visits` table. The earlier assumption that `inner`/`outer` visitor counts map directly onto this app's `impressions`/`circulation` columns is a **semantic error** — occupancy ≠ visits ≠ ad impressions, and these need to be explicitly reconciled against a metric glossary (see below), not assumed equivalent.
- The `bluefox`/`morpheus` domain aliases cited in the earlier draft could not be independently verified.
- Actual tenant schemas/responses still require a real access key to confirm.
- **New risk**: `run_query` accepts raw SQL. Queries must be built from an allowlist of tables/columns with validated identifiers and date ranges — LLM- or user-supplied SQL must never be passed through to this endpoint.
- **PoS data**: still no reference API — BlueZoo doesn't cover point-of-sale. `RevenueDataSource.get_revenue(location, date_range)` (the shape proposed in the original draft) is too weak for real PoS integration — it needs store/SKU mapping, timezone, currency, taxes, returns, attribution window, late corrections, and vendor-specific auth, on top of picking a target PoS system.

### The missing piece: creative playout/exposure attribution
**This is the review's most important finding — see Workstream 6.** BlueZoo supplies sensor/time data; PoS supplies store/SKU/time data; this app stores metrics by `video_id` and date (`db.py:137`). **Neither source says which creative was playing on which screen during which interval.** Without a signage playback log, per-variant RPI is not attributable from BlueZoo + PoS alone, no matter how well-built the adapters are. Workstream 2's adapters should be built to feed a canonical measurement model that includes this third input, not just audience + revenue.

### Proposed approach
**Revised per Codex review:**

1. Define a **metric glossary** first — canonical meanings and units for impressions, revenue, RPI. The current codebase is already internally inconsistent (mock generation calls impressions "ad displays," `mock_data.py:172`, while the product narrative treats it as audience traffic).
2. Build **three** provider interfaces, not two: `AudienceDataSource`, `RevenueDataSource`, and `PlayoutSource` (Workstream 6) — normalized into interval/store/screen/product/creative records with **provenance and watermarks** (source, `as_of` time, completeness/staleness), not raw pass-through query results.
3. Feed all of the above into **one canonical measurement read model** that `metrics_tools.py`, `campaign_tools.py`, `maps_tools.py`, and `review_tools.py` all read from — centralizing RPI computation in one place, replacing the 6+ duplicated implementations across all four files (not just `metrics_tools.py`).
4. Demo Mode implementations must be **deterministic fixtures**, not the current random generation — today's demo data changes on every restart and every video activation gets an independent random series, which is unusable as a stable comparison fixture (also affects Workstream 3).
5. **Live failures must never silently fall back to demo data.** Either serve a clearly labeled last-known-good snapshot with its age, or fail closed for the affected metric — silent fallback would misrepresent a retailer's real performance as demo numbers.
6. New env vars/secrets: `BLUEZOO_ACCESS_KEY`, a location→sensor mapping, PoS credentials once a system is chosen — **all of these belong in Secret Manager or equivalent, never in prompts, tool parameters, CLI args, logs, or error payloads** (see Workstream 5's security findings).

**Alternative considered:** a feature-flagged branch inside each existing function (mirroring `maps_tools.py`'s per-function pattern). Rejected — this is now confirmed to *not* isolate the source, since RPI/metrics logic is duplicated across 4 files, not 1.

### Open questions
- Need a live BlueZoo access key + a real `run_query` example to finalize the request/response shape and confirm which table(s) actually correspond to ad-relevant traffic vs. general occupancy.
- Which PoS system(s) should be supported first?
- Is "toggle to real-world" per-campaign, per-tenant, or a single global deployment switch? (See Workstream 5.)
- Required test coverage, currently missing entirely: adapter conformance tests against sanitized API fixtures, timezone-boundary handling, idempotent backfills, missing-sensor handling, stale-cache behavior, 401/403/429/timeout handling, and asymmetric BlueZoo/PoS failure (one source up, one down).

---

## Workstream 3 — Fix RPI-across-creatives visualization

### Current state
`metrics_tools.py:35-166` (`CHART_TEMPLATES`) confirms 4 chart types, all AI-image-rendered via `metrics_tools.py:975` (not a real charting library): `trendline` (true time series), `bar_chart` (weekly-bucketed time series), `comparison` (single-campaign KPI snapshot, not cross-variant despite the name), `infographic` (KPI panel + mini trend). None compare RPI across creative variants — Bill's specific ask, confirmed accurate.

**Correction from earlier draft**: `get_top_performing_ads` (`metrics_tools.py:285,315`) is **not** a good source for this — it aggregates across *all* campaigns with no campaign or date-window scoping. `get_campaign_insights` (`metrics_tools.py:519`) is the better starting point — it already groups performance by video inside a single campaign, though it still needs a date range parameter and corrected RPI ranking.

**New finding — live bugs in the function this workstream would extend**: the visualization tool's default metric is `"revenue"`, which its own validation doesn't accept (`metrics_tools.py:723,745`); it also dereferences `summary` before completing its no-data handling (`metrics_tools.py:773`). Fix these before/while extending the function.

**New finding — math error already present**: the existing weekly `bar_chart` sums daily RPI values across the week (`metrics_tools.py:906`) instead of computing `SUM(revenue) / SUM(impressions)`. Any new aggregation must use the correct weighted formula, not sum/average of per-day ratios.

**New finding — test coverage is too weak to protect this area**: some visualization tests invoke the async function without awaiting it and accept any non-`None` result or swallowed exception (`tests/unit/test_metrics_tools.py:177`, `tests/e2e/test_demo_workflows.py:297`); the analytics eval set has no variant-comparison scenario at all.

### Proposed approach
**Revised per Codex review** — "one new function plus routing" understates the work:

1. Define a structured comparison result first: variant ID/name, summed revenue, summed impressions, **weighted RPI** (`SUM(revenue)/SUM(impressions)`, never averaged daily ratios), exposure interval, source, freshness, and eligibility status (handles ties, zero-impression variants, minimum-exposure thresholds).
2. Source it from `get_campaign_insights`, scoped to campaign + date range, not `get_top_performing_ads`.
3. **Render with a deterministic charting mechanism, not generative AI image rendering** — generative rendering cannot reliably preserve exact values, labels, ordering, or bar heights, which matters for a quantitative business metric. Return the underlying data table alongside any chart.
4. Note this is only demo-mode-credible until Workstream 6 supplies real creative-playout attribution — don't claim Live Mode validity before then. Variant comparison is also not credible against today's *demo* data as-is, since every activated video gets an independent random series, sometimes with future-dated rows (activation adds day offsets from "today," `review_tools.py:485`) — needs Workstream 2's deterministic-fixture fix first.
5. Fix the two live bugs above (default-metric validation, `summary` null-deref) while touching this function.
6. Decide whether to keep `trendline`/`bar_chart` available for internal/debug use or hide them from customer-facing flows per Bill's concern — recommend keeping them available but making the new comparison view the default for customer-facing RPI reporting.

### Open questions
- Over what window should "a series of alternative advertising creatives over a period of time" be aggregated — campaign lifetime, last 30 days, or caller-specified?
- What counts as a "minimum exposure" threshold before a variant is eligible for comparison (avoids noisy conclusions from low-impression variants)?

---

## Workstream 4 — Upgrade media generation: Nano Banana 2 Lite (image stage) + Gemini Omni Flash (video stage)

**Revised (2026-07-13):** originally scoped as an exploratory, lowest-urgency, video-only swap. Now confirmed as a core-priority upgrade covering *both* stages of the existing two-stage pipeline, because it feeds directly into the app's central loop (generate variants → measure RPI → iterate on feedback → next round), not just a model refresh.

### Current state
**Stage 1 — scene image generation.** `IMAGE_GENERATION = "gemini-3-pro-image-preview"` (`config.py:27`), called from `generate_scene_image()` (`video_tools.py:191-259`) via `client.models.generate_content()`.

**Stage 2 — video generation.** `VEO_MODEL = "veo-3.1-generate-preview"` (`config.py:28`). `generate_videos()` is called from **three** places — the primary animation flow (`video_tools.py:298`), a direct fallback (`video_tools.py:579`), and a legacy tool (`video_tools.py:959`) — all with duplicated polling (`while not operation.done: sleep(20)`) and output-extraction logic. A provider branch added to only one of these would leave inconsistent behavior across the app.

**Correction from earlier draft**: `google-genai>=1.55.0` (`requirements.txt:19`) is not meaningfully "pinned" — no upper bound, no lockfile, so the exact installed API surface isn't reproducible from the repo alone; this needs a real version check before assuming `client.interactions` exists.

**Correction from earlier draft**: Omni's Cloud/Vertex availability is **less unclear than previously stated**. Official docs now confirm `gemini-omni-flash-preview`, `client.interactions.create`, image-to-video input, interaction continuation, inline/URI outputs, and 3–10 second 720p video, and official Cloud documentation lists Omni Flash Preview through the Agent Platform API. However, **compatibility with this repo's specific Agent Engine runtime, credentials, and `google-genai` Vertex mode remains unverified** without an authenticated smoke test.

**Verified (2026-07-13)**: the correct model name for the image-stage upgrade is **Nano Banana 2 Lite** (`gemini-3.1-flash-lite-image`), launched 2026-06-30 *alongside* Gemini Omni Flash — Google's own documented workflow for the pair is "generate an image with Nano Banana 2 Lite, then pass it to Gemini Omni Flash to create an animated video," which is almost exactly this app's existing Stage 1 → Stage 2 shape. That lowers migration risk: this is closer to swapping two model IDs and adapting API shapes than inventing a new pipeline. Specs: ~4s text-to-image latency, ~$0.034/image (faster and cheaper than the current Pro-tier model) — but a 1K resolution cap, weaker small-text rendering, no Search grounding, and reported character/product-consistency drift across repeated generations. Since this app must preserve exact product identity (garment, color, logo) across scene images, fidelity needs an explicit side-by-side check against real product photos before Lite replaces the Pro-tier model outright, not an assumed drop-in.

**Verified (2026-07-13)**: Gemini Omni Flash's editing mechanism is `previous_interaction_id` — a follow-up call can edit an already-generated video conversationally via a dedicated `edit` task type (alongside `text_to_video`, `image_to_video`, `reference_to_video`), without re-uploading or regenerating from scratch. Pricing is ~$0.10/sec (~$1 for a 10s 720p pass). Google's own positioning: Omni Flash is built for iterative, context-aware drafting (5-6 edit rounds), while Veo remains the recommended path for final single-shot high-resolution output (up to 4K) — this is a signal toward a hybrid draft/final design (see Proposed approach #6), not a strict one-for-one replacement.

**New finding**: current duration validation only permits 4/6/8 seconds (`config.py:32`); Omni's supported range differs, so duration validation needs to be provider-specific, not a single shared constant.

**New finding**: Veo calls run synchronous SDK calls and `time.sleep()` inside `async` tool functions (`video_tools.py:313,976`), blocking the event loop — a new backend shouldn't inherit this.

**New finding**: the database doesn't record provider, model, interaction ID, or job status at all (`db.py:110`) — Omni's conversational continuation can't be resumed reliably without storing something like `previous_interaction_id`. Also, the primary flow only writes a DB record *after* successful generation (`video_tools.py:650`), so failures leave no durable job/audit record — this predates Omni but would get worse with a second, differently-shaped provider.

**New finding**: existing generation tests are too weak to validate a new provider — they mostly assert non-`None` and often only run in slow/Veo-marked suites (`tests/unit/test_video_tools.py:245`).

### Why this is now core-priority, not exploratory
This directly serves the app's central loop: Review Agent HITL feedback → iterate → next generation round. Today, "iterate on feedback" means re-running the full two-stage pipeline from scratch with a revised prompt — there's no way to make a targeted edit to an already-generated video. Omni's `previous_interaction_id` + `edit` task type would let the Review Agent request a specific change (e.g., "brighten the lighting," "swap the background") and get a revised clip without a full regeneration — faster and cheaper per iteration. Separately, Nano Banana 2 Lite's speed and cost lower the cost of generating more creative variants per round, which matters because RPI-across-creatives (Bill's #1 ask, Workstream 3) only means something if there's a meaningful set of variants to compare — cheaper variants per round directly supports that.

### Proposed approach
**Revised per Codex review, extended to cover both stages** — consolidate before adding a second provider on either stage, don't branch inside the existing functions:

1. Introduce a **provider-neutral video-generation contract** first, and migrate all three existing Veo call sites behind it — this fixes the duplication problem regardless of Omni, and prevents building yet another set of divergent branches.
2. Introduce an equivalent **provider-neutral image-generation contract** for Stage 1 (new — the original plan only covered the video call sites). `generate_scene_image()` needs the same treatment before a second image backend (Nano Banana 2 Lite) can be added alongside the current Pro-tier model.
3. Persist provider/model/job-or-interaction-ID and explicit generation state in the DB (queued/running/succeeded/failed), including on failure paths.
4. Pin a compatible `google-genai` SDK range (or lockfile) and confirm `client.interactions` and the Nano Banana 2 Lite model ID actually resolve in the installed version before writing provider-specific code for either.
5. Prototype Omni against **both** the Gemini Developer API path and the now-documented Cloud/Agent Platform path with authenticated smoke tests, rather than assuming Vertex is blocked — but don't treat either as production-ready until tested against this repo's actual deployment target (Agent Engine).
6. **Design a two-tier draft/final split as the primary hypothesis, not a strict replacement**: generate creative variants using Nano Banana 2 Lite (image) + Omni Flash (video, using `edit` for review-feedback rounds), since both are fast/cheap and Omni is built for iteration. Once a variant wins on RPI, optionally re-render *that one winner* through the current Pro-tier image model + Veo 3.1 for a final high-resolution pass before it's activated in-store. This mirrors Google's own recommended draft/final split and maps directly onto this app's existing lifecycle (many variants generated → one winner selected → only the winner actually runs).
7. Add fixture-based tests for inline output, URI output, timeout, rejection, retry, storage failure, and backend fallback, for **both** the image and video contracts — the current test suite doesn't cover any of this.
8. Add independent config toggles: `IMAGE_MODEL_BACKEND` (`nano_banana_pro` default, `nano_banana_2_lite` opt-in) and `VIDEO_MODEL_BACKEND` (`veo` default, `omni` opt-in), so each stage can be swapped and measured on its own before either becomes the default.

**Alternative considered:** wait for Omni/Nano Banana 2 Lite GA before touching the code. Rejected as the sole plan — this is now a confirmed, prioritized part of the production plan, not a bounded side-experiment; it still lands as its own phase(s) in the sequencing below so it can be tested independently of the other workstreams.

### Open questions
- What SDK version is actually installed, and does it expose `client.interactions` and the Nano Banana 2 Lite model ID?
- Does Nano Banana 2 Lite's fidelity trade-off (1K cap, character/product-consistency drift) actually matter for this app's real product photography, or only for text-/logo-heavy products? Needs a side-by-side test with real product images before deciding whether Lite replaces the Pro-tier model outright or stays draft-only.
- Should the "draft in Lite/Omni, finalize in Pro/Veo" hybrid be the permanent architecture, or a migration bridge until Omni's output resolution/quality improves?
- Does the Review Agent's tool surface need a new `request_video_revision`-style tool that calls Omni's `edit` task with `previous_interaction_id`, distinct from the existing "generate a new video" tools?
- What are the acceptance criteria for adopting preview models in a product with a real deployment target — cost ceiling, latency ceiling, fidelity bar, fallback policy?

---

## Workstream 5 — Demo Mode vs. Live/Connected Mode (cross-cutting)

### Why this is its own workstream
The application needs two explicit, first-class modes, not just an internal data-source toggle:

1. **Demo Mode** — runs on demo presets (existing fashion catalog + new non-fashion catalogs from Workstream 1) and can also take **any product a user supplies on the spot** to showcase the system's flexibility, without real credentials.
2. **Live/Connected Mode** — a retailer plugs in their own BlueZoo access key (and future PoS credentials) and the system works "out of the box" against real audience/revenue data and their real product catalog.

### Current state
**New finding — this is more structurally invasive than "add a config flag":** the database is unconditionally initialized and populated with mock data during module import (`agent.py:105`). Live Mode must prevent this *before* agent construction, not merely branch tool behavior afterward.

**New finding**: the DB is deliberately ephemeral in managed environments (`config.py:65`) — incompatible with durable live retailer catalogs, source mappings, campaign state, audit records, or multi-instance deployment. Live Mode needs a real persistence decision, not just a config flag.

**New finding — security posture is not ready for live retailer data:**
- Cloud Run deployment defaults to **unauthenticated access** (`deploy.sh:87,232`).
- Agent Engine deployment enables capture of prompt/response message content (`deploy_ae.sh:244`), which could leak credentials or retailer data if entered conversationally.
- Storage helpers construct **public** GCS URLs (`storage.py:355`); live assets need private, tenant-scoped access.
- Config defaults to a shared bucket name (`config.py:47`).
- Activation records use a caller-supplied `"user"` string, not an authenticated principal (`review_tools.py:111`).

**Correction from earlier draft**: product-domain generalization (Workstream 1) should **not** actually be gated by mode — Demo and Live should share the same product/prompt contracts; only data providers, fixtures, and presentation labels should change by mode. The earlier framing implied mode gated "any product" support; it doesn't — Workstream 1 needs to deliver that regardless of mode.

### Proposed approach
**Revised per Codex review** — a single environment variable is not sufficient framing:

1. Treat mode as **typed, immutable deployment configuration**: `APP_MODE=demo|connected` plus explicit per-provider configuration, validated and rejected-if-contradictory at startup — not an emergent property of whatever env vars happen to be set, and not something that can flip live behind a running instance without a restart.
2. Distinguish **configured capability** from **current health** — binary mode is too coarse if audience is connected but PoS isn't, or a provider is temporarily unhealthy. Missing static config should fail startup; a transient outage should produce an explicit degraded/error state, not a restart loop or a silent slide back into demo data.
3. Before Live Mode ships, require: durable persistence, authenticated/private deployment, Secret Manager integration for all live credentials, tenant/store ownership rules, private asset delivery, real authenticated-principal audit records, and a non-conversational onboarding/configuration path (credentials should never be typed into a chat prompt).
4. Provide a `config doctor`-style connectivity-check workflow that validates credentials and mappings without ever exposing the secrets themselves.
5. Onboarding checklist (expanded from earlier draft): BlueZoo access key + sensor/screen/store mapping, timezone and SKU mapping, PoS credentials, catalog import, bucket/IAM setup, connectivity/schema checks, backfill range, validation totals, source health, and credential revocation path.
6. Source provenance (mode, provider, `as_of` time, completeness/staleness) should be a structural field on every metrics result, not something asserted only in agent instructions — this is what lets the Analytics Agent honestly say "this is demo data" vs. "this is your live data."

**Open decision, not yet resolved:** whether mode is fixed per deployment, switchable by an administrator, or selectable per tenant — the current architecture has no tenant ID, store ownership, or per-tenant config model at all, so this is a real architectural choice, not a detail to defer.

### Open questions
- Per-deployment vs. per-tenant mode — see above; this changes the entire persistence/auth design, not just a flag.
- What's the minimum viable onboarding for v2 — a documented manual process, or does live retailer data require enough security hardening (auth, secrets, private storage) that it can't ship as a lightweight checklist?
- In Demo Mode, should ad hoc user-supplied products be ephemeral or persisted for reuse?

---

## Workstream 6 — Creative playout/exposure attribution *(new — surfaced by review)*

### Why this exists
Codex's review identified this as the plan's biggest gap: **neither BlueZoo (sensor/time data) nor PoS (store/SKU/time data) records which creative was playing on which screen during which interval.** This app's metrics are stored by `video_id` and date (`db.py:137`), but nothing today establishes the link between "this ad was displayed here, then" and "this audience/revenue was measured here, then." Without that link, **per-variant RPI is not attributable** — Workstreams 2 and 3 can be built perfectly and still not produce a trustworthy answer to "which creative performed better," because there's no data connecting a creative to an exposure window.

### Proposed approach
1. Define a **playback/schedule log**: a record of which creative (video/variant) was active on which screen/store during which time interval. This can start as a simple table (`screen_id`, `video_id`, `start_time`, `end_time`) populated by whatever schedules signage today (manually, via a playlist system, or via a new lightweight scheduling tool this app should own).
2. This becomes the third required input — alongside `AudienceDataSource` and `RevenueDataSource` (Workstream 2) — for the canonical measurement model: join playout intervals against audience/revenue intervals by screen/store/time to attribute impressions and revenue to a specific creative.
3. Build and test this against **demo/fixture data only** first — the join logic (video × store × time window) can be fully validated with synthetic playback logs, with no live BlueZoo/PoS dependency.
4. Resolve the "impressions" terminology inconsistency as part of this work: mock generation currently calls it "ad displays" (`mock_data.py:172`) while the broader product narrative treats it as audience traffic — the metric glossary (Workstream 2) and the playout model need to agree on what an "impression" actually counts.

### Open questions
- Does a signage/playback scheduling system already exist for BlueZoo's retail customers that this app should integrate with, or does this app need to own scheduling itself?
- What's the minimum viable granularity for the playback log — per-screen, per-store, or per-campaign?

---

## Incremental sequencing

The original "workstream-level" ordering (do 1, then 2, then 5, etc.) doesn't specify what's testable at each step or what each phase hands to the next. Replaced with a phased plan where each phase has an explicit exit test and a named hand-off to the next phase.

| Phase | What it builds | Testable exit condition | Feeds into |
|---|---|---|---|
| **0. Foundations** | Metric glossary (canonical impressions/revenue/RPI units, resolving WS2/WS6's terminology conflict) + `APP_MODE` config skeleton (typed, fail-fast, no real adapters yet) | Config unit tests with fake env vars; no credentials needed | Everything downstream reads this config surface |
| **1. Product core** (WS1) | Typed product schema + versioned extensions, additive migration, old fashion columns kept as compatibility accessors | Existing tests still pass + new test with a non-fashion, no-human fixture product | Phase 2's prompt rewrite needs this data shape to exist first |
| **2. Prompt/agent generalization** (WS1) | Vertical-agnostic prompt builders + agent instructions, built on Phase 1's schema | Generate creative for 1 fashion + 1 non-fashion fixture, diff outputs; updated e2e suite | Phase 9a/9b reuse this abstraction instead of rebuilding it |
| **3. Playout/exposure attribution** (WS6) | Playback log model: which creative was on which screen/store during which interval | Unit-test the join logic (video × store × time window) against synthetic playback logs — no live APIs needed | Becomes the 3rd required input to Phase 4 |
| **4. Canonical measurement + demo adapters** (WS2) | `AudienceDataSource`/`RevenueDataSource`/`PlayoutSource` interfaces, **demo-only** deterministic implementations (fixing today's non-reproducible random data), RPI centralized in one place across all 4 consuming files | Full app run in Demo Mode, RPI numbers checked against hand-calculated fixture values | Phase 5 (chart) and Phase 6/7 (live adapters) both build against this same interface |
| **5. RPI-across-creatives chart** (WS3) | New comparison view against Phase 4's deterministic demo data, deterministic rendering (not generative image) | Exact-value assertions against known fixtures | First customer-demoable milestone |
| **6. Live BlueZoo adapter** (WS2) | Real `AudienceDataSource` implementation, conforming to Phase 4's contract | Adapter contract tests against sanitized/recorded API responses, + manual smoke test if a sandbox key is available | Required before Phase 8 |
| **7. Live PoS adapter** (WS2) | Real `RevenueDataSource` implementation — blocked until a target PoS system is chosen | Same adapter-conformance pattern as Phase 6 | Required before Phase 8 |
| **8. Live/Connected Mode cutover** (WS5) | `APP_MODE=live` enforcement, onboarding checklist, security fixes (Cloud Run auth, private GCS, Secret Manager, authenticated activation records) | Staging deployment against a real or sandboxed BlueZoo account, end-to-end | **Production launch milestone** |
| **9a. Nano Banana 2 Lite (image stage)** (WS4, parallel/decoupled) | Provider-neutral image-generation contract for Stage 1; add Nano Banana 2 Lite as a second `IMAGE_MODEL_BACKEND` alongside the current Pro-tier model | Side-by-side fixture test: same product/scene prompt through both backends, fidelity + latency logged | Feeds 9b — Nano Banana 2 Lite → Omni Flash is the vendor's own recommended image→video pairing |
| **9b. Gemini Omni Flash (video stage + iterative editing)** (WS4, parallel/decoupled) | Consolidate the 3 Veo call sites behind one provider-neutral interface; add Omni as a second `VIDEO_MODEL_BACKEND`; wire `previous_interaction_id`/`edit` into the Review Agent's feedback loop | Fixture-based tests for inline/URI output, timeout, rejection, plus one generate-then-edit round-trip | **Bill-demoable milestone** — faster, cheaper, editable creative generation |

Notes on this ordering (per Codex's sequencing critique, updated 2026-07-13):
- Phase 0's config foundation is pulled to the front — building live adapters (old Phase "Workstream 2") against an undefined secret/tenancy/failure model was the original plan's biggest sequencing risk.
- Phase 3 (playout attribution) did not exist in the original workstream list at all and is now a hard prerequisite for Phase 4 — this is the single most important structural change from the review.
- Phase 4 is demo-only by design — it proves the abstraction and unblocks Phase 5 (a shippable demo milestone) *before* any live credentials are needed.
- Phases 9a/9b (formerly a single "Omni prototype" phase) are fully decoupled from Phases 0–8 and only touch media generation — they can start as early as Phase 1 rather than waiting until last. The split reflects a real risk difference: 9a swaps a model ID within the same Gemini image-generation family (lower risk), while 9b introduces a new API shape (the Interactions API) and a new interaction pattern for the Review Agent (higher risk). Both are now confirmed core-priority work, not a low-priority afterthought — this ordering reflects *technical* dependency, not importance.
- Phases 2, 5, and 9b are demoable checkpoints on the way to the Phase 8 production launch — useful for staging what to show Bill as the work progresses, without treating any of them as a separate "MVP" track.

## Next steps

This document is planning-only; no repository changes beyond this doc and `.gitignore` have been made. Each workstream (1–6) should go through its own brainstorming → spec → implementation-plan cycle before code changes start, following the phase order above rather than the workstream numbering — phases 0, 1, and 3 in particular unblock everything else and should be spec'd first. The confirmed end state across all workstreams is production launch (Phase 8); Phases 2, 5, and 9b double as Bill-demoable checkpoints along the way, and Phases 9a/9b (media-generation upgrade) can be spec'd and started in parallel as soon as Phase 1 lands, given their now-confirmed priority.
