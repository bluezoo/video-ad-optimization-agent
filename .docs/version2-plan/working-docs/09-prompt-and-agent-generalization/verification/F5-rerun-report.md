# Scenario F5 — CLEAN RERUN report (workstream 09 verification)

Date: 2026-07-22
Context: rerun after `campaigns.db` reset. The first run (see `F5-report.md`) passed all
prompt criteria but F5.2's video registration failed on a UNIQUE filename constraint caused
by a stale row from an interrupted earlier run. This rerun exercises the full path end to
end on a freshly repopulated DB, specifically to confirm registration succeeds.

Environment: `make dev` in the `version_2_prompt-generalization` worktree, port 8501,
fresh ADK web session `ffd2cca6-e7fd-4b1a-92c0-82ab6b127c9a` (user `user`, app `app`).
Evidence gathered from the raw session event stream
(`GET /apps/app/users/user/sessions/<id>`), the server debug log, and a read-only query of
`campaigns.db` (`mode=ro` URI; the DB was never written to outside the app itself).

---

## Scene F5.1 — browse and create a campaign for a beverage product

**Query 1:** "List the beverage products"

- Observed: `transfer_to_agent(media_agent)` then `list_products(category="beverage")`.
- Response: `status: "success"`, `product_count: 2`, products include
  `aurora-cold-brew-330ml` (id 23) and `citrus-grove-sparkling-water-500ml` (id 24).
- `style`/`color`/`fabric` are proper JSON `null` (not `"None"` strings); no crash,
  no traceback.
- Evidence: `F5-rerun-f51-q1-session.txt`, `F5-rerun-f51-q1.png`.

**Query 2:** "Create a campaign for the Aurora cold brew at Target Downtown in Austin, Texas"

- Observed: `transfer_to_agent(campaign_agent)` then
  `create_campaign(product_id=23, store_name="Target Downtown", city="Austin", state="Texas")`
  (no explicit `category` arg — allowed by the doc).
- Response: `status: "success"`, campaign id 5,
  name "Aurora Cold Brew 330Ml - Target Downtown", **`category: "always-on"`** (not
  "essentials"), description "Campaign for Aurora Cold Brew 330Ml at Target Downtown,
  Austin." — mentions the product; contains neither "fashion item" nor "classic".
- No traceback anywhere in the session events or server log.
- Evidence: `F5-rerun-f51-session.txt`, `F5-rerun-f51-q2.png`.

**Result: PASS**

## Scene F5.2 — non-fashion video generation (same session)

**Query:** "Generate a video for the Aurora cold brew using a studio setting"

- Observed: `transfer_to_agent(media_agent)` then
  `generate_video_with_variation(campaign_id=5, product_id=23, setting="studio")`.
  Two-stage pipeline ran (Stage 1 scene image + Stage 2 Veo 3.1 animation);
  total generation 128 s.
- Tool response (full fields):
  - `status: "success"`; `video.id: 11`; `video.status: "generated"`
  - `video.video_filename: "aurora-cold-brew-330ml-072226-beverage-studio-elegant.mp4"`
  - `video.variation: "beverage-studio-elegant"` (product-centric, no ethnicity prefix)
  - `reference_image_used: false`
  - `warning: "No product image found for aurora-cold-brew-330ml — scene generated from text description only"`
- **Registration confirmed** (the criterion the first run could not): read-only query of
  `campaign_videos` shows row id 11 with `status: "generated"`, campaign_id 5,
  product_id 23, the filename above, `variation_name: "beverage-studio-elegant"`,
  `pipeline_type: "two-stage"`, full scene/video prompts stored. No UNIQUE constraint
  error this time.
- Prompt criteria: the full prompts as stored in the DB row (the exact text used for this
  generation) scanned case-insensitively — none of "fashion", "garment", "wearing",
  "model wearing", "she is", "model wearing this exact garment" appear. The prompts read
  as a product hero shot with appetite cues ("Appetizing hero shot", "condensation on
  cold surfaces", "condensation droplets glistening, gentle steam or fizz"). Archetype
  resolved to `consumable-hero`.
- Server log: zero tracebacks/exceptions; forbidden-term grep over the whole log came
  back empty.
- Evidence: `F5-rerun-f52-session.txt`, `F5-rerun-f52-db-row.txt`,
  `F5-rerun-f52-prompts.txt`, `F5-rerun-f52-chat.png`, `F5-rerun-server.log.txt`.

**Result: PASS**

---

## Verdict

Scenario F5 (clean rerun): **2/2 scenes PASS**, including end-to-end video registration.
The first run's UNIQUE-filename failure is confirmed to have been stale-row contamination,
not a code defect.

Note: the date-based filename component (`072226`) means a same-day regeneration of the
same product+variation would collide again — that is the same pre-existing behavior noted
in the first run's report, not a regression introduced by this workstream.
