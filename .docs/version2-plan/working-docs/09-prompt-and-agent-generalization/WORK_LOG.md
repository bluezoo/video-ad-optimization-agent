# Workstream 09 — prompt-and-agent-generalization — WORK_LOG

Append-only durable history (see tracking-workstream-progress). Branch:
`version_2_prompt-generalization`, base: version_2 @ 170dcbc (post-ws08 merge 5d3e1f8).

## 2026-07-21 — checkpoint 1: kickoff — worktree created
Worktree `.claude/worktrees/version_2_prompt-generalization` on branch
`version_2_prompt-generalization` off version_2. Dependency check: Phase 8 merged
(5d3e1f8) per STATUS.md. Inputs noted from ws08: (a) prompt-construction approach
options A-D (09 doc amendment, working-doc gate decision); (b) retail core set
`app/database/retail_products_data.py` is the required e2e input (beverage + QSR
primary); (c) reproduced failure example: cans-dress video for aurora-cold-brew-330ml
(ws08 WORK_LOG 2026-07-19 DISCOVERY — "wearing a stunning beverage" prompt).
Phase-doc research: pending (amended into this entry when done).

## 2026-07-21 — checkpoint 1 amendment: phase-doc research done (ultracode fan-out, 3 agents)
All substantive claims HOLD or DRIFTED (line-number shifts from ws06/ws08 edits); full digest
in kickoff research (workflow wf_461dbb50-872). Three DISCOVERY items:

### DISCOVERY 1: 09 doc's golden-exclusion premise is wrong
Assumed (09 doc, validation bullet 1): existing goldens can be kept and the default-variation
case "excluded" from comparison. Actual: BOTH ws08 goldens (tests/unit/data/golden_*_product1.txt,
pinned by tests/unit/test_product_adapter.py:46-60) use the bare-default variation whose output
contains "a beautiful woman" — exactly the text step 4 removes. No non-default golden exists.
Fix path: regenerate goldens on an explicit model_ethnicity (regression pair) + add a direct
assertion for the new "diverse" wording. Also: goldens use bare CreativeVariation() defaults,
NOT get_default_variation() (different lighting/activity) — two distinct "default variation"
notions the doc conflates. Blast radius: 09 doc (amended), this workstream's plan.

### DISCOVERY 2: video_tools.py fashion surface absent from 09 doc inventory
The doc's inventory + validation grep (step 5) name agent.py/config.py/campaign_tools.py/
maps_tools.py/prompt_builders.py only. Missing, on the ACTIVE two-stage path: the Stage-1
reference-image preamble video_tools.py:233 ("model wearing this exact garment" — UPSTREAM of
build_scene_image_prompt, so a product_only branch alone cannot fix the cold-brew bug),
analyze_video's prompt :141/:156, plus legacy-path strings (:63-90, :807-812, :1481) and module
docstring :20. Also missing surfaces: the four LlmAgent description= params (agent.py:165/:261/
:381/:480 — coordinator routes on them; :261 still says "22 pre-loaded products"), and the
flattened generate_video_with_variation wrapper (:1854-1922) which needs the presentation_mode
param + filename naming branch (:1898 name flows into filename/DB). Blast radius: 09 doc
(amended — inventory + grep list), this workstream's plan.

### DISCOVERY 3: Phase 2 item 7's xfail narrowing was never implemented
Assumed (09 doc step 7 + 02 doc item 7): ws02 narrowed the broad `except Exception: pytest.xfail`
catch in tests/integration/test_agents.py. Actual: all six tests still swallow everything
(:73-75, :90-91, :106-107, :122-123, :138-139, :157-158); ws02's WORK_LOG shows the item was
silently dropped from its executed scope. 09 step 7's new eval cases can't fail without it —
folding the narrowing into ws09 scope. Blast radius: 02 doc (amended with provenance), 09 doc
(amended), this workstream's plan.

