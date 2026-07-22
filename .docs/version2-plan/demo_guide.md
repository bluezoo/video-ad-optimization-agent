# Owner Demo Guide — manual test journeys (living document)

**This file is the always-current manual testing guide.** Every workstream that changes
agent-visible behavior must update it before its PR (rule recorded in `CLAUDE.md`
"Workstream process" and `HOW_TO_RUN_A_WORKSTREAM.md`), so the journeys here always
reflect the latest merged + in-review changes. It supersedes the ws08 snapshot at
`working-docs/08-product-schema-generalization/USER_JOURNEY_TEST_GUIDE.md` (kept as a
historical record).

**Last updated:** 2026-07-22, workstream 11a (live BlueZoo adapter, seam-only) —
demo-mode behavior is byte-identical; see Part 0b for what actually changed
(APP_MODE now gates a real seam). Previous update: workstream 10 (playout
attribution) — metrics now derive through the ad-play join described below; see
"What changed in Phase 10" ahead of Journey B4. Previous update: workstream 09
(prompt & agent generalization, PR #10) — incl. the ad-style policy added after
the owner's first manual test round.

---

## Setup (once per test session)

```bash
make reset-db   # wipe campaigns.db so journeys start from the seeded demo state
make dev        # ADK web UI on http://localhost:8501 (~20-30s to seed demo data)
```

Open http://localhost:8501, pick the app, start a **new session**. For any journey that
says "check the trace", use the **Trace tab** on the response (Event → functionCall /
functionResponse) — tool responses carry the real values; the chat prose is secondary.

> **Known quirk (pre-existing, not from ws09):** generated-video filenames embed only
> the date (MMDDYY) + variation name, so regenerating the **same product with the same
> setting/mood on the same day** fails with a `UNIQUE constraint` error *after* the
> (paid) generation. If you repeat a video journey in one day, vary the setting or mood
> ("use a rooftop setting", "make it moody"), or `make reset-db` first.

---

## Part 0 — What workstream 10 changed (newest — test these first)

Phase 10 made the metrics story causal: a video only earns metrics because it
**played on real screens during attribution windows**. These journeys check the new
machinery end to end. The sqlite commands below are read-only checks (except the one
marked SETUP) — run them in a second terminal from the repo root you started
`make dev` in.

### Journey 0.1 — activation opens attribution windows (SETUP + UI + DB check)

The seeded demo ships every video already activated, so first create one pending
video to activate (SETUP — run after `make dev` has finished seeding):

```bash
sqlite3 campaigns.db "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status) VALUES (1, (SELECT product_id FROM campaigns WHERE id = 1), 'owner-test-pending.mp4', 'generated');"
```

Then in the chat:

```
Show me the pending videos for campaign 1, then activate the first one
```

**Expect:** the pending list shows the `owner-test-pending` video; activation succeeds
and reports **30 days** of metrics generated. Then the DB check:

```bash
sqlite3 campaigns.db "SELECT va.screen_id, va.active_from, va.active_to FROM video_attribution va JOIN campaign_videos cv ON cv.id = va.video_id WHERE cv.video_filename = 'owner-test-pending.mp4';"
```

**Expect:** **2–3 rows** (campaign 1 has screens **101/102/103** — note screen ids are
NOT the campaign id anymore: the old 1:1 campaign-as-screen proxy is gone), every
`active_from` = 30 days back from the demo anchor, every `active_to` empty (open =
still live).

### Journey 0.2 — pausing closes the windows; reactivating reopens cleanly

```
Pause that video
```

Re-run the Journey 0.1 DB check. **Expect:** the same rows now all have `active_to`
set (closed = plays stop accruing).

```
Activate it again
```

**Expect:** activation succeeds; the DB check now shows the closed rows **plus** 2–3
new open rows (closed rows are kept as history), and — the important part — the
video's metrics are **unchanged** (`metrics_generated: 0` is correct here: rows
already existed, and overlapping windows never double-count; that guard has its own
tests).

