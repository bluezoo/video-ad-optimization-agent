# Workstream 04: centralize-rpi-metrics

**Branch:** version_2_centralize-rpi-metrics
**Phase doc:** .docs/version2-plan/04-centralize-rpi-metrics.md

## Research findings

Every phase-doc claim re-verified against current code (base 925bdbd, post-workstream-03; ws02's edits shifted most cited lines by 1-4 — corrected inventory below is current):

- **Complete python-level RPI inventory** (`revenue / impressions` divisions): metrics_tools.py:217, 248, 352, 554, 658; campaign_tools.py:254 (`get_campaign` def :188); maps_tools.py:558, 584 (`get_campaign_map_data` def :398), 962, 1011-1013 (`generate_map_visualization` def :857); review_tools.py:862 (`get_video_details` def :778). **SQL-level ratios:** metrics_tools.py:307 (`SUM(vm.revenue) / NULLIF(SUM(vm.impressions), 0)` in `get_top_performing_ads`), :494 and :506 (per-row `rpi` in `get_campaign_insights` best/worst-day queries). Derived `rpi*1000`: metrics_tools.py:256, 674; campaign_tools.py:263. RNG-based rpi in the two mock generators (mock_data.py:223-224, review_tools.py:482/503 — multiplication, not division; Phase 5 owns their unification). The phase doc's maps_tools set {559, 585, 963, 1013} is now {558, 584, 962, 1011-1013}; otherwise the doc's inventory is complete — the repo-wide grep found nothing it missed.
- **`get_campaign_insights` (def :413) — all three defects confirmed:** (a) signature takes only `campaign_id`, no date range; (b) "RPI trend" at :484-488 compares raw revenue halves (`first_half_rev` vs `second_half_rev * 1.1`) then reports "Campaign RPI is trending upward" (:540); (c) best/worst-day queries (:492-514) select individual `video_metrics` rows ordered by per-row rpi with no GROUP BY date — "best day" is actually "best single video-day row."
- **`get_top_performing_ads` (def :283) contract confirmed:** docstring says "across all campaigns," signature has no campaign/date params — the doc's do-not-silently-narrow correction stands.
- **`get_campaign_metrics` `summary=None` contract confirmed unchanged** (:243-244 set `summary = None` when no activated rows have impressions, returned under `status: "success"` at :268-277). ws02's guard lives in the *caller* (`generate_metrics_visualization` :768-779), exactly as the phase doc's ws02 amendment records.
- **Weekly ratio-sum bug confirmed** at metrics_tools.py:923 (`week_total = sum(d["value"] for d in week_slice)`), under the ws02 KNOWN-BUG comment (:918-922). `generate_metrics_visualization` itself computes no other RPI — it consumes `get_campaign_metrics` output.
- **DIVERGENCE — the "Phase 2 weekly-RPI regression test" the Validation section says to re-run does not exist.** `grep -rni "week" tests/` returns nothing; ws02 only flagged the bug with the comment. This workstream must *write* that regression test, not re-run it. Phase doc to be amended with provenance.
- **Nothing shared exists yet:** no `metrics_shared.py`, no `compute_rpi`/`compute_weighted_average` anywhere in app/ or tests/. `app/tools/prompt_builders.py` proves non-`*_tools` helper modules already live in `app/tools/`, so `app/tools/metrics_shared.py` fits conventions (relative imports, e.g. `from ..database.db import get_db_cursor`).
- **Dwell-time aggregation candidates:** the clearest broken case is maps_tools.py:1008-1010 — regional `avg_dwell_time` is an unweighted mean of per-campaign averages. The many SQL `AVG(dwell_time_seconds)` sites (11 across 4 files) are row-level averages over video-day rows.
- **Test coverage today:** per-function test classes exist for all touched tools (test_metrics_tools.py, test_campaign_tools.py, test_maps_tools.py, test_review_tools.py); no weekly regression test (above).

## Implementation approach

Exactly the phase doc's five steps, with these concretizations (no genuine design fork — the doc itself declares open questions: none; micro-decisions recorded for the record):

1. **Create `app/tools/metrics_shared.py`** with two pure functions, no DB access:
   - `compute_rpi(total_revenue, total_impressions) -> float` — returns `round(revenue/impressions, 4)`; **zero (or negative/None) impressions returns `0.0`** — chosen over `None` because every existing call site already does `else 0`, so behavior is preserved everywhere and no caller needs None-handling. Documented in `docs/METRICS.md` (one-sentence amendment to the RPI section — the glossary is the designated home for this decision per the phase doc).
   - `compute_weighted_average(rows, value_field, weight_field) -> float` — sum(value×weight)/sum(weight), 0.0 on zero total weight — for dwell-time aggregation weighted by impressions.
2. **Repair `get_campaign_insights`:** add `days: int = 30` date-range scoping (mirroring `get_campaign_metrics`' existing parameter idiom); RPI trend compares `compute_rpi(first_half_rev, first_half_imp)` vs `compute_rpi(second_half_rev, second_half_imp)` instead of raw revenue; best/worst-day queries gain `GROUP BY vm.metric_date` with `SUM(revenue)`/`SUM(impressions)` so a "day" is an aggregated day.
3. **Migrate all inventoried call sites** to `compute_rpi()` (mechanical; outputs unchanged except the two known bugs). The weekly view in `generate_metrics_visualization` recomputes weekly values from the underlying daily revenue/impressions via `compute_rpi` for ratio metrics (sums stay sums for additive metrics; weekly dwell uses `compute_weighted_average` weighted by impressions). SQL-level ratios: `get_top_performing_ads`' :307 aggregate stays in SQL (it's ORDER BY logic over ratio-of-sums, already correct) but the returned per-ad rpi values are recomputed in python via `compute_rpi` from the summed columns, so no *returned* number is produced by inline math.
4. **`get_top_performing_ads`:** add **optional** `campaign_id: int | None = None` and `days: int | None = None` filters; default (both omitted) behavior byte-identical to today (global, all-time).
5. **Normalize `get_campaign_metrics`' no-data contract** (the ws02 amendment explicitly hands this to this phase): when no activated-video rows have impressions in the window, return `{"status": "error", "message": "No metrics data available for campaign <id>. Metrics only exist for activated videos — use the Review Agent to activate videos first."}` — the same message/contract ws02 established in the visualization guard, moved to the source; the caller guard simplifies to a status check. Rejected alternative: zeroed summary under `status="success"` — keeps two callers guessing whether zeros mean "no data" or "real zeros," which is the ambiguity that caused the Phase-2 crash.
6. **Mock generators:** only swap their stored rpi figure to `compute_rpi(revenue, impressions)` where they derive it; RNG structure untouched (Phase 5 owns unification).
7. **Amend the phase doc** with provenance: corrected maps_tools line set, and the weekly regression test being *written* here (not re-run).

## Test plan

- **New `tests/unit/test_metrics_shared.py`:** known value pairs; zero-impressions → 0.0; all-equal-daily-values case (sum-of-ratios coincidentally agrees — documented as non-probative); unequal-daily-values case where ratio-of-sums must differ from sum-of-ratios (the regression-catcher); weighted-average with unequal weights vs naive mean.
- **Weekly-RPI regression test (new — the one the phase doc assumed existed):** drive `generate_metrics_visualization` weekly view over fixture rows with unequal daily impressions; assert each weekly RPI equals `compute_rpi(sum revenue, sum impressions)` for that week, not the daily-value sum.
- **Per-call-site parity tests:** for each migrated function, assert returned rpi equals `compute_rpi` applied to the same underlying totals.
- **`get_campaign_insights`:** three separate tests (date-scoping, RPI-trend-uses-RPI, best-day-groups-by-day).
- **`get_top_performing_ads`:** default unchanged (global); filters narrow correctly when supplied.
- **`get_campaign_metrics` no-data contract:** returns status "error" + message for a campaign with no activated metrics; visualization still errors cleanly (existing test `test_no_metrics_campaign_returns_clean_error` updated if its assertion shape changes).
- Full `make test` green.
- **Demo scenario:** `docs/demo-scenarios/fashion.md` Scenario F2 (both scenes — F2.1 chart-with-defaults, F2.2 two-turn visualization) via `verifying-with-demo-scenarios`, since the weekly chart is the user-visible behavior change.

## Out of scope

- Unifying the two `_generate_mock_video_metrics()` into one deterministic generator — Phase 5 (`05-deterministic-demo-data.md`).
- Touching the SQL `AVG(dwell_time_seconds)` sites — they're row-level averages consistent with the glossary's "app-local scalar average" definition; re-weighting them is not this phase's mandate (only python-level cross-row aggregation gets `compute_weighted_average`).
- Any change to what metrics *mean* — `docs/METRICS.md` governs; the only glossary edit is documenting the zero-impressions return.
- README.md, DEMO_GUIDE.md untouched.
- BlueZoo/PoS integration (Phases 11-12); chart redesign (Phase 7).
