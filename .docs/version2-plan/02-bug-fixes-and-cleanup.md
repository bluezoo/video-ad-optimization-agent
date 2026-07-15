# Phase 1 — Bug Fixes & Cleanup

## Goal

Fix the live bugs and stale facts already sitting in the codebase, before building anything new on top of them. Everything in this phase is mechanical, independently testable, and carries zero architectural risk — it's confidence-building groundwork, not part of the client's two requests, but doing it now avoids compounding these bugs into the generalization/live-mode work later.

## Current state and steps

### 1. `generate_metrics_visualization()` (and `generate_map_visualization()`) default-metric bug

**Files:** `app/tools/metrics_tools.py:720-1061`, `app/tools/maps_tools.py:858` (confirmed during review to have the identical bug — not mentioned in the original draft of this phase, fold it in here since it's the same fix)

- `metrics_tools.py:723`: the function signature defaults `metric="revenue"`.
- `metrics_tools.py:746`: the `valid_metrics` check does not include `"revenue"` as an accepted value.
- `maps_tools.py:858`: `generate_map_visualization()` has the same invalid `"revenue"` default against its own `valid_metrics` check.
- Result: calling either tool with no explicit `metric` argument (the documented default) raises immediately on its own validation check.

**Important correction — simply adding `"revenue"` to `valid_metrics` does not fully fix this.** The daily metric rows this function builds from (`metrics_tools.py:221`) do not currently include a raw daily revenue figure in their public shape — only derived fields. Adding `"revenue"` to the allow-list without also exposing raw daily revenue in that row shape will pass validation but render zeros. **Fix:** change the default in both functions to `"revenue_per_impression"` (a metric the row shape already supports), OR deliberately add raw daily revenue to the shared row shape and verify both tools render it correctly. Do not treat "add revenue to the allow-list" alone as a complete fix — test that the rendered output actually contains non-zero values.

**Test:** call `generate_metrics_visualization()` and `generate_map_visualization()` with no explicit `metric` argument; assert neither raises on validation, and assert the rendered/returned data is not degenerate (all-zero).

### 2. `generate_metrics_visualization()` null-deref bug

**File:** `app/tools/metrics_tools.py:773, 787`

- Line 773: `summary` is dereferenced inside an f-string (`f"...{summary['total_impressions']:,}..."`).
- Line 787: the `if not daily_metrics:` guard that would catch the "no data" case comes *after* line 773.
- Result: if `summary` is `None` (empty metrics), this raises `TypeError` instead of hitting the intended "no data available" path.

**Fix:** move the `if not daily_metrics:` (or equivalent `summary is None`) guard to before the f-string construction at line 773.

**Test:** call the function for a campaign/date range with zero metrics rows; assert it returns the "no data" response instead of raising.

### 3. Weekly `bar_chart` aggregation bug — flagged here, fixed in Phase 3 (not here, to avoid a double edit)

**File:** `app/tools/metrics_tools.py`, weekly bar_chart branch (~lines 796-800 build per-day values, ~909-916 aggregate them)

- Per-day RPI values (`revenue / impressions` computed once per day) are summed across the week to produce a weekly figure. This is mathematically wrong for a ratio metric: summing 7 daily ratios does not equal the weekly ratio. The correct weekly RPI is `SUM(daily revenue) / SUM(daily impressions)`.
- **This is broader than just RPI**: the same weekly-sum branch also sums `dwell_time`, which is itself an average, not an additive count — summing 7 daily averages is also wrong, for the same underlying reason (it needs a properly weighted average, not a sum), just a different specific fix than RPI's.

**Do not fix this in Phase 1.** Fixing it here and then moving the same logic into Phase 3's shared `compute_rpi()` would mean editing the same code twice. Instead, this item is a **flag, not a fix**: Phase 3 (`04-centralize-rpi-metrics.md`) is where the correct per-metric aggregation rule (ratio-of-sums for RPI, a defined weighted rule for dwell time, plain sum for impressions/circulation/revenue) gets implemented once, and this function is migrated to call it.

**Test (in Phase 3, not here):** construct a fixture with known daily values where "sum of per-day values" and "correctly aggregated weekly value" differ for both RPI and dwell_time, and assert the function returns the correctly-aggregated value for each.

### 4. `get_campaign_locations` reads from legacy tables

**File:** `app/tools/maps_tools.py:56-72`

- Currently queries `campaign_ads` and `campaign_metrics` — legacy tables kept only for migration history (see `app/database/db.py`).
- Current campaigns are recorded in `campaign_videos` and `video_metrics` (`app/database/db.py:139-151` and surrounding schema).
- Result: this tool silently returns incomplete or empty data for any campaign created under the current schema.

**Fix:** point the query at `campaign_videos`/`video_metrics`, matching the join pattern already used correctly elsewhere (e.g., `app/tools/metrics_tools.py`'s `get_campaign_insights()`, which is properly scoped).

**Test:** call `get_campaign_locations` for a campaign created via the current mock data / `create_campaign()` path and assert it returns non-empty, correct location data.

### 5. `CAMPAIGN_CATEGORIES` / DB CHECK constraint drift — dormant today, correct the classification

**Files:** `app/config.py:86`, `app/database/db.py:70`, `app/tools/campaign_tools.py:73`

**Correction from review:** this is not currently a live bug the way items 1-4 are — `create_campaign()` never actually validates against `CAMPAIGN_CATEGORIES` today. Instead, it runs its own hardcoded fashion-category mapping and silently defaults any unrecognized category to `"essentials"` (`campaign_tools.py:73`). The SQLite CHECK constraint (`db.py:70`) is also a hardcoded, independent copy, not generated from `config.py`. So today, `CAMPAIGN_CATEGORIES` and the CHECK constraint disagreeing (the constraint allows `'holiday'`, `config.py` doesn't list it) is **dormant schema/config drift** — it will only bite once something actually validates against `CAMPAIGN_CATEGORIES` (e.g., a future UI dropdown, or once Phase 7 tries to map a non-fashion product's category).

**Fix:** align `CAMPAIGN_CATEGORIES` and the CHECK constraint now, while the mismatch is easy to see and fix, so it doesn't silently resurface during Phase 7. But do not treat "make the two lists match" as solving the deeper problem Phase 7 will hit: `create_campaign()`'s silent fallback-to-`"essentials"` for unrecognized categories means a non-fashion product's category will currently be silently miscategorized rather than erroring — Phase 7 needs to decide whether campaign category should become a free-form/generic taxonomy or a real controlled list with proper validation and an explicit error path, not just a longer hardcoded fashion mapping. Flagged as an open question there, not solved here.

**Test:** assert `set(CAMPAIGN_CATEGORIES) == set(<values extracted from the CHECK constraint>)`. Also add a test asserting what `create_campaign()` currently does with an unrecognized category (documents the silent-fallback behavior explicitly, so Phase 7 has a clear "before" baseline to change deliberately rather than accidentally).

### 6. Stale/incorrect factual references (not vertical-specific — that's Phase 8)

These are copy-paste-drift bugs, not "hardcoded fashion" (which is handled deliberately in Phase 8). Fix them here because they're one-line corrections:

- `app/agent.py:152, 539` — reference "Emerald Satin Slip Dress," a product that no longer exists in mock data. Current mock product is `sage-satin-camisole` (see `app/database/mock_data.py:63-64`, which even has a comment noting the rename). Update references to match current mock data, or better, avoid naming a specific product in agent instructions at all (reduces future drift — revisit if Phase 8 changes how products are referenced anyway).
- `app/agent.py:310` — claims a "90 days" window; `app/database/mock_data.py:383` actually generates 30 days of mock metrics. Correct the instruction text to 30, or reference the config/constant if one exists rather than hardcoding a number that can drift again.
- `app/agent.py:200` (`MEDIA_AGENT_INSTRUCTION`) — claims Stage 1 image generation uses "Gemini 2.0 Flash Exp." After Phase 0, the actual configured model is `gemini-3-pro-image` (GA). Update the instruction text to match `config.py`'s `IMAGE_GENERATION` value, or better, reference it dynamically so this can't drift again.
- `app/tools/video_tools.py:18` — the module docstring ("Stage 1: Scene Image (Gemini 2.0 Flash Exp)") carries the same stale model name. Update it to match `config.py`'s `IMAGE_GENERATION` value. (This is distinct from the `video_tools.py:218` comment and `:966` Veo comment, both of which Phase 0 owns.)
- `README.md:66` — claims the repo "delivers the code for live connectivity to... BlueZoo's BigQuery database." No BlueZoo integration code exists anywhere in `app/` today (confirmed via repo-wide grep). **This phase does not edit `README.md`** — it's client-facing and stays untouched per repo etiquette. Instead, record the correction in `SETUP_INSTRUCTIONS.md`'s "Version 2 workstream setup notes" section: a note that README's BigQuery-connectivity claim is aspirational — no BigQuery connectivity exists yet, and Phase 10 will build the real adapter. The README correction itself is deferred to a client-approved change.

**Test:** none of these need automated tests; they're documentation/instruction text. Do a final grep pass to confirm no other reference to the old product name, the "90 days" figure, or "Gemini 2.0 Flash Exp" remains: `grep -rn "Emerald Satin\|90 days\|Gemini 2.0 Flash Exp" app/` (README.md is out of scope for this phase per item 6, so it's dropped from the grep). Note: a `Gemini 2.0 Flash Exp` hit at `video_tools.py:218` means Phase 0 hasn't run yet — Phase 0 owns that line (and `:966`); this phase owns `video_tools.py:18` and `agent.py:200`.

### 7. Integration eval suite is structurally unable to fail (`pytest.xfail` catch)

**File:** `tests/integration/test_agents.py` (first at ~lines 67-69, same pattern in all six tests)

- Every `AgentEvaluator` call is wrapped in `except Exception: pytest.xfail(...)`, which converts any routing/tool/eval-score failure into an expected-failure rather than a real test failure. The effect is that `make test-integration` cannot fail on genuine agent regressions — the eval suite is structurally unfailable. (This is the CODEX-REVIEW.md:101 "should-fix" that was not folded in during the original correction pass; folded in here on 2026-07-14.)

**Fix:** narrow the `except` so genuine eval failures fail the test. Keep `xfail` ONLY for infrastructure errors (e.g. missing credentials/quota), not for evaluation-score failures — catch the specific infrastructure exception(s) and let `AgentEvaluator`'s assertion failures propagate.

**Test:** deliberately break one eval expectation locally and confirm `make test-integration` actually fails (then revert). (Adding the non-fashion eval *cases* themselves is Phase 8's job — see `09-prompt-and-agent-generalization.md` — since the products they exercise don't exist until the generalization work lands.)

## Validation

- [ ] `make test-unit` covers items 1-3 with new/updated test cases; all pass.
- [ ] `get_campaign_locations` returns correct data for a current-schema campaign (item 4).
- [ ] `CAMPAIGN_CATEGORIES` matches the DB CHECK constraint exactly (item 5).
- [ ] Grep for stale references (item 6) returns nothing.
- [ ] After narrowing the `xfail` catch (item 7), deliberately breaking one eval expectation makes `make test-integration` fail; reverting restores green.
- [ ] Full `make test` suite still passes (no regressions from these fixes).

## Exit criteria

All six items above are fixed, tested, and `make test` is green. No behavior change to anything outside the specific bugs listed.

## Dependencies

None — can start immediately, in parallel with or right after Phase 0. Note the "Gemini 2.0 Flash Exp" cleanup is split across both phases (Phase 0 owns `video_tools.py:218` and `:966`; this phase owns `video_tools.py:18` and `agent.py:200`), so run the final `grep -rn "Gemini 2.0 Flash Exp" app/` validation only after both phases are done.

## Open questions

None — every item here is a verified bug or stale fact, not a design decision.
