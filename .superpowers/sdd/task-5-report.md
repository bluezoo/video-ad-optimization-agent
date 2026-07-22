# Task 5 Report — Agent instructions/descriptions/APP_DESCRIPTION/campaign copy

BASE: 944a699

## Plan section implemented
Task 5 from plan.md (workstream 09).


## Files changed
- app/agent.py: 5 instruction openers, product-count/fashion-metadata body edits, presentation_mode
  documentation, ethnicity suffix, "Fashion styles performance by geography" -> "Product category
  performance by geography", media_agent description=, Coordinator beverage example query.
- app/config.py: APP_DESCRIPTION -> "Retail ad campaign management agent with video generation for
  in-store media networks".
- app/tools/campaign_tools.py: create_campaign auto-description now checks `style` alone (not
  `style or color`) so a color-only product no longer gets the "fashion item" placeholder.
- tests/unit/test_agent_instructions.py (new): anti-drift net, 4 tests, verbatim from plan.
- tests/unit/test_campaign_tools.py: added test_color_without_style_uses_product_name_not_fashion_item.

## Decisions / judgment calls
- Plan Step 2's "Campaign/Coordinator examples" bullet cites anchors :128/:147/:151-154/:508/:524-525/
  :551-552 as places to "add one beverage example ... where an example query says only dresses". None
  of those anchors is actually phrased as a natural-language user query about dresses specifically —
  they are the four pre-loaded campaign names (kept unchanged per the plan's own "factual" carve-out)
  and the Media Agent bullet list. The only literal natural-language example query in the whole module
  is the Coordinator's "## Workflow Example" section ("I want to promote the black trousers..."), which
  isn't in the plan's anchor list (likely due to line drift across tasks 1-4's edits). I added the
  beverage example query there, immediately after the existing fashion example, using the plan's exact
  suggested string, since that's the only place the instruction's literal intent ("add a beverage
  example query") can attach to.
- Media Agent "Browse available products (22 pre-loaded products)" -> used the plan's literal phrase as
  the object of "from the product catalog" rather than nesting it in parens (which produced ugly
  double-closing-parens); wording is a faithful paraphrase carrying the same catalog-listing content.
- description= review at :165 (campaign_agent), :383 (analytics_agent), :480 (review_agent): none of
  these contained "fashion"/numeric-counts/"model ethnicity" already, so left unchanged; only
  media_agent's description (:263 in file, plan's :261 anchor) needed the rewrite.

## Test output
- pytest tests/unit/test_agent_instructions.py tests/unit/test_campaign_tools.py -v -> 26 passed, 1 skipped
- make test-unit -> 217 passed, 1 skipped
- pytest tests/e2e -v -> 25 passed, 1 skipped
- make lint on touched files (app/agent.py app/config.py app/tools/campaign_tools.py
  tests/unit/test_campaign_tools.py tests/unit/test_agent_instructions.py) -> All checks passed!
  (repo-wide `make lint` still reports the same 44 pre-existing errors in untouched files, confirmed
  identical via `git stash` diff against BASE 944a699)

## Self-review
git diff --stat 944a699..HEAD shows exactly the 5 files listed above touched, matching Task 5's file
list in the plan (app/agent.py, app/config.py, app/tools/campaign_tools.py,
tests/unit/test_agent_instructions.py (new), tests/unit/test_campaign_tools.py). No extraneous files
changed. grep confirms zero "fashion retail company" occurrences and zero "22 pre-loaded products" /
"28 pre-loaded products" occurrences remain in app/agent.py.

## Result
DONE — commit 4a4c4d3 (BASE 944a699..4a4c4d3).
