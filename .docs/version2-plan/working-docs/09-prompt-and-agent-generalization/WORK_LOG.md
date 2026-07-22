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
