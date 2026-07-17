# Phase 4 — Centralize RPI/Metric Computation

## Goal

Replace the independent, ad-hoc metric computations scattered across the codebase (a dozen-plus sites, precise inventory below) with calls to one shared function per metric, built on the definitions from Phase 3. This is what makes the Phase 2 weekly-RPI bug (and any similar bug) structurally impossible to reintroduce elsewhere.

## Current state

**Correction from review: the inventory below is the corrected, fuller list** — the first draft of this phase missed several sites and mischaracterized one as an already-correct "reference implementation."

- `app/database/mock_data.py:168-235` — `_generate_mock_video_metrics()`
- `app/tools/review_tools.py:454-513` — a second, separate `_generate_mock_video_metrics()` (see Phase 5 — this duplication is fixed there, but both currently compute RPI inline too)
- `app/tools/review_tools.py:862` — `get_video_details()` also computes RPI inline (missed in the first draft of this inventory)
- `app/tools/metrics_tools.py:169-283` — `get_campaign_metrics()`

> **Amended (workstream 02, 2026-07-14):** `get_campaign_metrics` returns `summary=None` while still reporting `status="success"` when no activated-video rows have impressions in the window (metrics_tools.py). Workstream 02 guarded the one crash this caused, but the odd contract itself is left for this phase's centralization to normalize (e.g. always return a zeroed summary, or a distinct status).

- `app/tools/metrics_tools.py:285-412` — `get_top_performing_ads()` — note its docstring/contract explicitly promises results **"across all campaigns"** with no campaign/date parameters; see the corrected step 4 below (do not silently change this to scoped-only behavior).
- `app/tools/metrics_tools.py:415-605` — `get_campaign_insights()` — **correction: this is not an already-correct reference implementation.** Its signature takes only `campaign_id` (no date-range parameter, `metrics_tools.py:415`), and its "RPI trend" actually compares revenue totals, not RPI (`metrics_tools.py:467`). Its "best/worst day" logic also selects individual `video_metrics` rows without grouping by day (`metrics_tools.py:493`) — meaning "best day" may actually mean "best single video-day row," not an aggregated day. This function needs its own repair alongside the migration, not to be used as the template.
- `app/tools/metrics_tools.py:608-717` — `compare_campaigns()`
- `app/tools/metrics_tools.py:720-1061` — `generate_metrics_visualization()` (weekly-sum bug flagged in Phase 2, fixed here)
- `app/tools/campaign_tools.py:184-292` — `get_campaign()`
- `app/tools/maps_tools.py:559`, `app/tools/maps_tools.py:585` — two inline RPI computations inside `get_campaign_map_data()` (def at `:399`), missed in the first draft.
- `app/tools/maps_tools.py:963`, `app/tools/maps_tools.py:1013` — two more inline RPI computations, missed in the first draft. (The complete `maps_tools.py` set is exactly {559, 585, 963, 1013}.)

> **Amended (workstream 04, 2026-07-16):** re-verified post-workstream-02/03 — the `maps_tools.py` set is now {558, 584, 962, 1011-1013} (lines shifted by ws02 edits; the 1011-1013 site is one statement). The rest of the inventory re-confirmed complete via the repo-wide grep.

Before starting, re-run `grep -rn "revenue" app/tools/ app/database/ --include="*.py"` yourself and treat this list as a starting checklist, not a guaranteed-complete inventory — the point of this phase is that after it, that grep only matches the shared module and its callers.

## Steps