### Journey 0.3 — deterministic extension still exact (F3's check)

```
What's the status of video 1, including how many days of metrics it has?
```
```
Generate 3 more days of metrics for video 1
```
```
Check video 1's status again — how many days now?
```

**Expect:** exactly **30 → 33** (every activated video extends together; nothing
random).

### Journey 0.4 — the numbers themselves

Run Journeys **B4 and B5** below — their invariants (RPI band [0.03, 0.07],
`revenue ≈ impressions × RPI` per creative, distinct RPIs across creatives, winner =
max RPI) are the real Phase 10 acceptance check, and the example numbers there were
re-captured from the new join.

---

## Part 0b — What workstream 11a changed (APP_MODE now does something)

Phase 11a put demo-data generation behind a real seam: an `AudienceDataSource`
interface with `SyntheticAudienceDataSource` (today's demo generator, wrapped
as-is) as the only registered implementation, resolved by `APP_MODE` through a
fail-closed factory. This is a refactor, not a behavior change — demo mode's
output is byte-identical by design (golden-pinned against the pre-refactor
join), so every ws10 journey above still applies verbatim; nothing to
re-verify there beyond re-running them once.

### Journey 0b.1 — demo mode unchanged

```bash
make dev
```

Re-run Journey 0.2 (or any ws10 journey) — expect **identical numbers** to
before this workstream. If anything differs, the seam refactor broke
byte-identity and that's a regression, not an intentional change.

### Journey 0b.2 — connected mode fails closed (terminal check, no browser needed)

```bash
cd <worktree> && APP_MODE=connected .venv/bin/python -c \
  "from app.audience import get_audience_datasource; get_audience_datasource()"
```

