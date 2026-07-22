# Task 3 report — archetype registry + product-centric builders + diverse rewording

BASE sha: c569b74
HEAD sha: be1ad14

## Plan section implemented
"### Task 3: Archetype registry + product-centric prompt builders + diverse-wording fix" from
`.docs/version2-plan/working-docs/09-prompt-and-agent-generalization/plan.md`.

## Files touched (as planned)
- Create: `app/tools/prompt_archetypes.py` (transcribed verbatim from plan Step 2)
- Modify: `app/tools/prompt_builders.py` (Step 3: dispatchers + renamed wearable builders +
  wording/None-guard fixes + new product-centric builders)
- Test: `tests/unit/test_prompt_archetypes.py` (new, verbatim from plan Step 1),
  `tests/unit/test_product_adapter.py` (rewrote `test_null_style_falls_back_to_category` per
  plan Step 3.4)

## Decisions / faithfulness notes
- `prompt_archetypes.py` has no license header, matching `app/models/product.py` (a comparable
  newer Phase-8 file that also omits it) and the plan's own code block, which has none either.
- Public dispatcher docstrings were shortened to single-line per the plan's exact example for
  `build_scene_image_prompt`; applied the same pattern to `build_video_animation_prompt` and
  `build_creative_prompt` (plan says "same pattern... for the animation and creative builders").
- Renamed private wearable builders keep their original multi-line docstrings (unchanged body
  text) since the plan only specifies renaming, not docstring rewrites, for these functions.
- Collapsed the dead if/else at the top of the scene builder into one assignment per the plan's
  explicit instruction ("output-identical, reviewer-noted").
- None-guards applied exactly as specified: `ethnicity_map.get(variation.model_ethnicity or
  "diverse", <new-fallback-string>)` in both wearable scene + creative builders;
  `pose_map.get(variation.activity or "walking", ...)` in scene; `activity_animation.get(...)`
  in animation; `activity_map.get(variation.activity or "walking", variation.activity)` in
  creative (second/fallback arg for this one call left as `variation.activity` per plan,
  unreachable as None since "walking" is always a map key).
- `test_null_style_beverage_routes_to_product_prompt` transcribed with `self` only (no
  `test_db` fixture) — matches the plan's literal code block; the test doesn't touch the DB.
- Ran `ruff check --fix` on the new test file to fix one auto-fixable import-ordering nit
  (blank line between `import pytest` and local imports) — purely cosmetic/mechanical,
  no content change.

## Test output

`pytest tests/unit/test_prompt_archetypes.py tests/unit/test_product_adapter.py -v`
→ 27 passed (0 failed).

`make test-unit` → 210 passed, 1 skipped (pre-existing e2e-adjacent skip, unrelated).

`make lint` (repo-wide) → 44 errors remain, ALL in files outside this task's scope
(`app/models/video_properties.py`, `app/storage.py`, `app/tools/review_tools.py`,
`app/__init__.py`, `app/agent_engine_app.py`, `app/database/products_data.py`,
`app/models/__init__.py`, `app/tools/__init__.py`, `app/tools/image_tools.py`,
`tests/conftest.py`, `tests/unit/test_maps_tools.py`, `tests/unit/test_metrics_tools.py`).
Verified via `git stash` that BASE (c569b74) already had 45 pre-existing lint errors in
these same files before any Task 3 change — my one contribution (the test-file import
order) is now fixed, dropping the count from 45 to 44. Scoped lint on exactly the four
files this task touches/creates
(`app/tools/prompt_archetypes.py app/tools/prompt_builders.py
tests/unit/test_prompt_archetypes.py tests/unit/test_product_adapter.py`) →
`All checks passed!`.

Golden byte-identity for product 1 / `CreativeVariation(name="golden-baseline-asian",
model_ethnicity="asian")`: `test_scene_prompt_unchanged` and `test_creative_prompt_unchanged`
both pass with an exact `==` comparison against the Task-1 golden files — confirms the
wearable regression bar holds.

Banned-term check (`fashion`, `garment`, `wearing`, `she is`, `model wearing`, case-insensitive):
verified absent from `build_scene_image_prompt`/`build_video_animation_prompt`/
`build_creative_prompt` output for beverage/electronics/unknown-category products via
`TestProductCentricPrompts` in the new test file — all pass.

New diverse wording ("a confident, radiant woman with a warm, engaging presence") verified
present (map entry AND `.get()` fallback, both prompt_builders.py sites) via
`TestDiverseWordingFix` — both tests pass, and "a beautiful woman" is confirmed absent from
both the default-diverse and unknown-ethnicity ("martian") cases.

## Self-review (git diff BASE..HEAD)

`git diff c569b74..HEAD --stat`:
```
 app/tools/prompt_archetypes.py       |  51 +++++++++
 app/tools/prompt_builders.py         | 199 ++++++++++++++++++++++++++++++++---
 tests/unit/test_product_adapter.py   |  21 ++--
 tests/unit/test_prompt_archetypes.py | 107 +++++++++++++++++++
 4 files changed, 352 insertions(+), 26 deletions(-)
```
Matches exactly the plan's "Files" list for Task 3 — nothing missing, nothing extra (the
`.superpowers/sdd/*.md` report/progress files and WORK_LOG.md entry are intentionally left
uncommitted/out-of-diff bookkeeping, consistent with Task 1's precedent).

## Commit
`be1ad14` — `feat: archetype registry + product-centric prompt builders + non-reductive diverse wording (ws09 Task 3)`
No Co-Authored-By / AI-attribution trailer. README.md and DEMO_GUIDE.md untouched.
