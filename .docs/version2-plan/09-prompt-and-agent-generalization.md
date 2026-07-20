# Phase 9 — Prompt & Agent Instruction Generalization

## Goal

Remove the hardcoded fashion assumptions from prompt construction and agent instructions, using the generic `Product` model from Phase 8 as the input instead of fashion-specific fields.

## Current state

**Correction from review: the fashion-hardcoding surface is bigger than agent instructions + prompt builders.** The first draft of this phase only covered `app/agent.py` and `app/tools/prompt_builders.py`. A fuller inventory, confirmed during review:

- `app/agent.py` — all five agent instructions (Coordinator, Campaign Agent, Media Agent, Review Agent, Analytics Agent — lines 122, 180, 289, 387, 487) hardcode "fashion retail company" framing directly in the instruction text.
- `app/config.py:83` — `APP_DESCRIPTION` is itself fashion-specific.
- `app/tools/campaign_tools.py:83` — campaign descriptions default to referencing a "fashion item" when none is supplied.
- `app/tools/maps_tools.py:141` — `search_nearby_stores` defaults `business_type="fashion store"`.
- `app/tools/maps_tools.py:229` — `get_location_demographics` hardcodes a fashion-specific demographic index per city.
- `app/tools/maps_tools.py:858` — the map visualization tool exposes a "Fashion styles" concept directly in its output.
- `app/tools/prompt_builders.py` (`build_scene_image_prompt()`, `build_video_animation_prompt()`, `build_creative_prompt()`) — hardcode an `ethnicity_map` (e.g., lines 56-64, 289-297) with entries like `"a graceful Asian woman with sleek dark hair"` and, notably, `"a beautiful woman"` for the `"diverse"` key — a reductive, non-descriptive fallback that's worth fixing on its own merits, independent of generalization. There is also a `garment_desc`/`garment_type` variable pair assuming every product is a wearable garment.
- `app/models/variation.py` — `CreativeVariation` mixes generic scene fields (`setting`, `mood`, `energy`, `camera_movement`, `camera_angle`, `lighting`, `visual_style`, `color_grading`, `time_of_day`, `weather`, `season`) with human-model-specific fields (`model_ethnicity`, `model_description`, `activity`, `props`) that don't apply to every product category. `PRESET_VARIATIONS` is entirely model-driven (diversity/settings/moods all assume a human model is in every shot). **Note: `props` is already a generic list field** (not fashion-typed) — it doesn't need to become nullable just because some of its *preset values* happen to be fashion-oriented; only `model_ethnicity`, `model_description`, and `activity` are the genuinely human-model-specific fields that need to become optional.
- No code path exists today for a product-only shot (no human model at all) — every generation assumes a person wearing/holding/using the product.
- `app/models/variation.py:301` (assignment; function def at `:297`) — the *default* variation already sets `model_ethnicity="diverse"`. This matters for the validation strategy in step 4 below.

## Steps