**Expect:** a `RuntimeError` whose message names `APP_MODE='connected'`, Phase
11b (the live BlueZoo adapter that isn't implemented yet), and the way back
(`APP_MODE=demo`, the default). This is where it surfaces in the app: any flow
that derives metrics (video activation, demo-data seeding) raises this same
error in connected mode instead of silently falling back to demo data — the
fail-closed principle from Phase 6, now real rather than deferred.

### Journey 0b.3 — invalid APP_MODE still rejected at startup

```bash
APP_MODE=banana make dev
```

**Expect:** the Phase 6 `ValueError` at config load (unchanged behavior — this
predates ws11a). Listed here so it's clear these are two different layers: an
invalid `APP_MODE` value fails at **config load** (`ValueError`), while a
valid-but-unimplemented value (`connected`) fails at **datasource resolution**
(`RuntimeError`) the first time something actually needs audience data.

---

## Part A — What workstream 09 changed

### Journey A1 — THE fix: cold-brew video is now a product ad, not a fashion shot

This is the bug you caught on 2026-07-19 (video showed a model wearing a dress made of
cold-brew cans). Prompts now route through a **category → archetype registry**:
beverages/QSR get an appetizing product-hero treatment, electronics/furniture/appliances
get styled product staging, unknown categories get a clean generic hero shot — and the
fashion path is untouched for wearables.

```
List the beverage products
```
```
Create a campaign for the Aurora cold brew at Target Downtown in Austin, Texas
```
```
Generate a video for the Aurora cold brew using a studio setting
```

**Expect (~2-3 min for the video):**
- The scene/video prompts in the trace contain **no** "fashion", "garment", "wearing",
  "model", "she" — they read like a drinks commercial (condensation, steam/fizz,
  appetite cues).
- The tool response shows `reference_image_used: false` **with a warning** that no
  product image exists (retail SKUs ship without images until Phase 14a/15 — the video
  is generated from the text description alone, so the can's look is plausible, not
  pixel-faithful to a real SKU).
- Filename is product-centric: `aurora-cold-brew-330ml-<date>-beverage-studio-elegant.mp4`
  — **not** `...-diverse-studio-elegant...`.
- Campaign was created with `category: "always-on"` and a description naming the product
  (no "fashion item", no "classic").

### Journey A1b — ad style policy: music only, clean frame (added 2026-07-22)

Applies to **every** video journey in this guide (fashion included). After any video
generates, check:

- **Audio:** instrumental background music only — no voiceover, narration, or lyrics.
- **Frame:** no text badges, captions, titles, or graphic overlays anywhere (the brisket
  video's "780 Calories / Limited Time" plaques are the failure mode this kills). Text
  that is part of the product's own packaging (the can's label) is fine.
- The trace's scene prompt contains a "NO TEXT OR GRAPHICS" block; the video prompt
  contains an "AUDIO & ON-SCREEN TEXT" block.

Note: this steers the models via prompt directives — Veo occasionally improvises, so an
odd output can still slip through on a given seed. Phase 16's Gemini-judge tests will
catch those automatically; report any you see meanwhile.

### Journey A2 — other verticals route to their own archetypes

```
Generate a video for the smoky brisket stack sandwich in a cafe setting with a warm mood
```
```
Generate a video for the Nordic oak lounge chair in a luxury interior setting
```

**Expect:** sandwich → appetizing food treatment (steam, fresh ingredients); chair →
styled-environment product staging. Same checks as A1: no fashion/model language in the
prompts, `reference_image_used: false` warning, product-centric filenames
(`qsr-menu-item-cafe-warm`, `furniture-luxury-interior-...`). Bonus detail: the earbuds
product renders its acronym correctly in prompts ("Pulse ANC Wireless Earbuds", not
"Anc") — visible if you try `Generate a video for the Pulse ANC earbuds`.

### Journey A3 — product-only mode for fashion products (new knob)

```
Generate a product-only video for the sage satin camisole — just the garment, no model. Studio setting.
```

**Expect:** the media agent passes `presentation_mode: "product_only"`; the prompt is a
product hero shot of the camisole (no human), and the filename uses the product-centric
name (`dress-studio-...`), not an ethnicity-prefixed one.

### Journey A4 — asking for a model on a non-wearable fails loudly (no silent fashion shot)

```
Generate a video of a model holding the Aurora cold brew
```

**Expect:** the agent should either explain that model presentation is only supported
for wearables (its instructions now say so), or — if it tries anyway with
`presentation_mode: "with_model"` — the tool returns a **structured error** saying
with-model presentation isn't supported for this category. What must NOT happen: a
fashion-style prompt for the beverage. (Person-using-product shots for non-wearables are
explicitly future work.)

### Journey A5 — the agents no longer claim to be a fashion company

```
What can you do? What kind of products do you work with?
```

**Expect:** the answer describes an **in-store retail media network** for any retail
vertical (beverage, QSR, electronics, furniture, fashion, …). It must not say "fashion
retail company" and must not hard-claim a product count like "22 products" (counts are
now non-numeric in the instructions so they can't drift).

---

## Part B — Regression journeys (workstreams 1–8 fixes, still current)

### Journey B1 — fashion two-stage video generation (ws01/ws06; the release gate)

```
Show me all campaigns
```
```
Generate 1 new video for the sage-satin-camisole product using the two-stage pipeline. Use a studio setting with an elegant mood.
```

**Expect:** 4 seeded campaigns listed; then Stage 1 (scene image) + Stage 2 (Veo, ~1-4
min), success with `sage-satin-camisole-<date>-diverse-studio-elegant.mp4`,
`reference_image_used: true` (fashion products have images). The scene prompt is still
the with-model fashion prompt — note the default model wording is now "a confident,
radiant woman with a warm, engaging presence" (ws09's deliberate rewrite of the old
reductive "diverse → a beautiful woman" mapping). Explicit options still work:
`...with an Asian model` → `asian-studio-elegant` naming.

### Journey B2 — HITL review + activation (ws05)

After B1's video generates:

```
Show me videos pending review
```
```
Activate that video
```
```
What's the status of that video, including how many days of metrics it has?
```

**Expect:** the new video appears pending; activation succeeds; status shows
**30 days** of deterministic metrics seeded on activation (not 7, not random).

