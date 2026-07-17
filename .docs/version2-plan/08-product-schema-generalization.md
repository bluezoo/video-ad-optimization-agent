# Phase 8 — Product Schema Generalization

## Goal

Make the `products` table and its Python-side handling vertical-agnostic, so a non-fashion product (e.g., a beverage, an electronics SKU, a QSR menu item) can be created and run through the full pipeline without touching fashion-specific columns. This is the data-layer half of the client's first request; Phase 9 does the prompt/agent-instruction half.

## Why this is smaller than it looks

`app/database/db.py:92` already has a generic `metadata TEXT` (JSON) column on the `products` table, alongside the fashion-specific columns (`style`, `color`, `fabric`, `occasion` — lines 84-88). This means the schema already has an escape hatch for vertical-specific attributes; the work here is making that the *primary* path for new products, not adding it from scratch, and doing an additive migration rather than a breaking one.

## Current state

**Correction from review: `metadata` is not actually unused.** Every seeded product is already serialized into the `metadata` column at write time (`app/database/db.py:351`). The real gap is on the *read* side: `get_product()` returns the raw SQLite row dictionary without parsing that JSON back out (`app/database/db.py:375`), and the video pipeline consumes that raw dictionary directly (`app/tools/video_tools.py:477`). So the actual missing piece isn't "wire up the metadata column" — it's "add a row↔model adapter that parses `metadata` on read and gives callers a typed object," plus migrating `video_tools.py` and any other consumer off the raw-dict shape.

- `app/database/db.py:84-92` — `products` table has fashion-typed columns (`style`, `color`, `fabric`, `occasion`) plus the already-populated-but-unparsed `metadata TEXT` JSON column.
- `app/database/db.py:375` (`get_product()`) — returns a raw dict; does not deserialize `metadata`.
- `app/tools/video_tools.py:477` — consumes that raw dict directly; this call site needs to move to the typed model once it exists.
- `app/database/products_data.py` — the entire seeded catalog (22 products) is fashion (dress/pants/skirt/top/outerwear), with no non-fashion example anywhere in the codebase to prove genericity.
- `app/tools/campaign_tools.py:66` (`create_campaign()`) — hardcodes a `category_mapping` dict literal that maps fashion product categories to campaign categories, and **silently defaults any unrecognized category to `"essentials"`** (the fallback itself is at `:73`) rather than erroring (see Phase 2, item 5 — this is dormant drift today, but it's exactly what a non-fashion product's category will hit).
- **Correction from review — the category problem is more structural than a mapping fix.** `Product.category` is meant to be an open, vertical-agnostic value, but campaigns validate against a closed SQLite CHECK constraint (`app/database/db.py:70`). Feeding an arbitrary non-fashion product category straight into that closed list cannot work as-is. This phase needs to explicitly decide: is *campaign* category a separate, small, controlled taxonomy (theme/objective, like "seasonal" or "always-on") that's independent of *product* category (which can be anything), or does the campaign CHECK constraint need to become a free-form field? Don't conflate "product taxonomy" and "campaign category" as the same problem — they're different concepts that happen to share a mapping function today.
- No Pydantic model represents "a product" generically today — `app/models/variation.py`'s `CreativeVariation` is about a video's creative treatment, not the underlying product.

## Steps