Other notable research facts for the plan: "a beautiful woman" is ALSO the ethnicity_map .get()
miss-fallback (prompt_builders.py:66/:299); campaign_tools.py:108 "fashion item" fallback still
fires for color-without-style products; fashion_market_index key has an in-file consumer at
maps_tools.py:1179; test_null_style_falls_back_to_category pins the cold-brew fallback and must
be consciously rewritten; generate_video_from_product's silent validation fallback (:492-499)
would silently turn a malformed product_only request into a with_model fashion shot — make loud;
agent.py product counts inconsistent (:186/:261 say 22, :193/:524 say 28); F5 has no
video-generation scene — verification needs a new F5.2.

## 2026-07-21 — checkpoint 2: working doc approved
Owner approved the six-dimension restatement and chose **Option B: vertical-archetype
template registry** (wearable = preserved fashion path; consumable-hero; staged-product;
generic product-hero fallback for unknown categories; presentation_mode as override knob;
LLM prompt-writer deferred to Phase 15 as a registry extension seam). Proceeding to
writing-plans.

## 2026-07-21 — checkpoint 3: plan approved
Owner approved the 8-task plan (plan.md in this folder). Execution: ultracode workflow,
sequential implementer->reviewer per task (Task 1 golden re-baseline first, from
unmodified code), then loop-until-green stabilize (full make test + integration), then
demo verification F1 / F5.1 / new F5.2.

## 2026-07-21 — Task 1 implemented
**Re-baseline golden prompts on explicit asian ethnicity (code untouched)**

All steps completed per plan.md:
- Step 1: Captured new goldens from UNMODIFIED code via Python script with `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")` — generated `golden_scene_prompt_product1_asian.txt` and `golden_creative_prompt_product1_asian.txt`
- Step 2: Verified both golden files contain "a graceful Asian woman with sleek dark hair" and do NOT contain "a beautiful woman" ✓
- Step 3: Rewrote `tests/unit/test_product_adapter.py::TestGoldenPrompts` (lines 50-60) to use `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")` and point to `*_asian.txt` files; left `test_null_style_falls_back_to_category` untouched for Task 3
- Step 4: All tests pass — `pytest tests/unit/test_product_adapter.py -v` (11/11 pass), `make test-unit` (191 passed, 1 skipped)
- Step 5: Committed `test: re-baseline golden prompts on explicit asian ethnicity (ws09 Task 1)` (commit e84ff2d)

**Test output summary:** make test-unit = 191 passed, 1 skipped (pre-existing e2e skip). Golden prompts are now the wearable regression bar, pinned to explicit-ethnicity output per Global Constraints.

Commit range: 8021123..e84ff2d

## 2026-07-21 — Task 2 implemented
**presentation_mode + Optional human-model fields on CreativeVariation**

All steps completed per plan.md:
- Step 1: Modified `app/models/variation.py`:
  - Added `presentation_mode: str | None` field with description (None/"auto"/"with_model"/"product_only")
  - Changed `model_ethnicity`, `model_description`, `activity` to `str | None` (types become Optional, defaults RETAINED)
  - Updated `get_summary()` with guard: `(self.model_ethnicity or "diverse") != "diverse"`
  - Modernized type hints: `list[str]` and `dict[str, Any]` syntax
- Step 2: Added three test methods to `tests/unit/test_video_tools.py::TestCreativeVariation`:
  - `test_presentation_mode_defaults_to_none` ✓
  - `test_presentation_mode_accepts_product_only` ✓
  - `test_human_fields_accept_none` ✓
- Step 3: All tests pass — `pytest tests/unit/test_video_tools.py tests/unit/test_product_adapter.py -v` (all pass), `make test-unit` (194 passed, 1 skipped)
- Step 4: Committed `feat: add presentation_mode + Optional human-model fields to CreativeVariation (ws09 Task 2)` (commit f881f5b)

**Test output summary:** make test-unit = 194 passed, 1 skipped. Golden prompts remain byte-identical (Task 1 regression bar verified). New Optional fields default to sensible values, preserving wearable output compatibility while enabling product-centric builders downstream.

Commit range: e84ff2d..f881f5b
