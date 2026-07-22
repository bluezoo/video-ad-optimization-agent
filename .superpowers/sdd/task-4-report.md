# Task 4 report — video_tools.py active-path generalization

BASE sha: be1ad14

## Plan re-read notes / decisions

- Task 3 (archetype registry + prompt_builders dispatch) is already committed at BASE
  (be1ad14). `resolve_archetype`, `WEARABLE`, etc. exist in `app/tools/prompt_archetypes.py`
  and are used by `app/tools/prompt_builders.py`.
- `tests/conftest.py::test_db` copies the main `campaigns.db`, which already contains the
  ws08 retail core test set (verified `get_product_by_name("aurora-cold-brew-330ml")` returns
  a beverage product, id 23) because `init_database()` calls `populate_retail_test_products()`.
  So the Step 6 tests can use `test_db` directly without needing `retail_db`/`fresh_test_db`.
- Campaign id=1 and product id=1 both exist in the seeded DB (dress/trousers), so the
  "malformed variation" test hits the variation-validation branch before any campaign/product
  mismatch guard — matches the plan's assumption.
- Docstring anchor ":194-196"/":265-268" "product: dict -> product: Product": the actual
  signatures for `generate_scene_image` and `animate_scene_with_veo` read
  `product: dict[str, Any]` even though callers always pass a real `Product` object (stale type
  hint from before the generic Product model existed, Phase 8). Changed the type annotation to
  `Product` on both functions and imported `Product` from `..models.product`. Also reworded the
  Args docstring line "Product dictionary with metadata" -> "Product object with metadata" for
  consistency with the corrected type (not explicitly required by the plan's literal text, but
  it was inconsistent to leave "dictionary" wording next to the corrected type hint).
- Module docstring line 20 ("- Output: Scene-ready first frame (model wearing product)"): the
  plan's quoted target text ("Stage 1: Scene Image (configured image model)") duplicates the
  existing Stage 1 header line 18 almost verbatim and doesn't fit grammatically as a
  replacement for the "Output:" bullet. No test covers this docstring. Used judgment: reworded
  the bullet to acknowledge both archetypes instead of assuming a human model:
  "- Output: Scene-ready first frame (model wearing product for wearables; product-centric hero
  shot otherwise)". This removes the fashion-only assumption while staying accurate, in the
  spirit of "drop fashion/model-name staleness" from Step 5.
- `save_video_metadata` (line 373, `product: dict[str, Any]`) is NOT in the Task 4 file-anchor
  list — left untouched.
- Legacy-path strings (`generate_video_prompt` :63-90, and other non-anchored regions) left
  untouched per the plan's explicit "Do NOT touch" instruction.
- `reference_image_used` / `warning` keys added at the TOP LEVEL of the success payload dict
  (sibling to `status`/`video`/`prompts`), matching how the F5.2 demo scenario doc (Task 8,
  not in scope here) describes checking `reference_image_used` directly on the tool response.

## Steps

(See commit log / diff for the actual code — this section tracks test runs.)

## Test runs

- `pytest tests/unit/test_video_tools.py -v` → 22 passed (includes the two new
  `TestVariationValidationLoud` tests).
- `make test-unit` → 212 passed, 1 skipped.
- `pytest tests/unit/test_product_adapter.py -v` → 11 passed (golden regression bar for
  product 1 / asian ethnicity remains byte-identical — Task 4 did not touch
  `prompt_builders.py` or `prompt_archetypes.py` at all).
- `make test-e2e` → 25 passed, 1 skipped.
- `make lint` (repo-wide) → 44 pre-existing errors, same count as BASE (verified via
  `git stash` + `make lint` on BASE, matching Task 3's WORK_LOG-documented baseline).
  `ruff check app/tools/video_tools.py tests/unit/test_video_tools.py` (this task's two
  touched files) → "All checks passed!" (one import-order issue I introduced in the new
  test class was fixed before this final run).

## Pre-existing state discovered at start

`git status` at the start of this task (I only ran `git rev-parse --short HEAD` initially,
then `git status` once `make lint` showed a different pre-existing-error count than
expected) showed the Task 3 implementer's `WORK_LOG.md` and `.superpowers/sdd/progress.md`
entries were already written but never committed (BASE commit be1ad14 only touched code/
test files per `git show --stat`). This is not something I introduced — I left the
pre-existing Task 3 entries in place and appended my own Task 4 entries below them in both
files, per my own step 6 instructions. Following the same pattern already established for
Tasks 1-3, I left these two bookkeeping files uncommitted (not folded into the Task 4 code
commit) since my instructions treat the commit (step 4) and the WORK_LOG/progress append
(step 6) as separate actions.

## Commit

`944a699` — `feat: archetype-aware video pipeline, loud variation errors, reference-image
surfacing (ws09 Task 4)`, containing exactly `app/tools/video_tools.py` and
`tests/unit/test_video_tools.py` (verified via `git diff be1ad14..944a699 --stat`).

## Self-review against Task 4 spec

- Step 1 (reference-image preamble branch + archetype param + ValueError wrapping): done,
  transcribed verbatim from the plan.
- Step 2 (loud variation validation, both the dict branch and the final `else`): done.
- Step 3 (`reference_image_used` + conditional `warning` in success payload): done.
- Step 4 (`presentation_mode` param on `generate_video_with_variation` + product-centric
  naming block): done, transcribed verbatim.
- Step 5 (stale-text cleanups: module docstring, analyze_video prompt x2, docstring type
  hints x2): done, with the two judgment calls noted above (module docstring wording; the
  "product: Product object" docstring rewording is additional clarity, not required
  verbatim by the plan but consistent with the corrected type hint).
- Step 6 (tests): both tests transcribed verbatim and passing.
- Step 7 (test commands): all run and green/clean (scoped to this task's files for lint,
  matching the workstream's established precedent for the pre-existing 44 lint errors).
- Step 8 (commit message): matches exactly.
- Confirmed `git diff BASE..HEAD --stat` shows only the two files the plan's "Files:"
  section names — nothing extra, nothing missing.
