# Workstream 02: Bug Fixes and Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven confirmed defects from `.docs/version2-plan/02-bug-fixes-and-cleanup.md` (invalid metric defaults, null-deref crash, legacy-table query, category drift, stale prompt texts, silently-masked integration imports, three broken e2e tests) plus one planning-time discovery (five vacuous async unit tests), taking `make test-e2e` to fully green.

**Architecture:** Pure bug-fix batch — no new modules, no schema changes. Each task touches one defect site plus its test. The weekly ratio-aggregation bug gets a flag comment only (fix belongs to Phase 3's metric centralization).

**Tech Stack:** Python 3.12, pytest (`asyncio_mode = auto` — async test functions need no markers), unittest.mock, SQLite, google-genai SDK (mocked in unit tests).

## Global Constraints

- Branch `version_2_bug-fixes-and-cleanup`, worktree `.claude/worktrees/version_2_bug-fixes-and-cleanup`. Never commit `app/.env`.
- `README.md` and `DEMO_GUIDE.md` are never edited. Corrections to README facts live in `SETUP_INSTRUCTIONS.md` (the one relevant correction already exists at SETUP_INSTRUCTIONS.md:81 — no work).
- No schema changes: legacy tables `campaign_ads`/`campaign_metrics` stay in `app/database/db.py`.
- New chart/map default metric is exactly `"revenue_per_impression"`. Do NOT add a raw `revenue` metric key (deferred to Phase 3 per the approved working doc).
- No `Co-Authored-By: Claude` or AI-attribution trailers in commits.
- A PostToolUse hook runs `make test-unit` after every `app/**/*.py` edit — if it fails, stop and fix before proceeding.
- Only lint-clean files this plan touches; the ~170 pre-existing `make lint` errors elsewhere are out of scope.

## File Map

| File | Tasks | Change |
|---|---|---|
| `app/tools/metrics_tools.py` | 1, 2 | `metric` default; no-data guard; week_total flag comment |
| `app/tools/maps_tools.py` | 1, 3 | `metric` default; `get_campaign_locations` query repoint |
| `app/config.py` | 4 | `CAMPAIGN_CATEGORIES` + `"holiday"` + source-of-truth comment |
| `app/tools/campaign_tools.py` | 4 | `create_campaign` docstring documents mapping + fallback |
| `app/agent.py` | 5 | 4 stale prompt texts |
| `app/tools/video_tools.py` | 5 | module docstring model names |
| `tests/unit/test_metrics_tools.py` | 1, 2, 7 | new default/guard tests; de-vacuate 2 async tests |
| `tests/unit/test_maps_tools.py` | 1, 3, 7 | new default/locations tests; de-vacuate 3 async tests |
| `tests/unit/test_config.py` | 4 | category/CHECK parity test |
| `tests/integration/test_agents.py` | 6 | loud module-level import; remove 6 ImportError-skip arms |
| `tests/e2e/test_demo_workflows.py` | 8 | repair 3 async tests |
| `docs/demo-scenarios/fashion.md` | 9 | new analytics scene F2 |

---

### Task 1: Fix invalid `metric` defaults in chart and map tools

**Files:**
- Modify: `app/tools/metrics_tools.py:723` (signature default)
- Modify: `app/tools/maps_tools.py:860` (signature default)
- Test: `tests/unit/test_metrics_tools.py`, `tests/unit/test_maps_tools.py`

**Interfaces:**
- Produces: `generate_metrics_visualization(campaign_id, chart_type="trendline", metric="revenue_per_impression", days=30, tool_context=None)` and `generate_map_visualization(visualization_type="performance_map", metric="revenue_per_impression", style="infographic", tool_context=None)`. Tasks 7 and 8 rely on these defaults being valid.

- [ ] **Step 1: Write the failing tests**

Append to the `TestGenerateMetricsVisualization` class in `tests/unit/test_metrics_tools.py` (note `async def` — pytest is `asyncio_mode = auto`):

```python
    async def test_default_metric_is_valid(self, test_db, mock_storage_module):
        """Calling with default metric must not trip the valid_metrics check.

        Regression: default was "revenue", which the tool itself rejects.
        The mocked client raises so the test never makes a real API call —
        reaching the mocked-API error proves validation passed.
        """
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.metrics_tools import generate_metrics_visualization

            result = await generate_metrics_visualization(campaign_id=1)

            assert "Invalid metric" not in result.get("message", "")
```

Append to the `TestGenerateMapVisualization` class in `tests/unit/test_maps_tools.py`:

```python
    async def test_default_metric_is_valid(self, test_db, mock_storage_module):
        """Calling with default metric must not trip the valid_metrics check.

        Regression: default was "revenue", which the tool itself rejects.
        """
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization()

            assert "Invalid metric" not in result.get("message", "")
```

(`patch` and `MagicMock` are already imported at the top of both test files.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_metrics_tools.py::TestGenerateMetricsVisualization::test_default_metric_is_valid tests/unit/test_maps_tools.py::TestGenerateMapVisualization::test_default_metric_is_valid -v`

Expected: both FAIL — `result["message"]` is `"Invalid metric. Must be one of: revenue_per_impression, impressions, dwell_time, circulation"`.

(If the maps test class is named differently, `grep -n "class Test.*MapVisualization" tests/unit/test_maps_tools.py` and use the actual name.)

- [ ] **Step 3: Fix both defaults**

In `app/tools/metrics_tools.py` (~line 723) change:

```python
    metric: str = "revenue",
```

to:

```python
    metric: str = "revenue_per_impression",
```

In `app/tools/maps_tools.py` (~line 860) change:

```python
    metric: str = "revenue",
```

to:

```python
    metric: str = "revenue_per_impression",
```

Both docstrings already list the correct valid values — no docstring change needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_metrics_tools.py tests/unit/test_maps_tools.py -v`

Expected: the two new tests PASS; no existing test regresses. (The metrics one may still fail here if campaign 1's summary path hits the Task 2 bug — if it fails with `TypeError: 'NoneType' object is not subscriptable`, that's the Task 2 defect, not this one; campaign 1 has activated-video metrics in demo data so it should not. Investigate before proceeding if it does.)

- [ ] **Step 5: Commit**

```bash
git add app/tools/metrics_tools.py app/tools/maps_tools.py tests/unit/test_metrics_tools.py tests/unit/test_maps_tools.py
git commit -m "Fix invalid default metric in chart and map visualization tools"
```

---

### Task 2: Guard the no-data path before the summary deref; flag the weekly ratio bug

**Files:**
- Modify: `app/tools/metrics_tools.py:772-793` (reorder guard above debug print) and `:914` (flag comment)
- Test: `tests/unit/test_metrics_tools.py`

**Interfaces:**
- Consumes: `create_campaign(product_id, store_name, city, state)` from `app/tools/campaign_tools.py` (sync, returns `{"status": "success", "campaign": {"id": ...}}`).
- Produces: `generate_metrics_visualization` returns `{"status": "error", "message": "No metrics data available for campaign <id>. Metrics only exist for activated videos — use the Review Agent to activate videos first."}` for campaigns with no activated-video metrics, instead of raising `TypeError`.

- [ ] **Step 1: Write the failing test**

Append to `TestGenerateMetricsVisualization` in `tests/unit/test_metrics_tools.py`:

```python
    async def test_no_metrics_campaign_returns_clean_error(self, test_db):
        """A campaign with zero activated-video metrics must get a clean
        error response, not TypeError.

        Regression: get_campaign_metrics returns summary=None with
        status="success" when no rows have impressions; a debug print
        dereferenced summary['total_impressions'] before the empty guard.
        """
        from app.tools.campaign_tools import create_campaign
        from app.tools.metrics_tools import generate_metrics_visualization

        created = create_campaign(
            product_id=1,
            store_name="No Metrics Test Store",
            city="Austin",
            state="TX",
        )
        assert created["status"] == "success"
        campaign_id = created["campaign"]["id"]

        result = await generate_metrics_visualization(campaign_id=campaign_id)

        assert result["status"] == "error"
        assert "No metrics data available" in result["message"]
```

(If `create_campaign`'s success payload nests the id differently, check with `grep -n "return {" -A 8 app/tools/campaign_tools.py` and adjust the extraction — the assertion contract stays the same.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_metrics_tools.py::TestGenerateMetricsVisualization::test_no_metrics_campaign_returns_clean_error -v`

Expected: FAIL with `TypeError: 'NoneType' object is not subscriptable` (from the `summary['total_impressions']` debug print).

- [ ] **Step 3: Reorder the guard**

In `app/tools/metrics_tools.py`, the current sequence after fetching (~lines 768-793) is:

```python
    campaign_name = metrics_result["campaign"]["name"]
    summary = metrics_result["summary"]
    daily_metrics = metrics_result["daily_metrics"]

    print(f"[DEBUG VIZ] Step 2: Data received from DB:")
    print(f"[DEBUG VIZ]   - Campaign: {campaign_name}")
    print(f"[DEBUG VIZ]   - Total daily records: {len(daily_metrics)}")
    print(f"[DEBUG VIZ]   - Summary totals: impressions={summary['total_impressions']:,}, revenue=${summary['total_revenue']:,.2f}")
```

…followed by the sample-data prints, and only then `if not daily_metrics:`. Replace from `campaign_name = ...` through the end of the `if not daily_metrics:` block with:

```python
    campaign_name = metrics_result["campaign"]["name"]
    summary = metrics_result["summary"]
    daily_metrics = metrics_result["daily_metrics"]

    # Guard BEFORE any summary deref: get_campaign_metrics returns
    # summary=None (status still "success") when no activated-video rows
    # have impressions in the window.
    if not daily_metrics or not summary:
        return {
            "status": "error",
            "message": (
                f"No metrics data available for campaign {campaign_id}. "
                "Metrics only exist for activated videos — use the Review "
                "Agent to activate videos first."
            )
        }

    print(f"[DEBUG VIZ] Step 2: Data received from DB:")
    print(f"[DEBUG VIZ]   - Campaign: {campaign_name}")
    print(f"[DEBUG VIZ]   - Total daily records: {len(daily_metrics)}")
    print(f"[DEBUG VIZ]   - Summary totals: impressions={summary['total_impressions']:,}, revenue=${summary['total_revenue']:,.2f}")

    # Show first 3 and last 3 daily records as sample
    print(f"[DEBUG VIZ]   - Sample daily data (first 3 records):")
    for i, day in enumerate(daily_metrics[:3]):
        print(f"[DEBUG VIZ]     [{i}] date={day['date']}, {metric}={day.get(metric, 'N/A')}")
    if len(daily_metrics) > 6:
        print(f"[DEBUG VIZ]     ... ({len(daily_metrics) - 6} more records) ...")
    if len(daily_metrics) > 3:
        print(f"[DEBUG VIZ]   - Sample daily data (last 3 records):")
        for i, day in enumerate(daily_metrics[-3:]):
            print(f"[DEBUG VIZ]     [{len(daily_metrics)-3+i}] date={day['date']}, {metric}={day.get(metric, 'N/A')}")
```

(The old `if daily_metrics:` wrapper around the sample prints becomes unnecessary — the guard above already returned. The old standalone `if not daily_metrics:` error block is subsumed; delete it.)

- [ ] **Step 4: Add the Phase 3 flag comment**

At `app/tools/metrics_tools.py:914` (`week_total = sum(...)` inside the bar_chart branch), add the comment above the line — no behavior change:

```python
                # KNOWN BUG (flagged, fix in Phase 3 / 04-centralize-rpi-metrics):
                # summing per-day values is wrong for ratio metrics like
                # revenue_per_impression — a weekly RPI must be recomputed as
                # sum(revenue)/sum(impressions), not sum(daily ratios).
                # Phase 3 centralizes per-metric aggregation rules.
                week_total = sum(d["value"] for d in week_slice)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_metrics_tools.py -v`

Expected: all PASS, including `test_no_metrics_campaign_returns_clean_error`.

- [ ] **Step 6: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Guard no-data path before summary deref; flag weekly ratio-sum bug for Phase 3"
```

---

### Task 3: Repoint `get_campaign_locations` to current tables

**Files:**
- Modify: `app/tools/maps_tools.py:57-72` (query) and `:98-101` (metrics keys unchanged, values now real)
- Test: `tests/unit/test_maps_tools.py`

**Interfaces:**
- Produces: `get_campaign_locations()` unchanged shape (`{"status", "locations": [{"campaign_id", "name", "category", "status", "location", "metrics": {"ad_count", "total_revenue", "total_impressions"}}]}`) but `metrics` now computed from `campaign_videos` + `video_metrics`; `ad_count` = count of **activated** videos (consistent with `get_campaign_metrics`' activated-only rule).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_maps_tools.py` (top-level class):

```python
class TestGetCampaignLocationsCurrentSchema:
    """get_campaign_locations must read campaign_videos/video_metrics,
    not the legacy campaign_ads/campaign_metrics tables (which are empty)."""

    def test_locations_report_real_video_metrics(self, test_db):
        with patch("app.tools.maps_tools.GOOGLE_MAPS_API_KEY", "test-key"), \
             patch("googlemaps.Client") as mock_gmaps:
            mock_gmaps.return_value.geocode.return_value = [
                {"geometry": {"location": {"lat": 34.05, "lng": -118.24}}}
            ]
            from app.tools.maps_tools import get_campaign_locations

            result = get_campaign_locations()

            assert "locations" in result
            # Demo data has activated videos with 30 days of metrics on the
            # pre-loaded campaigns — the legacy tables are empty, so any
            # non-zero count proves the query reads the current schema.
            campaigns_with_ads = [
                loc for loc in result["locations"]
                if loc["metrics"]["ad_count"] > 0
            ]
            assert len(campaigns_with_ads) >= 1
            assert any(
                loc["metrics"]["total_impressions"] > 0
                for loc in campaigns_with_ads
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_maps_tools.py::TestGetCampaignLocationsCurrentSchema -v`

Expected: FAIL on `assert len(campaigns_with_ads) >= 1` — the legacy `campaign_ads` table is empty, so every `ad_count` is 0.

- [ ] **Step 3: Rewrite the query**

In `app/tools/maps_tools.py` (~lines 57-72), replace:

```python
        cursor.execute('''
            SELECT
                c.id,
                c.name,
                c.category,
                c.city,
                c.state,
                c.status,
                COUNT(DISTINCT ca.id) as ad_count,
                SUM(cm.revenue) as total_revenue,
                SUM(cm.impressions) as total_impressions
            FROM campaigns c
            LEFT JOIN campaign_ads ca ON c.id = ca.campaign_id
            LEFT JOIN campaign_metrics cm ON c.id = cm.campaign_id
            GROUP BY c.id
        ''')
```

with (same JOIN pattern `generate_map_visualization` already uses at maps_tools.py:915-934):

```python
        # Current schema: campaign_videos + video_metrics (HITL workflow).
        # ad_count = activated videos; metrics only exist for activated videos.
        cursor.execute('''
            SELECT
                c.id,
                c.name,
                c.category,
                c.city,
                c.state,
                c.status,
                COUNT(DISTINCT CASE WHEN cv.status = 'activated' THEN cv.id END) as ad_count,
                SUM(vm.revenue) as total_revenue,
                SUM(vm.impressions) as total_impressions
            FROM campaigns c
            LEFT JOIN campaign_videos cv ON c.id = cv.campaign_id
            LEFT JOIN video_metrics vm ON cv.id = vm.video_id AND cv.status = 'activated'
            GROUP BY c.id
        ''')
```

The result-building loop below (`campaign["ad_count"]`, `campaign["total_revenue"]`, `campaign["total_impressions"]`) reads the same aliases — no further change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_maps_tools.py tests/unit/test_campaign_tools.py -v`

Expected: new test PASSES; the two pre-existing `TestGetCampaignLocations` tests in test_campaign_tools.py still pass/skip as before.

- [ ] **Step 5: Commit**

```bash
git add app/tools/maps_tools.py tests/unit/test_maps_tools.py
git commit -m "Repoint get_campaign_locations to campaign_videos/video_metrics"
```

---

### Task 4: Align CAMPAIGN_CATEGORIES with the DB CHECK; document create_campaign's fallback

**Files:**
- Modify: `app/config.py:88-89`
- Modify: `app/tools/campaign_tools.py` (`create_campaign` docstring, ~line 38)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `config.CAMPAIGN_CATEGORIES == ["summer", "formal", "professional", "essentials", "holiday"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_config.py` (module level, alongside the existing config tests; it uses the `test_db` fixture from `tests/conftest.py`):

```python
class TestCampaignCategoriesParity:
    """config.CAMPAIGN_CATEGORIES must stay in sync with the CHECK
    constraint on campaigns.category (app/database/db.py — source of truth)."""

    def test_all_config_categories_accepted_by_db(self, test_db):
        from app import config
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            for cat in config.CAMPAIGN_CATEGORIES:
                # Raises sqlite3.IntegrityError if cat violates the CHECK
                cursor.execute(
                    "INSERT INTO campaigns (name, city, state, category) "
                    "VALUES (?, ?, ?, ?)",
                    (f"parity-{cat}", "Los Angeles", "CA", cat),
                )

    def test_holiday_category_present(self):
        from app import config

        assert "holiday" in config.CAMPAIGN_CATEGORIES
```

- [ ] **Step 2: Run tests to verify the state**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py::TestCampaignCategoriesParity -v`

Expected: `test_holiday_category_present` FAILS (config lists only 4 values). `test_all_config_categories_accepted_by_db` PASSES (the 4 are a subset of the CHECK's 5) — it exists to catch the reverse drift (a config value the DB rejects) permanently.

- [ ] **Step 3: Fix config**

In `app/config.py` (~lines 88-89), replace:

```python
# Campaign categories
CAMPAIGN_CATEGORIES = ["summer", "formal", "professional", "essentials"]
```

with:

```python
# Campaign categories — mirrors the CHECK constraint on campaigns.category
# in app/database/db.py (the source of truth). Keep the two in sync.
CAMPAIGN_CATEGORIES = ["summer", "formal", "professional", "essentials", "holiday"]
```

- [ ] **Step 4: Document create_campaign's mapping and fallback**

In `app/tools/campaign_tools.py`, in the `create_campaign` docstring, after the line `The campaign name is auto-generated from product and store if not provided.` add:

```python
    The campaign category is derived from the product's category via a
    hardcoded mapping (dress→summer, top→essentials, pants→professional,
    skirt→formal, outerwear→essentials); any unmapped product category
    silently falls back to "essentials". Valid categories are enforced by
    the CHECK constraint on campaigns.category (app/database/db.py) and
    mirrored in config.CAMPAIGN_CATEGORIES.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_campaign_tools.py -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/tools/campaign_tools.py tests/unit/test_config.py
git commit -m "Align CAMPAIGN_CATEGORIES with DB CHECK; document create_campaign category fallback"
```

---

### Task 5: Fix stale prompt/docstring texts

**Files:**
- Modify: `app/agent.py:152, 200, 205, 310, 539`
- Modify: `app/tools/video_tools.py:16-25` (module docstring)

**Interfaces:** none (prompt text only — no code paths change).

- [ ] **Step 1: Make the five agent.py edits**

Line 152: `4. **Emerald Satin Slip Dress - The Grove** (Los Angeles, CA)` → `4. **Sage Satin Camisole - The Grove** (Los Angeles, CA)`

Line 200: `**Stage 1: Scene Image** (Gemini 2.0 Flash Exp)` → `**Stage 1: Scene Image** (Gemini image model — see IMAGE_GENERATION in app/config.py)`

Line 205: `**Stage 2: Video Animation** (Veo 3.1)` → `**Stage 2: Video Animation** (video model — see VIDEO_GEN_MODEL in app/config.py)`

Line 310: `Each active campaign has 90 days of mock performance metrics.` → `Each active campaign has 30 days of mock performance metrics.`

Line 539: `- Emerald Satin Slip Dress - The Grove (LA)` → `- Sage Satin Camisole - The Grove (LA)`

(Line numbers may shift a few lines — locate by the quoted text, not the number.)

- [ ] **Step 2: Fix the video_tools.py module docstring**

In `app/tools/video_tools.py` (~lines 16-25), change:

```python
    Stage 1: Scene Image (Gemini 2.0 Flash Exp)
```
to:
```python
    Stage 1: Scene Image (image model from config.IMAGE_GENERATION)
```
and:
```python
    Stage 2: Video Animation (Veo 3.1)
```
to:
```python
    Stage 2: Video Animation (video model from config.VIDEO_GEN_MODEL)
```

- [ ] **Step 3: Verify no stale strings remain**

Run: `grep -rn "Emerald Satin\|90 days\|Gemini 2.0 Flash Exp" app/ && echo "STALE TEXT REMAINS" || echo "clean"`

Expected: `clean`. Then: `.venv/bin/python -m pytest tests/unit -q` — all PASS (prompt text is not asserted by unit tests, this is a regression backstop).

- [ ] **Step 4: Commit**

```bash
git add app/agent.py app/tools/video_tools.py
git commit -m "Fix stale prompt texts: campaign 4 name, metrics window, model references"
```

---

### Task 6: Make missing google-adk[eval] fail loudly in integration tests

**Files:**
- Modify: `tests/integration/test_agents.py` (module head + all 6 tests)

**Interfaces:**
- Produces: importing `tests.integration.test_agents` without the `google-adk[eval]` extra raises `ImportError` naming the fix; the 6 tests use the module-level `AgentEvaluator` and keep only the `except Exception: xfail` arm.

- [ ] **Step 1: Add the loud module-level import**

In `tests/integration/test_agents.py`, after the existing `import pytest` (~line 26), add:

```python
try:
    from google.adk.evaluation import AgentEvaluator
except ImportError as e:
    # Fail loudly. A broad per-test `except ImportError: pytest.skip` used to
    # swallow this, silently reporting the whole suite as 6 skips when the
    # eval extra was missing (discovered in workstream 01).
    raise ImportError(
        "google.adk.evaluation is unavailable. Install the eval extra: "
        "pip install 'google-adk[eval]' — see SETUP_INSTRUCTIONS.md (Tests)."
    ) from e
```

- [ ] **Step 2: Update all 6 tests**

In each of the 6 test bodies, the current pattern is:

```python
        try:
            from google.adk.evaluation import AgentEvaluator

            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("<file>.test.json"),
                num_runs=1,
            )
        except ImportError:
            pytest.skip("google.adk.evaluation not available")
        except Exception as e:
            pytest.xfail(f"Integration test failed (may need config): {e}")
```

Change each to (drop the local import and the ImportError arm; keep everything else, including each test's own eval-set filename and comments):

```python
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("<file>.test.json"),
                num_runs=1,
            )
        except Exception as e:
            pytest.xfail(f"Integration test failed (may need config): {e}")
```

- [ ] **Step 3: Verify the loud-failure path**

Run (blocks the module to simulate the missing extra):

```bash
.venv/bin/python - <<'EOF'
import sys
from importlib.abc import MetaPathFinder

class Blocker(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "google.adk.evaluation":
            raise ImportError("blocked: simulating missing google-adk[eval]")

sys.meta_path.insert(0, Blocker())
try:
    import tests.integration.test_agents  # noqa: F401
except ImportError as e:
    assert "google-adk[eval]" in str(e), f"message not actionable: {e}"
    print("OK: fails loudly with actionable message")
else:
    raise SystemExit("FAIL: import unexpectedly succeeded")
EOF
```

Expected: `OK: fails loudly with actionable message`.

- [ ] **Step 4: Verify the happy path still works**

Run: `.venv/bin/python -m pytest tests/integration -v -m "not slow" 2>&1 | tail -5`

Expected: same result as the workstream-01 baseline (5 passed / xfails allowed; NOT "6 skipped"). Integration tests hit the real LLM — a transient xfail is acceptable; 6 silent skips are not.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_agents.py
git commit -m "Fail loudly when google-adk[eval] is missing instead of silently skipping"
```

---

### Task 7: De-vacuate the 5 async unit tests (planning-time discovery)

**Files:**
- Modify: `tests/unit/test_metrics_tools.py` (`TestGenerateMetricsVisualization`: 2 tests)
- Modify: `tests/unit/test_maps_tools.py` (map-visualization class: 3 tests)

**Interfaces:**
- Consumes: Task 1's valid defaults; the tools' `try/except Exception → {"status": "error", "message": "Failed to generate ...: <e>"}` wrapper around the `genai.Client()` call (metrics_tools.py:975-1058, maps_tools.py:~1355).

Background: these 5 tests call `async def` tools without `await`, so they assert on a coroutine object — always truthy, never executing the tool (`RuntimeWarning: coroutine ... was never awaited` in every unit run). Repair pattern: `async def` + `await`, with the mocked client's `generate_content` raising, so the tool deterministically returns its error dict without any real API call.

- [ ] **Step 1: Rewrite the 2 metrics tests**

In `tests/unit/test_metrics_tools.py`, replace `test_generate_metrics_visualization_trendline` and `test_generate_metrics_visualization_types` with:

```python
    async def test_generate_metrics_visualization_trendline(
        self, test_db, mock_storage_module
    ):
        """Tool runs the full pre-API pipeline and returns the graceful
        error dict when the (mocked) image API fails."""
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.metrics_tools import generate_metrics_visualization

            result = await generate_metrics_visualization(
                campaign_id=1,
                chart_type="trendline",
                metric="revenue_per_impression",
            )

            assert result["status"] == "error"
            assert "mocked API failure" in result["message"]

    async def test_generate_metrics_visualization_types(
        self, test_db, mock_storage_module
    ):
        """All four chart types pass validation and reach the API stage."""
        chart_types = ["trendline", "bar_chart", "comparison", "infographic"]

        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.metrics_tools import generate_metrics_visualization

            for chart_type in chart_types:
                result = await generate_metrics_visualization(
                    campaign_id=1,
                    chart_type=chart_type,
                    metric="impressions",
                )
                assert "Invalid chart_type" not in result.get("message", ""), chart_type
                assert result["status"] == "error"
                assert "mocked API failure" in result["message"], chart_type
```

- [ ] **Step 2: Rewrite the 3 maps tests**

In `tests/unit/test_maps_tools.py`, replace `test_generate_map_visualization_performance_map`, `test_generate_map_visualization_regional_comparison`, and `test_generate_map_visualization_styles` with the same pattern (keep the class and any other tests as-is):

```python
    async def test_generate_map_visualization_performance_map(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization(
                visualization_type="performance_map"
            )

            assert result["status"] == "error"
            assert "mocked API failure" in result["message"]

    async def test_generate_map_visualization_regional_comparison(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization(
                visualization_type="regional_comparison"
            )

            assert result["status"] == "error"
            assert "mocked API failure" in result["message"]

    async def test_generate_map_visualization_styles(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            for style in ["infographic", "artistic", "simple"]:
                result = await generate_map_visualization(style=style)
                assert "Invalid style" not in result.get("message", ""), style
                assert result["status"] == "error"
                assert "mocked API failure" in result["message"], style
```

(Adapt surgically to the current file — e.g. if the originals wrapped `mock_instance = MagicMock()` boilerplate, it's replaced by the `side_effect` line. If any of these tests carried `@pytest.mark.slow`, drop the marker: with the raising mock they're fast and deterministic.)

- [ ] **Step 3: Run to verify green with no coroutine warnings**

Run: `.venv/bin/python -m pytest tests/unit/test_metrics_tools.py tests/unit/test_maps_tools.py -v -W error::RuntimeWarning`

Expected: all PASS; zero `coroutine ... was never awaited` warnings (the `-W error` flag turns any stray one into a failure).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_metrics_tools.py tests/unit/test_maps_tools.py
git commit -m "De-vacuate async visualization unit tests: await tools, assert real error paths"
```

---

### Task 8: Repair the 3 broken e2e tests

**Files:**
- Modify: `tests/e2e/test_demo_workflows.py:151-181` (video), `:297-311` (chart), `:361-369` (map)

**Interfaces:**
- Consumes: `async generate_video_from_product(campaign_id: int, product_id: int, variation: Optional[dict] = None, use_two_stage: bool = True, duration_seconds: int = 8, tool_context=None)`; `async generate_metrics_visualization(...)` and `async generate_map_visualization(...)` per Task 1. All three return `{"status": "success"|"error", "message": ..., ...}` — success carries `"visualization"` (chart/map) or `"video"` (video gen); there is no `chart_url`/`map_url`/`"error"` key (the old asserts checked keys that no return path produces).

- [ ] **Step 1: Repair `test_video_generation_flow`**

Replace the body (keep the `@pytest.mark.slow` / `@pytest.mark.veo` markers and the docstring):

```python
    @pytest.mark.slow
    @pytest.mark.veo
    async def test_video_generation_flow(self, shared_test_db, mock_storage_module):
        """Scene 2.2: Generate a video (requires Veo API).

        This test validates the full video generation flow:
        1. Get a campaign
        2. Generate video with variation parameters
        3. Verify video is created with 'generated' status
        """
        from app.tools.campaign_tools import get_campaign
        from app.tools.video_tools import generate_video_from_product

        # Get campaign details
        campaign = get_campaign(campaign_id=1)
        assert campaign is not None

        # Generate video (this is slow - 2-3 minutes)
        result = await generate_video_from_product(
            campaign_id=1,
            product_id=1,
            variation={
                "name": "european-studio-elegant",
                "model_ethnicity": "european",
                "setting": "studio",
                "mood": "elegant",
                "lighting": "soft",
                "activity": "posing",
            },
        )

        # Verify result
        assert result["status"] in ("success", "error"), result
        if result["status"] == "success":
            video = result["video"]
            assert video["status"] == "generated"
```

(Check the `variation` dict keys against `CreativeVariation` in `app/models/variation.py` — `name`, `model_ethnicity`, `setting`, `mood`, `lighting`, `activity` are all fields there; if `generate_video_from_product` validates the dict through the model and rejects an extra/missing key, align to the model, not the other way.)

- [ ] **Step 2: Repair `test_chart_generation`**

```python
    @pytest.mark.slow
    async def test_chart_generation(self, shared_test_db):
        """Scene 4.2: Generate metrics visualization."""
        from app.tools.metrics_tools import generate_metrics_visualization

        result = await generate_metrics_visualization(
            campaign_id=1,
            chart_type="trendline",
            metric="revenue_per_impression",
            days=30,
        )

        # Real image-generation call: success carries the visualization
        # payload; a clean error dict is also acceptable in e2e.
        assert result["status"] in ("success", "error"), result
        if result["status"] == "success":
            assert "visualization" in result
```

(The old `metric="rpi"` was never a valid key; the old `"chart_url" in result or "error" in result` asserted keys no return path produces.)

- [ ] **Step 3: Repair `test_map_visualization`**

```python
    @pytest.mark.slow
    async def test_map_visualization(self, shared_test_db):
        """Scene 5.2: Generate map visualization."""
        from app.tools.maps_tools import generate_map_visualization

        result = await generate_map_visualization(style="infographic")

        assert result["status"] in ("success", "error"), result
        if result["status"] == "success":
            assert "visualization" in result
```

- [ ] **Step 4: Run the fast e2e suite**

Run: `.venv/bin/python -m pytest tests/e2e -q -m "not slow"`

Expected: all PASS, 0 failed (the 3 repaired tests are deselected here; this proves no collateral damage).

- [ ] **Step 5: Run the two non-Veo slow tests for real**

Run: `.venv/bin/python -m pytest "tests/e2e/test_demo_workflows.py::TestAnalyticsWorkflow::test_chart_generation" "tests/e2e/test_demo_workflows.py::TestGeographicIntelligenceWorkflow::test_map_visualization" -v`

Expected: 2 PASS (each makes one real Gemini image call; allow ~1-2 min).

- [ ] **Step 6: Run the Veo test once for real**

Run: `.venv/bin/python -m pytest "tests/e2e/test_demo_workflows.py::TestCreativeGenerationWorkflow::test_video_generation_flow" -v`

Expected: PASS in ~2-4 min (Phase 0's smoke run generated a video in ~97s). If it fails on quota/transient API errors, retry once; a genuine signature/contract failure is a bug to fix, not to skip.

- [ ] **Step 7: Full e2e sweep — the phase's headline deliverable**

Run: `.venv/bin/python -m pytest tests/e2e -q`

Expected: **0 failed** (was: 3 failed, 22 passed, 1 skipped). The 1 skip (Maps API key-dependent) may remain.

- [ ] **Step 8: Commit**

```bash
git add tests/e2e/test_demo_workflows.py
git commit -m "Repair 3 e2e tests: await async tools, current signatures, real return-shape asserts"
```

---

### Task 9: Extend the fashion demo scenario and verify

**Files:**
- Modify: `docs/demo-scenarios/fashion.md` (add Scenario F2)

**Interfaces:**
- Consumes: everything above, merged into the branch.

- [ ] **Step 1: Add Scenario F2 to `docs/demo-scenarios/fashion.md`**

Append (matching the existing F1 Act/Scene format with explicit expected-tool-call assertions):

```markdown
## Scenario F2: Analytics chart with defaults (workstream 02 regression)

Covers the Phase 1 fixes: valid default metric and the no-data guard.

### Scene F2.1 — Chart with default metric

**Query:** "Show me a performance chart for the Blue Floral Maxi Dress campaign"

**Expected tool calls:**
- `generate_metrics_visualization` with `campaign_id` resolved to the Blue
  Floral Maxi Dress campaign; `metric` argument either omitted (default
  `revenue_per_impression`) or an explicit valid value — the response must
  NOT contain "Invalid metric".

**Pass criteria:**
- Tool response has `status: "success"` and a chart artifact is rendered
  in the UI (screenshot as evidence).

### Scene F2.2 — Campaign with no activated-video metrics

**Query:** "Create a campaign for product 1 at Test Mall in Austin, Texas,
then show me its performance chart"

**Expected tool calls:**
- `create_campaign(product_id=1, store_name="Test Mall", city="Austin", state="Texas"|"TX")`
- `generate_metrics_visualization` for the new campaign's id.

**Pass criteria:**
- No crash/traceback in the tool response; the visualization tool returns
  the clean error ("No metrics data available … activate videos first")
  and the agent relays that guidance (e.g. pointing at review/activation).
```

- [ ] **Step 2: Commit**

```bash
git add docs/demo-scenarios/fashion.md
git commit -m "Add analytics demo scenario F2 covering workstream 02 fixes"
```

- [ ] **Step 3: Full local suites**

Run: `make test-unit && .venv/bin/python -m pytest tests/e2e -q && make lint 2>&1 | tail -3`

Expected: unit green, e2e 0 failed, and `make lint` reports no NEW errors in the files this plan touched (pre-existing errors elsewhere are out of scope — compare against `git stash`-free baseline if unsure).

- [ ] **Step 4: Demo-scenario verification (lifecycle step 5)**

Per `verifying-with-demo-scenarios`: set STATUS.md to `verify in progress` (main checkout), then dispatch the `demo-scenario-verifier` subagent against this worktree's `make dev` (port 8501, kill stale servers first) for **Scenario F1 and Scenario F2 sequentially**. Record pass/fail + evidence paths in `WORK_LOG.md`. A failing scene blocks the PR.

---

## Post-plan lifecycle (not plan tasks)

`requesting-code-review` on the whole branch → fix findings → `finishing-a-development-branch`: PR into `version_2` (body links `.docs/version2-plan/02-bug-fixes-and-cleanup.md`, lists test evidence + scenario results, no AI-attribution trailer), owner-confirmed self-merge, worktree cleanup via ExitWorktree, STATUS.md → `merged`, WORK_LOG checkpoint 6.
