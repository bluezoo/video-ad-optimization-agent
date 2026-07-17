# Workstream 02: bug-fixes-and-cleanup

**Branch:** version_2_bug-fixes-and-cleanup
**Phase doc:** .docs/version2-plan/02-bug-fixes-and-cleanup.md

## Research findings

Every phase-doc claim was re-verified against current code (post-Phase-0 merge, base 7d3c866). All hold. Per item:

1. **Invalid default `metric="revenue"`** — confirmed in both `generate_metrics_visualization` (app/tools/metrics_tools.py:720, default at signature) and `generate_map_visualization` (app/tools/maps_tools.py:858). Both validate against `valid_metrics = ["revenue_per_impression", "impressions", "dwell_time", "circulation"]`, which excludes `"revenue"` — so calling either tool with defaults returns an error. Additional confirmation of the phase doc's "important correction": the daily row dicts built in `get_campaign_metrics` (~metrics_tools.py:215-228) contain `date, impressions, dwell_time, circulation, revenue_per_impression` — **no raw `revenue` key** — although raw revenue is computed inside the loop, so exposing it would be one line if ever wanted.
2. **Null-deref before empty guard** — confirmed: `get_campaign_metrics` returns `summary=None` with `status="success"` whenever no rows have impressions (metrics_tools.py ~246: `summary = None; if totals and totals["total_impressions"]: ...`). In `generate_metrics_visualization`, a debug f-string interpolating `summary['total_impressions']` runs **before** the `if not daily_metrics:` guard → live `TypeError: 'NoneType' object is not subscriptable` for any campaign with zero activated-video metrics.
3. **Weekly bar_chart ratio-sum bug** — confirmed: `week_total = sum(d["value"] for d in week_slice)`, which is meaningless for ratio metrics like RPI (sums the ratios instead of recomputing revenue/impressions per week). **Flag only** — the fix belongs to Phase 3 (centralize-rpi-metrics), where per-metric aggregation rules get a single home.
4. **`get_campaign_locations` queries legacy tables** — confirmed: LEFT JOINs `campaign_ads` + `campaign_metrics` (maps_tools.py ~57-72). Current tables are `campaign_videos` (db.py:112) and `video_metrics` (db.py:139). The legacy tables still exist in the schema, so the query runs but reports zero ads/metrics.
5. **`CAMPAIGN_CATEGORIES` drift** — confirmed and sharpened: config.py:89 lists 4 values; the DB CHECK constraint (db.py:70) allows 5 (adds `holiday`). New finding: `CAMPAIGN_CATEGORIES` has **zero consumers** anywhere in app/ or tests/ — it's dead config. `create_campaign` (campaign_tools.py ~66-73) uses its own hardcoded product-category→campaign-category mapping with a silent fallback to `"essentials"`, undocumented.
6. **Stale texts** — confirmed: agent.py:152 and :539 list "Emerald Satin Slip Dress - The Grove" as demo campaign 4; actual is `sage-satin-camisole` at The Grove (mock_data.py:63-64, name auto-generated as "Sage Satin Camisole - The Grove"). agent.py:310 says "90 days of mock performance metrics"; mock data generates 30 (mock_data.py:245, :383). agent.py:200 and video_tools.py:18 say Stage 1 uses "Gemini 2.0 Flash Exp"; actual is `config.IMAGE_GENERATION` (default `gemini-3-pro-image`, env-overridable since Phase 0). The README:66 BigQuery bullet is **already handled** — SETUP_INSTRUCTIONS.md:81 records the correction; no new work.
7. **Integration test exception-catch masking** — confirmed: all 6 tests in tests/integration/test_agents.py share `except ImportError: pytest.skip("google.adk.evaluation not available")` + `except Exception as e: pytest.xfail(...)`. The ImportError arm is what silently masked the missing `google-adk[eval]` extra in workstream 01 (whole suite "passed" as 6 skips).
8. **conftest DB path** — already fixed and merged in workstream 01 (phase doc amended there). No work.
9. **Three pre-existing e2e failures** — reproduce identically on this branch (3 failed, 22 passed, 1 skipped). Root causes now precisely known:
   - `test_video_generation_flow`: `generate_video_from_product` is `async def (campaign_id, product_id, variation: Optional[dict], ...)` — the test passes stale `model_ethnicity=`/`setting=`/`mood=`/`lighting=`/`activity=` kwargs, omits required `product_id`, and never awaits.
   - `test_chart_generation` / `test_map_visualization`: both tools are `async def`, called synchronously → `TypeError: argument of type 'coroutine' is not iterable`. The chart test additionally passes invalid `metric="rpi"` (valid key is `revenue_per_impression`).
   - pytest config already has `asyncio_mode = auto`, so `async def` test functions need no extra markers. All 3 tests carry `@pytest.mark.slow` (video also `veo`), but `make test-e2e` runs **without** deselecting slow, so they fail on every e2e run today.

## Implementation approach

Seven work items (phase items 3 and 8 need no code; item 3 gets a code comment flagging it for Phase 3):

