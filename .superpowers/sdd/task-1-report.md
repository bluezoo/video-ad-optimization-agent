# Task 1 Report: Re-baseline golden prompts on explicit asian ethnicity

## Base SHA
8021123

## Summary
Task 1 successfully re-baselines the golden prompt tests from generic "golden-baseline" variation to explicit "golden-baseline-asian" with model_ethnicity="asian". This captures the reference output for the wearable regression bar required by the Global Constraints.

## Work Completed

### Step 1: Capture new goldens from UNMODIFIED code
- Ran Python script to generate golden files with `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")`
- Generated two new golden files:
  - `tests/unit/data/golden_scene_prompt_product1_asian.txt`
  - `tests/unit/data/golden_creative_prompt_product1_asian.txt`

### Step 2: Verify captured files
- Scene prompt contains: "a graceful Asian woman with sleek dark hair"
- Creative prompt contains: "a graceful Asian woman with sleek dark hair"
- Neither prompt contains "a beautiful woman" ✓
- Both files properly formatted and contain full prompt text

### Step 3: Rewrite TestGoldenPrompts
- Updated `tests/unit/test_product_adapter.py` lines 50-60 (test_scene_prompt_unchanged, test_creative_prompt_unchanged)
- Changed variation from `CreativeVariation(name="golden-baseline")` to `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")`
- Changed golden file paths from `golden_*_product1.txt` to `golden_*_product1_asian.txt`
- Left `test_null_style_falls_back_to_category` untouched (Task 3 will rewrite it)

### Step 4: Run tests
- Ran `pytest tests/unit/test_product_adapter.py -v` → all 11 tests PASS
- Ran `make test-unit` → 191 passed, 1 skipped (pre-existing skip)
- All golden prompt tests pass ✓

### Step 5: Commit
- Committed with exact message from plan: `test: re-baseline golden prompts on explicit asian ethnicity (ws09 Task 1)`
- Commit: e84ff2dfc212445d042d50179db33d7e55f3b678
- Changed 3 files: renamed 2 golden files, updated test file with 6 insertions/4 deletions

## Testing Summary
- **Unit tests**: 191 passed, 1 skipped
- **Golden prompt tests**: All 3 pass (test_scene_prompt_unchanged, test_creative_prompt_unchanged, test_null_style_falls_back_to_category)
- **Lint check**: Modified file passes ruff cleanly

## Verification Checklist
- [x] Step 1: Captured new goldens from unmodified code
- [x] Step 2: Verified captured files contain expected text and exclude "a beautiful woman"
- [x] Step 3: Rewrote TestGoldenPrompts with new variation and golden file paths
- [x] Step 4: All named tests pass + make test-unit green
- [x] Step 5: Committed with plan's commit message

## Notes
- The pre-existing lint errors in the full codebase (54 errors in other files) are not addressed as they're unrelated to Task 1
- The new golden files encode the wearable regression bar and will be kept byte-identical through all subsequent tasks per Global Constraints
- No code behavior changed, only test baselines and expectations

## Commit Range
BASE: 8021123
HEAD: e84ff2d