1. Define a `Product` Pydantic model (new file, e.g. `app/models/product.py`, matching the pattern already used for `CreativeVariation` in `app/models/variation.py`) with a small set of **required, generic** fields (id, name, category, primary image reference, short description) and one `attributes: dict` field backed by the existing `metadata` JSON column for anything vertical-specific (style/color/fabric/occasion for fashion, or whatever fields a different vertical needs — no fixed schema for this field, by design).
2. Add the row↔model adapter this phase actually needs: update `get_product()` (`app/database/db.py:375`) to parse `metadata` and return (or be wrapped by a function that returns) a `Product` instance, and migrate `app/tools/video_tools.py:477` to consume the typed model instead of the raw dict. This is the concrete piece of "wiring up" the schema — not a config toggle, an actual data-flow change with its own test.
3. Migrate the DB additively: keep `style`/`color`/`fabric`/`occasion` as nullable columns (do not drop them — the 22 existing fashion products keep working unchanged). No destructive migration, no data loss, no forced rewrite of `products_data.py`'s existing entries.
4. Add a second seed dataset — a small (5-10 item) **non-fashion** product catalog (pick one concrete vertical to prove genericity with; this is a product/business call worth a quick check with the client rather than an arbitrary technical choice — see open questions) using the `attributes` JSON path instead of the fashion-typed columns. This becomes the test fixture proving the schema is actually generic, not just theoretically capable of being.
5. Decide and implement the product-category vs. campaign-category resolution from "Current state" above, then fix `create_campaign()`'s hardcoded `category_mapping` (`app/tools/campaign_tools.py:66`) accordingly — using the corrected `CAMPAIGN_CATEGORIES` from Phase 2, item 5, and replacing the silent `"essentials"` fallback with an explicit, deliberate behavior (error, or a genuine "uncategorized" bucket — a conscious choice either way, not an accident).
6. **Do not build product CRUD tools in this phase — but they are now committed scope elsewhere.** *(Amended, workstream replan-data-track, 2026-07-16: the owner decided from-scratch product onboarding is a real requirement — Q8 is answered "yes." Product CRUD (agent tools + CLI wrapper: `create_product`, `import_products_from_folder`, `generate_product_image`) lives in Phase 15, `15-product-onboarding.md`, which depends on this phase's `Product` model and adapter. This phase's job is unchanged: build the typed model/adapter/migration that Phase 15's tools will call. Products remain seeded via `products_data.py` and the new non-fashion fixture file within this phase.)*

## Validation

- [ ] Existing 22 fashion products still load and display correctly through `get_product()`'s new typed return, unchanged (regression test — nothing about this phase should degrade the current fashion demo).
- [ ] `app/tools/video_tools.py:477` correctly consumes the typed `Product` model, including its parsed `attributes`, for at least one existing fashion product (proves the adapter migration didn't break the primary video pipeline).
- [ ] The new non-fashion fixture catalog (step 4) can be created (via direct seed, not a CRUD tool) and retrieved via `get_product()` with `attributes` populated and correctly parsed.
- [ ] `create_campaign()`'s resolved category behavior (step 5) is tested explicitly for both a fashion and a non-fashion product category, including whatever the new deliberate "unrecognized category" behavior is.
- [ ] `make test-unit` pass, including new tests using the non-fashion fixture data and the `get_product()`/`video_tools.py` adapter migration.

## Exit criteria

**Narrower than the first draft, deliberately** (per review: full non-fashion video generation needs Phase 9's prompt changes too, so it can't be this phase's exit bar). This phase exits when: a non-fashion product can be persisted, retrieved via `get_product()` as a typed `Product` with parsed `attributes`, and successfully used to create a campaign — with zero references to fashion-specific columns or a silent category fallback in the code paths exercised. Full end-to-end non-fashion image/video generation is proven in Phase 9, which depends on this phase's `Product` model existing.

## Dependencies

Phase 2 (corrected `CAMPAIGN_CATEGORIES`).

## Open questions

1. **Which non-fashion vertical should the proof-of-genericity fixture use?** This should match whatever BlueZoo customer/vertical is most relevant to show next (BlueZoo's own marketed verticals are out-of-home advertising, retail, hospitality, and smart cities — none of which are fashion-specific) — worth a quick confirmation with the client rather than picking arbitrarily.
2. **Is campaign category a controlled taxonomy independent of product category, or should it become free-form?** This determines whether step 5's fix is "add a small campaign-theme enum separate from product category" or "loosen the DB CHECK constraint" — a real design decision, not a mechanical mapping fix.
3. ~~Product CRUD is intentionally out of scope for this phase (see step 6) — flag only as backlog if a future demo genuinely needs to create products live rather than via seed fixtures.~~ **Answered (owner, 2026-07-16): yes, it's needed** — from-scratch onboarding is a stated goal; CRUD tools are Phase 15 (`15-product-onboarding.md`). Still out of scope for *this* phase.