### Journey B3 — analytics charts and the no-data guard (ws02)

```
Show me a performance chart for the Blue Floral Maxi Dress campaign
```

**Expect:** a chart artifact renders; no "Invalid metric" (default metric is valid since
ws02).

```
Create a campaign for product 1 at Test Mall in Austin, Texas, then show me its performance chart
```
```
Generate the trendline chart for that campaign anyway
```

**Expect:** no crash — the clean "No metrics data available … activate videos first"
guidance instead of a traceback.

> **What changed in Phase 10 (ws10, playout attribution):** metrics no longer come
> from a per-video daily fraction of the campaign's visits. Activating a video now
> opens deterministic `video_attribution` windows on 2–3 real screens for that
> campaign (`screen_id != campaign_id`); a seeded `AdPlayRecord` schedule says which
> 15-min slots each video actually played on each screen; impressions/circulation
> are summed only over those played slots, and revenue is attributed per play
> window (`play visits × video_rpi`), summing to the same daily `impressions × rpi`
> total. Pausing a video closes its windows (`active_to` set), so its plays stop
> accruing. **What this changes:** the absolute impressions/revenue numbers below
> shifted (they now depend on how many slots a creative won, not a random
> fraction). **What didn't change:** the band [0.03, 0.07] and the
> `revenue ≈ impressions × RPI` invariant — both still hold exactly, and remain the
> thing to actually check (see Journeys B4/B5).

### Journey B4 — deterministic, internally-consistent metrics (ws05/ws07/ws10)

```
Give me the top performing ads for the Sage Satin Camisole campaign, with their impressions, revenue and RPI
```

**Expect (check the arithmetic, not the prose):** every row satisfies
`revenue ≈ impressions × RPI` (cent rounding), RPIs sit in [0.03, 0.07], and in a
multi-creative campaign the RPIs are **not all identical** (per-creative seeded factor,
ws07). Fresh example observed from a `make reset-db`-seeded DB on 2026-07-22 (all
seeding is deterministic — sha256-seeded on campaign/video/screen/day — so a
same-day `make reset-db` reproduces these exactly; the 30-day window rolls with
"today", so totals will drift slightly on a different date): the Sage Satin
Camisole campaign's three creatives came back as
30-day totals of impressions 60,572 / revenue $2,980.15 / RPI 0.0492,
impressions 47,916 / revenue $2,616.21 / RPI 0.0546, and
impressions 60,238 / revenue $2,578.16 / RPI 0.0428 — three distinct RPIs, all inside
[0.03, 0.07], each row's revenue matching impressions × its own RPI to the cent.

### Journey B5 — creative comparison chart (ws07/ws10)

```
Which of the creatives in the Sage Satin Camisole campaign is winning? Show me a comparison chart.
```

**Expect:** a matplotlib chart artifact renders (`artifact_saved: true`); the named
winner has the max RPI; chart numbers match the comparison payload.

### Journey B6 — non-fashion products are first-class in the catalog (ws08)

```
List all products grouped by category
```
```
Add a new product: "Verde Matcha Latte Can", category beverage, description "Ceremonial matcha latte in a 250ml can", price 4.5
```
```
Create a campaign for the Verde Matcha Latte at Whole Foods Midtown in New York
```

**Expect:** fashion + retail categories listed without crashes (retail rows have null
style/color/fabric); self-service product insert works (ws08); the new product's
campaign gets `always-on` category and a product-named description. A video for it
routes to the beverage archetype — unknown categories would fall back to a generic
product-hero shot rather than erroring.

---

## Part C — Status of the issues you reported, and what's deliberately not done

### Your two reported issues (2026-07-19)

1. **"Cold brew video shows a fashion model wearing the product" — FIXED in ws09**
   (this PR). Root cause was the fashion template's `style → category` fallback
   ("wearing a stunning beverage"). Now every category routes to an archetype; verified
   live in demo scenario F5.2 (prompts scanned clean from the DB row, video registered).
   Journey A1 is your direct re-test.

