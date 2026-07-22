# Workstream 09: prompt-and-agent-generalization

**Branch:** version_2_prompt-generalization
**Phase doc:** .docs/version2-plan/09-prompt-and-agent-generalization.md
**Base:** version_2 @ 170dcbc (post-ws08 merge 5d3e1f8)

## Research findings

Full digest: kickoff workflow wf_461dbb50-872 (3 parallel readers); DISCOVERY entries in
this folder's WORK_LOG (2026-07-21). Summary — every substantive doc claim HOLDS or merely
DRIFTED (line shifts from ws06/ws08 edits), with three corrections now amended into the
phase docs:

1. **Golden tests must be replaced, not "excluded."** Both ws08 goldens pin the
   bare-default variation whose output contains "a beautiful woman" — exactly what step 4
   rewrites. Regenerate on an explicit `model_ethnicity` + add a direct assertion for the
   new "diverse" wording. "a beautiful woman" is also the `ethnicity_map.get()`
   miss-fallback (prompt_builders.py:66/:299) — both sites change.
2. **video_tools.py is a first-class scope item** the doc missed: Stage-1 reference-image
   preamble (:233, "model wearing this exact garment") is UPSTREAM of the prompt builders
   on the active pipeline — the cold-brew bug cannot be fixed in prompt_builders alone;
   analyze_video's prompt (:141/:156) is fashion-framed; the flattened
   `generate_video_with_variation` wrapper (:1854-1922) needs the new knob + a
   `product_only` filename branch; the silent dict-validation fallback (:492-499) would
   turn a malformed request into a default fashion shot — must become loud. Plus the four
   `LlmAgent description=` strings (coordinator routes on them; one still says "22
   products") and inconsistent product counts (agent.py :186/:261 say 22; :193/:524 say 28).
3. **Phase 2 item 7's xfail narrowing never happened** — folded into this workstream
   (step 7's eval cases can't fail without it). 02 doc amended with provenance.
4. `campaign_tools.py:108` still emits "Campaign for fashion item in {color}…" for any
   product with a color attribute but no style (ws08's fallback only covered
   neither-style-nor-color). `fashion_market_index` rename has an in-file consumer at
   maps_tools.py:1179. `test_null_style_falls_back_to_category` deliberately pins the
   cold-brew fallback and gets consciously rewritten this phase.

## Implementation approach

**The design decision (options A–D from the ws08 amendment), recommendation: B —
vertical-archetype template registry with a deterministic generic fallback.**

- **A. `presentation_mode` branch only (doc as written):** one generic `product_only`
  template next to the preserved fashion path. Smallest diff, but every non-fashion
  vertical gets the same flat "product on a surface" prompt — doesn't deliver "its own ad
  visuals per product type," and a second generalization pass becomes inevitable.
- **B. Archetype registry + deterministic fallback (RECOMMENDED):** a small registry maps
  product category → prompt archetype; each archetype is a deterministic template (same
  style as today's fashion builders) filled from the typed `Product` + generic
  `CreativeVariation` fields:
  - `wearable` (dress/top/pants/skirt/outerwear/footwear) → the EXISTING fashion
    with-model path, byte-preserved for explicit-ethnicity inputs (golden-pinned);
  - `consumable-hero` (beverage, qsr-menu-item) → appetizing product-hero shot
    (condensation/steam, ingredients, no human);
  - `staged-product` (electronics, furniture, home-appliance) → styled-environment
    product staging with feature emphasis (no human);
  - `product-hero` (any unknown category — the self-service catch-all) → clean generic
    hero shot built from name/description/attributes.
  `presentation_mode` still lands on `CreativeVariation` per the doc (override knob:
  `product_only` forces a product-centric archetype even for wearables; `with_model` on a
  non-wearable errors loudly this phase rather than silently producing a fashion shot).
  Deterministic → golden-testable per archetype; a new vertical = a registry entry, no
  rebuild; a vendor's never-seen category still works via `product-hero`.
- **C. LLM prompt-writer:** maximally flexible, but adds a nondeterministic LLM call
  inside currently-deterministic tools — goldens impossible, cost/latency per generation,
  quality variance in front of prospects. Rejected as the primary mechanism this phase.
- **D. Hybrid B+C (LLM fallback for unknown categories):** the unknown-category case is
  already served deterministically by B's `product-hero`; the LLM layer's real value
  arrives with Phase 15's vendor onboarding (tailoring from vendor-supplied detail).
  Deferred to Phase 15 as an explicit extension seam on the registry, not built now.

**The other steps follow the phase doc as amended:** optional human-model fields on
`CreativeVariation`; non-reductive "diverse" wording (both map entry and `.get()`
fallback); one-pass rewrite of the five agent instructions + four agent `description=`
strings + `APP_DESCRIPTION` + campaign-description text (fixing the color-no-style
"fashion item" hole) + maps defaults/prompts (renaming `fashion_market_index` →
`market_index` incl. its :1179 consumer); video_tools.py active-path fixes (reference
preamble branches by archetype, analyze_video prompt generalized, loud validation
fallback, `generate_video_with_variation` gains `presentation_mode` + product-only
naming); product counts in instructions become non-numeric ("the product catalog") so
they can't drift again; xfail narrowing + 2-3 non-fashion eval cases; legacy-only
strings (video_tools :63-90/:807-812/:1481, video_properties.py garment fields) marked
accepted-legacy, not rewritten.

## Test plan

Per the owner's instruction, tests are updated WITH the changes and the suite runs to
green before verification (implementation uses the ws08-style loop-until-green stabilize
phase):

- **Unit:** regenerate the two goldens on explicit `model_ethnicity="asian"` (regression
  pair proving the wearable path is unchanged for non-default inputs); new direct
  assertions for the new "diverse" wording; a golden per new archetype (beverage/
  electronics/unknown-category fixtures) asserting zero garment/model/wearing language;
  rewrite `test_null_style_falls_back_to_category` → beverage now routes to
  `consumable-hero` (asserts no "wearing", no "None"); campaign-description tests incl.
  the color-no-style case; maps default/rename tests; loud-fallback test for malformed
  variation dicts; instruction-content greps (no "fashion retail company" in any
  instruction/description string).
- **Integration:** narrowed xfail (infrastructure-only), then 2-3 non-fashion eval cases
  (beverage list→campaign routing; QSR video-generation routing) wired into
  `make test-integration`; deliberate-break check that the suite can actually fail.
- **Demo scenarios (verifying-with-demo-scenarios):** F1 scenes 1-2 (fashion two-stage
  generation — the regression gate: byte-identical prompts for explicit-ethnicity
  wearables) + **new Scene F5.2**: generate a video for `aurora-cold-brew-330ml` and
  assert from the trace that the scene/video prompts contain no
  fashion/garment/wearing/model-ethnicity language and the campaign artifacts render —
  the direct re-test of the owner's reproduced cans-dress failure.

## Out of scope

- Image generation/upload/storage for retail SKUs and the local-first storage seam
  (Phase 15; Phase 14a for the image model). F5.2 runs with no reference image — the
  loud "no reference image" surfacing IS in scope, generating the image is not.
- Person-using-product shots for non-wearables (the doc's named future work; all
  non-wearable archetypes are product-only this phase).
- LLM prompt-writer layer (deferred to Phase 15 as a registry extension seam).
- `PRESET_VARIATIONS` overhaul (presets stay fashion-demo-oriented; at most a minimal
  product-only preset group if the plan finds it cheap).
- `app/models/video_properties.py` legacy garment-typed fields; legacy
  campaign_images-path prompt strings (marked accepted-legacy).
- README.md, DEMO_GUIDE.md (untouched per repo etiquette).