1. Add a `presentation_mode` concept — **placed on `CreativeVariation`, not `Product`** (corrected from the first draft's suggestion of putting it on `Product`): review correctly pointed out that the same product may legitimately need both a product-only shot and a lifestyle/with-model shot across different creative variations, so this is a property of an individual creative treatment, not a fixed property of the product itself. Values: `"with_model"` vs `"product_only"`. Existing variations default to `"with_model"` (preserves current behavior exactly).
2. In `app/tools/prompt_builders.py`, branch on `presentation_mode`: keep the existing model-driven prompt construction (garment/ethnicity/activity fields) exactly as-is for `"with_model"`, and add a new, simpler prompt path for `"product_only"` that describes the product, setting, mood, lighting, camera work — the fields already generic in `CreativeVariation` — without any human-model fields at all.
3. Make `model_ethnicity`, `model_description`, and `activity` on `CreativeVariation` optional (`Optional[...] = None`), and have `prompt_builders.py` skip that part of the prompt entirely when `presentation_mode == "product_only"` or when they're unset, rather than requiring a value or defaulting to something meaningless. Leave `props` as-is (already generic, not part of this change).
4. Fix the `ethnicity_map`'s reductive `"diverse"` entry (`"a beautiful woman"`) to something actually descriptive and non-reductive, while you're already touching this function. **This intentionally changes output for the default variation** (`variation.py:301` sets `model_ethnicity="diverse"` by default) — call this out explicitly as an intentional, expected change, and exclude the default-variation case from whatever golden/regression comparison step 6 below uses, rather than trying to make it byte-for-byte identical to the old (reductive) output.
5. Rewrite the five agent instructions in `app/agent.py`, `APP_DESCRIPTION` (`config.py:83`), the campaign-description default (`campaign_tools.py:83`), and the map tool defaults (`maps_tools.py:141, 229, 858`), plus the remaining fashion-framed prompt bodies the validation grep surfaces (e.g. `maps_tools.py:761` "Editorial fashion magazine aesthetic", the fashion-categories infographic prompt at `maps_tools.py:1122-1157`, and the `fashion_market_index` usage at `maps_tools.py:1172`/`:1202`), to remove hardcoded fashion framing. Replace with generic retail/advertising framing that references the active product's category dynamically (from the `Product` model) rather than assuming a vertical in the text/defaults itself. Do this as one pass across all of these — they're the same kind of edit repeated across files, not independent design decisions.
6. Re-run the Phase 8 non-fashion fixture catalog through the full pipeline (product → prompt → image → video) using `presentation_mode="product_only"`, and confirm the generated prompts contain no fashion/garment/model language.
7. Add non-fashion routing eval cases to `tests/integration/eval_sets/` (the `AgentEvaluator` suite currently exercises fashion queries only), so the generalization this phase claims is checked by the deterministic eval suite, not only by the browser demo scenario. Keep it small — 2-3 cases exercising a non-fashion product through create-campaign and analytics routing. (This is the second half of the eval should-fix whose first half — narrowing the `pytest.xfail` catch so the suite can actually fail — is Phase 2, item 7 in `02-bug-fixes-and-cleanup.md`; both are needed for these new cases to be meaningful.)

## Validation

- [ ] Fashion products with `presentation_mode="with_model"` and a **non-default, explicit `model_ethnicity`** produce prompts equivalent to today's output for the same inputs (a golden-output regression test) — explicitly excluding the default-variation case, since step 4 intentionally changes that one.
- [ ] The corrected default-variation output (using the new, non-reductive "diverse" wording) is asserted directly, as its own test — not compared against the old output.
- [ ] Non-fashion fixture products (`presentation_mode="product_only"`) produce prompts with no garment/ethnicity/model language — a test asserting the output string doesn't contain any of the model-specific field names' typical values.
- [ ] All five agent instructions, `APP_DESCRIPTION`, the campaign-description default, and the map tool defaults no longer contain hardcoded fashion framing — `grep -rn "fashion" app/agent.py app/config.py app/tools/campaign_tools.py app/tools/maps_tools.py app/tools/prompt_builders.py` returns nothing outside of comments explaining historical defaults (a judgment call, not a hard requirement). **Expected survivors in `prompt_builders.py`:** the `with_model` (fashion) prompt path is intentionally preserved this phase, so hits inside that path (e.g. the 'elegant fashion piece' fallbacks at `:43`/`:53`/`:283`/`:286`, and 'wearing a stunning {garment_desc}' at `:147`/`:373`) are expected and acceptable; any `fashion` hit *outside* the `with_model` path is a failure.
- [ ] `make test-unit`, `make test-e2e` pass; `make test-integration` (real LLM) run manually against both a fashion and a non-fashion product to sanity-check actual generated output quality, not just prompt-string structure.
- [ ] The new non-fashion routing eval cases (step 7) are present in `tests/integration/eval_sets/` and pass under `make test-integration` — and, given Phase 2 item 7's narrowed `xfail`, would actually fail if routing regressed.

## Exit criteria

The full pipeline (including map tools and campaign descriptions, not just prompt construction) runs correctly for both a fashion product (`with_model`, unchanged behavior aside from the deliberate ethnicity-wording fix) and a non-fashion product (`product_only`, new behavior), with no hardcoded vertical assumptions left in prompt construction *outside the `with_model` (fashion) prompt path, which is intentionally preserved*, nor in agent instructions, campaign defaults, or maps tool defaults. Generalizing the `with_model` path itself for non-fashion products (a person using/holding a non-garment product) is explicitly out of scope for this phase and is named as future work.

## Dependencies

Phase 8 (`Product` model and non-fashion fixture data must exist first).

> **Amended (workstream 08, 2026-07-20):** the "Phase 8 non-fashion fixture
> catalog" is the multi-vertical retail core test set in
> `app/database/retail_products_data.py` (five verticals — use the beverage
> and QSR SKUs as primary e2e inputs). Note also: (a) create_campaign now
> takes an explicit validated `category` theme param this phase's instruction
> rewrite should surface to the agent; (b) create_campaign's auto-description
> was minimally generalized in ws08 (name-based fallback when style/color are
> absent) — this phase's step 5 still owns making that text vertical-aware.

## Open questions

None new beyond Phase 8's — this phase is the mechanical follow-through on the schema decisions made there.