1. **Fix invalid defaults (item 1):** change `metric` default to `"revenue_per_impression"` in both `generate_metrics_visualization` and `generate_map_visualization`, and align their docstrings. **Rejected alternative:** additionally exposing raw daily `revenue` in the row shape + allow-list. It's one line here, but it creates a new public metric key whose weekly aggregation semantics (sum, unlike RPI) would land right before Phase 3 centralizes exactly that logic — deferring keeps Phase 3's surface clean, and RPI is the product's flagship metric anyway.
2. **Fix null-deref (item 2):** move the empty-data guard (`if not daily_metrics:`) above the debug print, and make the print summary-safe. Add a unit test: campaign with zero activated-video metrics → tool returns a clean "no data" response instead of raising.
3. **Flag weekly aggregation (item 3):** comment at the `week_total` line: ratio metrics are summed incorrectly; fix lands in Phase 3 with centralized per-metric aggregation. No behavior change.
4. **Modernize `get_campaign_locations` (item 4):** rewrite the JOIN to `campaign_videos` + `video_metrics` (mirroring the pattern already used by `get_campaign_metrics`), so location results reflect real per-campaign video/metric counts. Unit test asserting non-zero counts for a campaign with activated videos.
5. **Resolve category drift (item 5):** align `CAMPAIGN_CATEGORIES` to the 5 CHECK-constraint values (add `"holiday"`) with a comment naming db.py's CHECK as the source of truth, and document `create_campaign`'s hardcoded mapping + silent `"essentials"` fallback in its docstring. **Rejected alternative:** deleting the dead constant — Phases 7/8 (schema/prompt generalization) are likely consumers; keeping it aligned is cheaper than re-adding it.
6. **Fix stale texts (item 6):** agent.py:152/539 → "Sage Satin Camisole - The Grove"; agent.py:310 → 30 days; agent.py:200 + video_tools.py:18 → describe Stage 1 by role ("Gemini image model, see `config.IMAGE_GENERATION`") rather than a hardcoded model name, so Phase-0-style swaps don't re-stale them. README bullet: no-op (already in SETUP_INSTRUCTIONS.md:81).
7. **Unmask integration import errors (item 7):** replace the per-test `except ImportError: pytest.skip` with a module-level import of `google.adk.evaluation` that fails loudly with an actionable message ("pip install 'google-adk[eval]' — see SETUP_INSTRUCTIONS.md"), keeping the `except Exception: xfail` arm for genuine flaky-LLM/config failures. Missing dependency = error, not skip.
8. **Repair the 3 e2e tests (item 9):** make all three `async def` + `await` (asyncio_mode=auto handles the rest); `test_video_generation_flow` gets the current signature (`product_id=1, variation={...}` replacing the five stale kwargs); `test_chart_generation` gets `metric="revenue_per_impression"`. Verification: run the two non-Veo slow tests to green locally; run the `veo`-marked video test once (~2-3 min, Phase 0 proved the pipeline at ~97s/video) to confirm end-to-end.

Sequencing note: this is a bug-fix batch with no cross-item dependencies; tasks land in the order above (smallest blast radius first, e2e repairs last since they validate against the fixed tools).

## Test plan

- **Unit:** `make test-unit` green throughout (PostToolUse hook enforces per-edit). New tests: empty-metrics guard (item 2), `get_campaign_locations` against current tables (item 4), config/CHECK category parity (item 5).
- **E2E:** `make test-e2e` goes from 3-failed to fully green (the headline deliverable of item 9) — including the slow-marked chart/map tests run explicitly; the `veo` test run once against the real API.
- **Integration:** `make test-integration` still passes with the extra installed (5 passed baseline from workstream 01); a run *without* `google-adk[eval]` now errors loudly instead of 6 silent skips (verified by uninstalling in a throwaway venv or documented as a code-inspection check).
- **Demo scenario:** `docs/demo-scenarios/fashion.md` Scenario F1 via `verifying-with-demo-scenarios` (the `demo-scenario-verifier` subagent, port 8501). Additionally, one analytics-flavored scene exercising `generate_metrics_visualization` with defaults (the item-1/2 fix path: chart renders for an active campaign; clean no-data message for a campaign without activated videos) — extending fashion.md with that scene as part of this workstream.

## Out of scope

- **Weekly ratio aggregation fix** (item 3) — Phase 3 (`04-centralize-rpi-metrics`).
- **Exposing raw daily `revenue` as a chartable metric** — deferred to Phase 3 per the design choice above.
- **The ~170 pre-existing `make lint` errors** across untouched files (noted in workstream 01) — cleanup batch, but not this phase's mandate; only files this workstream touches get lint-cleaned.
- **README.md** — never edited (client-facing; corrections live in SETUP_INSTRUCTIONS.md, and the one relevant correction already exists).
- **Any schema change** — legacy tables `campaign_ads`/`campaign_metrics` stay in the schema; item 4 only repoints the query. Dropping them is a future-phase decision.
- **DEMO_GUIDE.md** — stays untouched (fashion-specific, human-facing).
