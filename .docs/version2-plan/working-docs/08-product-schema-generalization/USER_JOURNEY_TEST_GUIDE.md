# Manual User-Journey Test Guide — Version 2, Workstreams 1–8

**Purpose:** owner-driven acceptance test of everything delivered in workstreams 1–8, run
against the ws08 worktree (branch `version_2_product-schema`, PR #9) **before** the final
merge. This worktree contains all merged workstreams 1–7 *plus* workstream 8, so one
session covers the cumulative state.

**How to use it:** each journey is a sequence of chat queries to type into the ADK web UI
(http://localhost:8501). Every step lists **what you're testing** (which workstream fixed
it), **what to type**, and **what you should see**. Anything marked ❌ is an explicit
fail condition — if you see it, stop and report it. The Trace tab (per response) shows
which tools fired if you want to verify beyond the chat text.

---

## Setup (already done for you if the server is running)

1. Run everything from the ws08 worktree, not the main checkout.
2. `make reset-db` is **mandatory** before this test: workstream 8 changed the campaigns
   table's CHECK constraint (added `always-on`), and SQLite can't alter constraints on an
   existing DB. A stale DB will reject non-fashion campaign creation.
3. `make dev` → http://localhost:8501, select the app, start a new session.
4. `app/.env` must have `GOOGLE_CLOUD_LOCATION=global` (Gemini 3.x requirement, ws01).

**Fresh-DB baseline you should expect everywhere:**
- **28 products** (22 fashion + 6 retail test SKUs — ws08)
- **4 seeded campaigns** (e.g. `sage-satin-camisole - The Grove`, Blue Floral Maxi
  Dress, …)
- All seeded videos already **activated** with **30 days** of deterministic metrics each

---

## Journey A — Fashion end-to-end: browse → generate → review → activate

*Covers: ws01 (current model IDs — the release gate), ws02 (stale product/model
references removed), core HITL flow, ws05 (deterministic activation metrics).*

| Step | Type this | Expect |
|---|---|---|
| A1 | `Show me all campaigns` | `list_campaigns` fires; the 4 seeded campaigns listed, incl. `sage-satin-camisole - The Grove`. ❌ Any mention of "Emerald Satin Slip Dress" (stale name ws02 removed). |
| A2 | `Show me all products` | 28 products across fashion + retail categories (dress, top, pants, skirt, outerwear, beverage, electronics, furniture, qsr-menu-item, home-appliance). ❌ Count of 22 (retail seeding missed) or literal `None` strings in product fields. |
| A3 | `Generate 1 new video for the sage-satin-camisole product using the two-stage pipeline. Use a studio setting with an elegant mood.` | Stage 1 scene image, then Stage 2 Veo animation (**takes ~1–4 min**; polling is normal). Success message with a video filename like `sage-satin-camisole-<MMDDYY>-….mp4`, status generated / pending review. ❌ Model-not-found or permission error (would mean ws01's model currency regressed), any traceback. |
| A4 | `Show me videos pending review` | Review tool lists the new video from A3 (seeded ones are already activated, so this list should basically be just yours). |
| A5 | `Activate that video` | Activation succeeds and (ws05) seeds a deterministic 30-day metrics window for it — the response or a follow-up status check should show ~30 days of metrics, not 7, and no wording about "random" generation. |

> A3 costs a real Veo call. If you want to keep the run cheap, you may skip A3–A5 —
> ws05's determinism is also verified in Journey B (B3/B4) against seeded videos.

---

## Journey B — Analytics correctness: charts, guards, deterministic numbers

*Covers: ws02 (default-metric bug, no-data crash), ws04 (centralized RPI, correct
weekly aggregation), ws05 (deterministic 30-day windows, consistent numbers).*

| Step | Type this | Expect |
|---|---|---|
| B1 | `Show me a performance chart for the Blue Floral Maxi Dress campaign` | A chart artifact renders in the UI. ❌ "Invalid metric" (ws02's default-metric bug back from the dead), all-zero chart. |
| B2 | `Create a campaign for product 1 at Test Mall in Austin, Texas, then show me its performance chart` — then, as a follow-up: `Generate the trendline chart for that campaign anyway` | Campaign created; the chart request returns the **clean guidance** "No metrics data available … activate videos first" (agent may phrase it, pointing you to review/activation). ❌ A traceback / TypeError (ws02's null-deref regression). |
| B3 | `What's the status of video 1, including how many days of metrics it has?` | Status **activated**, **30** metric days. ❌ 7 days (old generator), any other count. |
| B4 | `Generate 3 more days of metrics for video 1` then `How many days of metrics does video 1 have now?` | `days_generated: 3`, then exactly **33**. ❌ Off-by-anything, or a second run of this pair not continuing deterministically. |
| B5 | `Give me the top performing ads for that campaign, with their impressions, revenue and RPI` (the campaign video 1 belongs to — its name is in B3's response) | **Check the arithmetic yourself:** for every row, `revenue ≈ impressions × its RPI` (cent rounding), every RPI within **[0.03, 0.07]**, and — in a multi-creative campaign — **not all RPIs identical** (ws07's per-creative factor). ❌ Any row where revenue/impressions disagrees with its own stated RPI; any RPI like 0.08–0.15 (legacy generator range). |
| B6 | `Show me a weekly bar chart of RPI for the Sage Satin Camisole campaign` | Weekly RPI bars stay in the **same [0.03–0.07] band** as daily. ❌ Weekly values around ~0.25–0.35 — that's 7 daily ratios *summed*, the exact ws04 aggregation bug. |
| B7 *(optional — needs `GOOGLE_MAPS_API_KEY`)* | `Show me the locations for the Sage Satin Camisole campaign on a map` | Non-empty location data / map for a current-schema campaign (ws02 pointed this at the current tables; before, it silently returned nothing). |

---

## Journey C — Creative comparison: "which ad is winning?" (the client's core question)

*Covers: ws07 (creative-level RPI comparison + deterministic matplotlib chart).*

| Step | Type this | Expect |
|---|---|---|
| C1 | `Which of the creatives in the Sage Satin Camisole campaign is winning? Show me a comparison chart.` | A PNG chart artifact renders (deterministic matplotlib bar chart, not an AI-drawn image). The named winner's RPI is the **maximum** of the listed per-creative RPIs. Numbers in the chart match the numbers in the text. ❌ No chart, winner ≠ max RPI, RPIs all identical, or chart numbers ≠ text numbers. |
| C2 | Re-ask C1 in a **new session** (top-left, new session) | Same creatives, same RPIs, same winner — determinism across sessions (ws05+ws07). ❌ Different numbers on the re-run. |

---

## Journey D — Non-fashion retail products (the ws08 headline)

*Covers: ws08 (typed vertical-agnostic Product model, 6-SKU retail core set, themed
campaign taxonomy with `always-on` default + validated explicit category).*

The 6 retail SKUs: `aurora-cold-brew-330ml`, `citrus-grove-sparkling-water-500ml`
(beverage), `smoky-brisket-stack-sandwich` (qsr-menu-item), `pulse-anc-wireless-earbuds`
(electronics), `nordic-oak-lounge-chair` (furniture), `crispwave-air-fryer-5l`
(home-appliance).

| Step | Type this | Expect |
|---|---|---|
| D1 | `List the beverage products` | Both beverage SKUs, described from their attributes (roast notes, size, …). ❌ Crash, or fields showing literal `None` (the old dict path did exactly that for non-fashion rows). |
| D2 | `Create a campaign for the Aurora cold brew at Target Downtown in Austin, Texas` | Campaign created with **category `always-on`** — the deliberate non-fashion default. Description mentions the product ("Aurora Cold Brew … at Target Downtown, Austin"). ❌ Category `essentials` (the old **silent** fallback ws08 removed), any fashion wording ("fashion item", "classic") in the description. |
| D3 | `Create a holiday campaign for the crispwave air fryer at Lowes Central in Denver, Colorado` | Explicit category honored: campaign category = `holiday`. (Explicit valid categories now override the mapping — ws08's Option A.) |
| D4 | `Create a campaign for the earbuds at Best Buy Plaza in Seattle, Washington with category "clearance"` | A **clean, structured rejection**: `clearance` isn't a valid theme; the response lists the valid values (summer, formal, professional, essentials, holiday, always-on). ❌ A silently created campaign with some other category, or a traceback. |
| D5 | Repeat D2-style creation for one or two more verticals (sandwich / lounge chair) | Same pattern: success, `always-on`, product-specific description. |
| D6 *(optional, costs a Veo call)* | `Generate a video for the Aurora cold brew` | **Known limitation, not a failure:** the video pipeline runs, but the Veo prompt still uses fashion wording ("fashion photography", "garment", "fabric flow") — prompt generalization is **Phase 9**, the next workstream. Judge D6 only on "does it run without crashing", not on prompt quality. |

---

## Journey E — Self-service: a vendor's brand-new product, on the fly

*Covers: ws08's self-service substrate (`insert_product`) — the scenario "BlueZoo's
vendor asks: can you run MY product through it?". The chat-facing `create_product` tool
lands in Phase 15; today the insert is one command, and everything downstream of it must
just work with zero code changes.*

**E1 — insert the vendor product** (run in a terminal in the worktree, server can stay up):

```bash
.venv/bin/python -c "
from app.models.product import Product
from app.database.db import insert_product
p = insert_product(Product(
    name='vendor-demo-trail-shoe',
    category='footwear',
    description='Lightweight waterproof trail running shoe with recycled mesh upper',
    image_filename='vendor-demo-trail-shoe.jpg',
    attributes={'colorway': 'moss green', 'weight_grams': 240, 'terrain': 'trail'},
))
print('inserted id', p.id)
"
```

Expect: `inserted id 29` (or next free id). Note the image file doesn't exist — that's
allowed by design (image is reference-only; vendor images or nano-banana generation get
wired in Phases 14a/15).

| Step | Type this (in the chat) | Expect |
|---|---|---|
| E2 | `List the footwear products` | The trail shoe appears immediately — no restart, no reseeding. Its attributes (moss green, 240 g, trail) come through in the description. |
| E3 | `Create a campaign for the vendor demo trail shoe at REI Flagship in Portland, Oregon` | Campaign created, category `always-on` (footwear isn't in the theme mapping), description names the product. ❌ Any crash on the never-seen-before category. |
| E4 | `Show me the performance chart for that campaign` | The clean no-data guidance from B2 (new campaign, no activated videos) — proving the whole analytics path tolerates an on-the-fly product too. |

**E1-dup (optional):** run the E1 command a second time → it should raise
`sqlite3.IntegrityError` (duplicate name), *not* silently insert a duplicate.

---

## Journey F — Cross-cutting sanity (quick)

| Step | What / how | Expect |
|---|---|---|
| F1 | Skim any analytics answer's terminology | Consistent with `docs/METRICS.md` (ws03): "impressions", "RPI (revenue per impression)", "dwell time" — no invented metric names. |
| F2 *(optional, needs server restart)* | Stop the server, `APP_MODE=bogus make dev` | Startup **fails fast** with a ValueError naming valid modes (ws06). Then restart normally (no APP_MODE / `demo`) — everything works as before. `connected` mode is accepted but inert until Phase 11. |

---

## Result sheet

Mark each journey as you go; anything not-PASS blocks the PR #9 merge until triaged.

| Journey | Result | Notes |
|---|---|---|
| A — fashion end-to-end | ☐ PASS ☐ FAIL ☐ SKIPPED | |
| B — analytics correctness | ☐ PASS ☐ FAIL | |
| C — creative comparison | ☐ PASS ☐ FAIL | |
| D — retail products | ☐ PASS ☐ FAIL | |
| E — self-service on the fly | ☐ PASS ☐ FAIL | |
| F — cross-cutting | ☐ PASS ☐ FAIL ☐ SKIPPED | |

**Known limitations (expected, do not report as failures):**
1. Veo prompts still fashion-worded for non-fashion products — Phase 9 (next).
2. Retail SKUs appear in the demo catalog alongside fashion (28 products) — the
   `DEMO_DATASET` separation knob is Phase 15.
3. No chat-facing "add a product" tool yet — Phase 15 wraps `insert_product` (Journey E
   proves the substrate).
4. Retail SKU image files don't exist on disk — reference-only by design until 14a/15.