2. **"Products still saved in GCS / broken product links" — NOT fixed in ws09
   (deliberately).** Your local-first decision (2026-07-16) is recorded as the plan:
   local save/load for product images and videos, GCS as opt-in for cloud deploys —
   that's **Phase 15** (`15-product-onboarding.md`, step 1), with the image model work
   in Phase 14a. ws09's contribution: the missing-image case is now **loud and honest**
   (`reference_image_used: false` + explicit warning in every video response) instead of
   silently generating or 404ing. Retail SKUs still have no images at all until 14a/15.

### Also fixed along the way (ws09)

- Campaign descriptions for a product with a color but no style no longer say "fashion
  item" (the last hole from ws08's fallback fix).
- Maps analysis renamed `fashion_market_index` → `retail_market_index`, defaults
  generalized to "retail store" (needs `GOOGLE_MAPS_API_KEY` to test live).
- Malformed video-variation requests now return a structured error listing valid fields
  instead of silently producing a default fashion shot.
- Integration tests' xfail was narrowed to genuine infrastructure errors only.

### Owner feedback from the 2026-07-22 test round — where each item landed

1. **Videos must be music-only with no on-screen text** (brisket badges + speech) —
   **FIXED in ws09/PR #10** (prompt policy across all archetypes; Journey A1b is the
   check). Automated judge verification of actual outputs lands with Phase 16.
2. **Product image links are GCS and 404** — routed to **Phase 15** (its local-first
   step now hardened by amendment: nothing to/from GCS in local mode incl. videos;
   demo asset set ships as a Drive bundle auto-downloaded at setup, all-local after).
3. **Tests must hit the live API** — new **Phase 16** (`16-live-api-testing.md`,
   resolves Q19): fast + live tiers both green, `gemini-3.6-flash` default, live
   Veo/image-gen tests, Gemini-judge review script for generated media.

### Workstream 11a — fixed vs. deliberately not done

- **Fixed:** ws10's carried items 1+2 — the `_load_attribution_windows`
  empty-list `IN ()` guard, and the mock_data/review_tools window-load SQL
  duplication, now live once in `app/demo_data/windows.py` and are shared by
  both call sites.
- **Deliberately not done:** the live/cached BlueZoo conformer for
  `APP_MODE=connected` — that's Phase 11b, tracked as the `RuntimeError` in
  Journey 0b.2 above. Also deliberately deferred: ws10's carried items 3
  (closed-attribution-window history growth) and 4 (repo-wide lint red) —
  owner directed only items 1+2 into this workstream at kickoff.

### Known-not-done (tracked, out of ws09 scope)

- **Integration eval suite is vacuous under pytest** — discovered this workstream:
  `make test-integration` has *never* actually called the LLM (conftest's fake project
  + ADK swallowing inference errors), and the pre-existing eval sets fail when genuinely
  executed. Documented in `CLAUDE.md` (Gotchas) and `99-open-questions.md` **Q19** —
  needs your decision (repairing it makes `make test` spend real LLM calls). Demo
  scenarios (this guide's automated siblings in `docs/demo-scenarios/`) are the real
  behavioral gate meanwhile.
- Product **image generation** for retail SKUs (Phase 14a) and **local-first storage**
  (Phase 15) — see item 2 above.
- Person-using-product shots for non-wearables (model drinking the cold brew etc.) —
  named future work in the phase doc.
- LLM prompt-writer layer for vendor-supplied detail — deferred to Phase 15 as a
  registry extension seam.
- Variation **presets** (`get_variation_presets`) remain fashion-demo-oriented.
- Legacy strings marked accepted-legacy (old single-stage video path, `analyze_image`'s
  "fashion image" prompt, `video_properties.py` garment fields) — inert on the active
  pipeline.
- Same-day filename-collision quirk (see the Setup caveat) — pre-existing; recommended
  for a future bug-fix slot.