1. Create a `compute_rpi(total_revenue, total_impressions)` function as **pure arithmetic** — sum revenue, sum impressions, divide once, no query/scoping logic inside it — in a shared module (`app/tools/metrics_shared.py` is a reasonable name; check this repo's existing module conventions before choosing). Handle the zero-impressions case explicitly (return `0.0` or `None` — pick one and document it in `docs/METRICS.md` from Phase 3). Also add a `compute_weighted_average(rows, value_field, weight_field)` (or similar) for the dwell-time aggregation case identified in Phase 2, item 3 — dwell time is not a ratio-of-sums metric like RPI, it needs its own correctly-weighted rule.
2. Fix `get_campaign_insights()` (`app/tools/metrics_tools.py:415-605`) as part of this phase, not treated as already-correct: add proper date-range scoping to its signature, fix its RPI trend to use `compute_rpi()` instead of comparing raw revenue totals, and fix its best/worst-day logic to group by day before comparing (rather than comparing individual video-metric rows). Once fixed, this becomes a genuinely good scoping example for the other call sites — but it isn't one yet.
3. Migrate the remaining call sites (listed above) to call `compute_rpi()` / `compute_weighted_average()` instead of recomputing the math inline. This is a mechanical refactor — no output should change for any call site that was already computing the ratio-of-sums correctly; outputs **will** change for `generate_metrics_visualization()`'s weekly view and for `get_campaign_insights()`'s RPI trend (both are the bugs being fixed).
4. **Correction on `get_top_performing_ads()`**: do not silently narrow it to campaign/date-scoped-only, since its current contract is explicitly global ("top performing ads across all campaigns") and something may already rely on that. Instead, add **optional** `campaign_id`/date-range filter parameters that narrow the result when provided, while preserving the current unscoped behavior as the default when they're omitted. This is an enhancement to a documented contract, not a bug fix to a broken one.
5. Do not touch `_generate_mock_video_metrics()` in either `mock_data.py` or `review_tools.py` in this phase beyond making them call `compute_rpi()` for the RPI figure they store — the deeper fix (making them a single deterministic generator) is Phase 5.

> **Amended (workstream 04, 2026-07-16):** Step 5 is vacuous as written — neither `_generate_mock_video_metrics()` stores an RPI figure or divides revenue by impressions; both synthesize `revenue` as impressions × an RNG rate (multiplication only: `mock_data.py:223-224`, `review_tools.py:482/503`). Verified during this workstream's migration sweep; no change made to either generator. Phase 5 still owns their unification.

## Validation

- [ ] Unit test `compute_rpi()` and `compute_weighted_average()` directly: known value pairs, including a zero-impressions case, an all-equal-daily-values case (where sum-of-ratios and ratio-of-sums coincidentally agree — doesn't prove correctness), and an unequal-daily-values case (where they must differ, catching regressions).
- [ ] For each migrated call site, add or update a test that asserts the returned value matches the shared function applied to the same underlying rows — i.e., the call site is a thin wrapper, not an independent calculation.
- [ ] `get_campaign_insights()` is properly date-scoped, its RPI trend uses `compute_rpi()`, and its best/worst-day logic groups by day — three separate test cases, since these are three separate fixes bundled into one function.
- [ ] `get_top_performing_ads()`'s default (no-filter) behavior is unchanged (still global/unscoped); a test confirms the new optional filters narrow results correctly when supplied.
- [ ] Full `make test` suite passes; specifically re-run the Phase 2 weekly-RPI regression test and confirm it still passes now that the logic lives in the shared function.

> **Amended (workstream 04, 2026-07-16):** no weekly-RPI regression test exists — Phase 2 (workstream 02) deferred the fix and only flagged the bug with a KNOWN-BUG comment (`metrics_tools.py:918-922`); no test mentions "week" anywhere under tests/. This phase must *write* that regression test, not re-run it.

## Exit criteria

Every metric-computation call site identified above (and any others found via the repo-wide grep in "Current state") calls the shared `compute_rpi()`/`compute_weighted_average()` instead of reimplementing the math. `get_campaign_insights()` is properly scoped and its RPI/best-day logic is correct. No remaining inline `revenue / impressions` (or equivalent) division outside the shared module.

## Dependencies

Phase 3 (`docs/METRICS.md` definitions must exist first).

## Open questions

None — this is a mechanical refactor and targeted repair of already-identified call sites, not a new design decision.
