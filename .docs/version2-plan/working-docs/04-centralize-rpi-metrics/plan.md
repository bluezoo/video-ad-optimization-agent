# Workstream 04: Centralize RPI/Metric Computation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One shared module (`app/tools/metrics_shared.py`) becomes the only place RPI and weighted-average math lives; every inline computation migrates to it, fixing the weekly-chart ratio-sum bug and `get_campaign_insights`' three defects along the way.

**Architecture:** Two pure-arithmetic functions (`compute_rpi`, `compute_weighted_average`) with no DB/scoping logic; call sites keep their own queries and pass summed totals. Contract change: `get_campaign_metrics` returns a status-error on no-data instead of `summary=None` under `status="success"`. Tasks are ordered so the shared module lands first and the visualization fix (which depends on Task 2's enriched daily rows) lands last.

**Tech Stack:** Python 3.12, sqlite3, pytest (fixtures `test_db`/`mock_storage_module` from `tests/conftest.py`), Google ADK tool conventions.

## Global Constraints

- `compute_rpi` returns `round(revenue/impressions, 4)`; zero/negative/None impressions → `0.0` (exact parity with every existing call site's `else 0`).
- RPI over any window = ratio of sums, never sum/average of per-period ratios (docs/METRICS.md rule).
- Optional-parameter idiom is `param: int = None` (repo/ADK convention, e.g. `maps_tools.generate_static_map(locations: list = None, ...)`) — NOT `int | None`.
- `get_top_performing_ads` default (no-filter) behavior stays identical: global, all-time.
- Mock generators (`mock_data.py`, `review_tools.py:_generate_mock_video_metrics`) are NOT touched — verified: neither contains any division; Phase 5 owns them.
- SQL `AVG(dwell_time_seconds)` sites untouched. Only two python-level cross-row aggregations change: visualization weekly dwell, maps regional dwell.
- One SQL ratio survives by design: `metrics_tools.py` `metric_column_map`'s `SUM(vm.revenue) / NULLIF(SUM(vm.impressions), 0)` — used for ORDER BY only; returned values come from `compute_rpi()` (Task 3 adds a comment saying so).
- Imports are relative: `from .metrics_shared import compute_rpi` inside `app/tools/`.
- README.md and DEMO_GUIDE.md untouched. No `Co-Authored-By` / AI-attribution trailers.
- A PostToolUse hook runs `make test-unit` after every edit to `app/**/*.py` — expected, not an error.
- Line numbers below are exact at branch base 925bdbd (commit `11c3b04` on this branch); earlier tasks shift later files' numbers only within the same file — re-locate by the quoted code, not blindly by number.

## File Map

| File | Tasks | Change |
|---|---|---|
| `app/tools/metrics_shared.py` | 1 | Create — the shared module |
| `tests/unit/test_metrics_shared.py` | 1 | Create — direct unit tests |
| `docs/METRICS.md` | 1 | Add zero-impressions convention paragraph |
| `app/tools/metrics_tools.py` | 2, 3, 4, 7 | Migrate 5 sites; no-data contract; filters; insights repair; weekly fix |
| `tests/unit/test_metrics_tools.py` | 2, 3, 4, 7 | Fixture helper + contract/parity/repair/regression tests |
| `app/tools/campaign_tools.py` | 5 | Migrate `get_campaign` |
| `app/tools/review_tools.py` | 5 | Migrate `get_video_details` |
| `tests/unit/test_campaign_tools.py`, `tests/unit/test_review_tools.py` | 5 | Parity tests |
| `.docs/version2-plan/04-centralize-rpi-metrics.md` | 5 | Provenance amendment (Step 5 vacuous) |
| `app/tools/maps_tools.py` | 6 | Migrate 4 sites + weighted regional dwell |
| `tests/unit/test_maps_tools.py` | 6 | Parity tests |

---

### Task 1: Shared module `metrics_shared.py` + unit tests + glossary note

**Files:**
- Create: `app/tools/metrics_shared.py`
- Test: `tests/unit/test_metrics_shared.py`
- Modify: `docs/METRICS.md` (RPI section)

**Interfaces:**
- Produces: `compute_rpi(total_revenue, total_impressions) -> float` and `compute_weighted_average(rows, value_field, weight_field) -> float` — every later task imports these via `from .metrics_shared import compute_rpi` (add `compute_weighted_average` to the import only where used).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_metrics_shared.py` with exactly:

```python
"""Unit tests for metrics_shared.py — the single home of RPI math.

These are the phase's core validation: known pairs, the zero case, and the
equal-vs-unequal daily-values cases that distinguish ratio-of-sums from
sum-of-ratios (docs/METRICS.md rule).
"""

from app.tools.metrics_shared import compute_rpi, compute_weighted_average


class TestComputeRpi:
    def test_known_value_pair(self):
        assert compute_rpi(50.0, 1000) == 0.05

    def test_rounding_to_four_places(self):
        assert compute_rpi(1.0, 3) == 0.3333

    def test_zero_impressions_returns_zero(self):
        assert compute_rpi(100.0, 0) == 0.0

    def test_none_and_negative_impressions_return_zero(self):
        assert compute_rpi(100.0, None) == 0.0
        assert compute_rpi(100.0, -5) == 0.0

    def test_none_revenue_treated_as_zero(self):
        assert compute_rpi(None, 1000) == 0.0

    def test_equal_daily_values_coincide_with_mean_of_ratios(self):
        # Two identical days: ratio-of-sums == mean of daily ratios.
        # This agreement is coincidental and NOT probative of correctness —
        # kept to document the trap (see the unequal case below).
        days = [(10.0, 100), (10.0, 100)]
        ratio_of_sums = compute_rpi(sum(r for r, _ in days), sum(i for _, i in days))
        mean_of_ratios = round(sum(compute_rpi(r, i) for r, i in days) / len(days), 4)
        assert ratio_of_sums == mean_of_ratios == 0.1

    def test_unequal_daily_values_must_differ_from_sum_of_ratios(self):
        # THE regression-catcher: with unequal days, sum (and mean) of daily
        # ratios diverge from ratio-of-sums. Weekly RPI must be the latter.
        days = [(10.0, 1000), (50.0, 500)]  # daily RPIs 0.01 and 0.1
        ratio_of_sums = compute_rpi(60.0, 1500)
        assert ratio_of_sums == 0.04
        sum_of_ratios = sum(compute_rpi(r, i) for r, i in days)  # 0.11
        mean_of_ratios = sum_of_ratios / len(days)  # 0.055
        assert ratio_of_sums != round(sum_of_ratios, 4)
        assert ratio_of_sums != round(mean_of_ratios, 4)


class TestComputeWeightedAverage:
    def test_unequal_weights_differ_from_naive_mean(self):
        rows = [
            {"dwell_time": 10.0, "impressions": 900},
            {"dwell_time": 2.0, "impressions": 100},
        ]
        weighted = compute_weighted_average(rows, "dwell_time", "impressions")
        assert weighted == 9.2  # (10*900 + 2*100) / 1000
        naive_mean = (10.0 + 2.0) / 2  # 6.0
        assert weighted != naive_mean

    def test_equal_weights_match_naive_mean(self):
        rows = [
            {"dwell_time": 4.0, "impressions": 500},
            {"dwell_time": 6.0, "impressions": 500},
        ]
        assert compute_weighted_average(rows, "dwell_time", "impressions") == 5.0

    def test_zero_total_weight_returns_zero(self):
        rows = [{"dwell_time": 4.0, "impressions": 0}]
        assert compute_weighted_average(rows, "dwell_time", "impressions") == 0.0

    def test_missing_fields_treated_as_zero(self):
        rows = [{"dwell_time": 4.0, "impressions": 100}, {"impressions": 100}]
        assert compute_weighted_average(rows, "dwell_time", "impressions") == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_metrics_shared.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'app.tools.metrics_shared'`

- [ ] **Step 3: Write the implementation**

Create `app/tools/metrics_shared.py` with exactly:

```python
"""Shared metric computation — the ONLY place RPI math lives.

docs/METRICS.md is the authoritative definition source; this module is its
executable counterpart (Phase 4 / 04-centralize-rpi-metrics). Every tool
that returns an RPI value calls compute_rpi() instead of dividing inline;
python-level cross-row averaging of already-averaged quantities (dwell
time) goes through compute_weighted_average().

Both functions are pure arithmetic: no queries, no scoping logic. Callers
sum revenue/impressions over their own window first.
"""


def compute_rpi(total_revenue: float, total_impressions: float) -> float:
    """Revenue per impression: ratio of sums, never sum of ratios.

    Returns 0.0 when impressions are zero, negative, or None (convention
    documented in docs/METRICS.md — every pre-centralization call site
    already returned 0 for that case). None revenue is treated as 0.
    """
    if not total_impressions or total_impressions <= 0:
        return 0.0
    return round((total_revenue or 0) / total_impressions, 4)


def compute_weighted_average(rows: list, value_field: str, weight_field: str) -> float:
    """Average of rows[value_field] weighted by rows[weight_field].

    For aggregating already-averaged quantities (e.g. daily dwell-time
    averages) across rows of unequal size — an unweighted mean of averages
    over-weights small rows. Missing/None fields count as 0; returns 0.0
    when total weight is zero.
    """
    total_weight = sum((row.get(weight_field) or 0) for row in rows)
    if total_weight <= 0:
        return 0.0
    weighted_sum = sum(
        (row.get(value_field) or 0) * (row.get(weight_field) or 0) for row in rows
    )
    return round(weighted_sum / total_weight, 4)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_metrics_shared.py -v`
Expected: 11 passed

- [ ] **Step 5: Document the zero-impressions convention in the glossary**

In `docs/METRICS.md`, in the "## Revenue per Impression (RPI)" section, immediately after the paragraph beginning `Derived convenience form:`, insert as a new paragraph:

```markdown
Zero-impressions convention: the shared implementation (`compute_rpi()` in `app/tools/metrics_shared.py`, added by Phase 4) returns `0.0` when total impressions are zero — "no impressions yet" is reported as zero RPI, not an error or null. A caller that needs to distinguish "no data" from "genuinely zero RPI" must check the impressions count, not the ratio.
```

- [ ] **Step 6: Commit**

```bash
git add app/tools/metrics_shared.py tests/unit/test_metrics_shared.py docs/METRICS.md
git commit -m "Add metrics_shared: compute_rpi and compute_weighted_average"
```

---

### Task 2: Migrate `get_campaign_metrics`, enrich daily rows, normalize no-data contract

**Files:**
- Modify: `app/tools/metrics_tools.py` (function `get_campaign_metrics`, lines 167-280)
- Test: `tests/unit/test_metrics_tools.py`

**Interfaces:**
- Consumes: `compute_rpi` from Task 1.
- Produces: (a) `get_campaign_metrics` daily rows now include `"revenue"` (float) alongside existing keys — Task 7's weekly aggregation depends on this; (b) no-data contract: when no activated-video rows have impressions in the window, returns `{"status": "error", "message": "No metrics data available for campaign <id>. Metrics only exist for activated videos — use the Review Agent to activate videos first."}` — Task 7 relies on this to drop its guard; (c) test helper `_make_campaign_with_metrics(rows, num_videos=1) -> dict` at module level of `tests/unit/test_metrics_tools.py`, returning `{"campaign_id": int, "video_ids": list[int]}` — Tasks 3, 4, 7 reuse it.

- [ ] **Step 1: Add the import**

In `app/tools/metrics_tools.py`, with the other relative imports at the top of the file (near `from ..database.db import get_db_cursor`), add:

```python
from .metrics_shared import compute_rpi, compute_weighted_average
```

(`compute_weighted_average` is used by Task 7 in this same file; importing both now avoids an import churn commit later. If ruff flags it unused at this commit, add it in Task 7 instead — do not suppress the warning.)

- [ ] **Step 2: Migrate the daily loop and add revenue to daily rows**

Replace (currently lines 216-225):

```python
            # Compute RPI on the fly (THE key metric)
            rpi = round(revenue / impressions, 4) if impressions > 0 else 0

            daily_metrics.append({
                "date": row["date"],
                "impressions": impressions,
                "dwell_time": round(row["avg_dwell_time"], 1) if row["avg_dwell_time"] else 0,
                "circulation": int(row["circulation"]) if row["circulation"] else 0,
                "revenue_per_impression": rpi
            })
```

with:

```python
            rpi = compute_rpi(revenue, impressions)

            daily_metrics.append({
                "date": row["date"],
                "impressions": impressions,
                "dwell_time": round(row["avg_dwell_time"], 1) if row["avg_dwell_time"] else 0,
                "circulation": int(row["circulation"]) if row["circulation"] else 0,
                "revenue": revenue,
                "revenue_per_impression": rpi
            })
```

- [ ] **Step 3: Migrate the summary block and normalize the no-data contract**

Replace (currently lines 243-257):

```python
        summary = None
        if totals and totals["total_impressions"]:
            total_impressions = int(totals["total_impressions"])
            total_revenue = round(totals["total_revenue"], 2) if totals["total_revenue"] else 0
            # RPI is THE key metric for retail media
            rpi = round(total_revenue / total_impressions, 4) if total_impressions > 0 else 0

            summary = {
                "total_impressions": total_impressions,
                "average_dwell_time": round(totals["avg_dwell_time"], 1) if totals["avg_dwell_time"] else 0,
                "total_circulation": int(totals["total_circulation"]) if totals["total_circulation"] else 0,
                "total_revenue": total_revenue,
                "revenue_per_impression": rpi,
                "revenue_per_1000_impressions": round(rpi * 1000, 2)  # CPM equivalent
            }
```

with:

```python
        summary = None
        if totals and totals["total_impressions"]:
            total_impressions = int(totals["total_impressions"])
            total_revenue = round(totals["total_revenue"], 2) if totals["total_revenue"] else 0
            # RPI is THE key metric for retail media
            rpi = compute_rpi(total_revenue, total_impressions)

            summary = {
                "total_impressions": total_impressions,
                "average_dwell_time": round(totals["avg_dwell_time"], 1) if totals["avg_dwell_time"] else 0,
                "total_circulation": int(totals["total_circulation"]) if totals["total_circulation"] else 0,
                "total_revenue": total_revenue,
                "revenue_per_impression": rpi,
                "revenue_per_1000_impressions": round(rpi * 1000, 2)  # CPM equivalent
            }

        # Normalized no-data contract (Phase 4): a window with no
        # activated-video impressions is an explicit error, never
        # summary=None under status="success" (the ambiguity behind the
        # Phase-2 visualization crash).
        if not summary or not daily_metrics:
            return {
                "status": "error",
                "message": (
                    f"No metrics data available for campaign {campaign_id}. "
                    "Metrics only exist for activated videos — use the Review "
                    "Agent to activate videos first."
                ),
            }
```

Then in the success return (currently lines 268-280), delete the line:

```python
            "note": "Metrics only available for activated videos. Use Review Agent to activate pending videos." if not summary else None
```

(the no-data path now returns earlier, so the conditional note is dead; remove the trailing comma on the preceding line accordingly).

- [ ] **Step 4: Add the test helper and tests**

In `tests/unit/test_metrics_tools.py`: add `import pytest` is NOT needed (no skips used); add these imports and module-level helper directly below the existing `from unittest.mock import patch`:

```python
from datetime import date, timedelta


def _make_campaign_with_metrics(rows, num_videos=1):
    """Create a campaign with activated video(s) and controlled metric rows.

    rows: dicts with keys metric_date (ISO str), impressions, revenue, and
    optional dwell_time_seconds, circulation, video_index (default 0).
    Returns {"campaign_id": int, "video_ids": [int, ...]}.
    """
    from app.database.db import get_db_cursor
    from app.tools.campaign_tools import create_campaign

    created = create_campaign(
        product_id=1, store_name="Parity Test Store", city="Austin", state="TX"
    )
    assert created["status"] == "success"
    campaign_id = created["campaign"]["id"]

    video_ids = []
    with get_db_cursor() as cursor:
        for i in range(num_videos):
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, video_filename, status)"
                " VALUES (?, ?, 'activated')",
                (campaign_id, f"parity-test-{campaign_id}-{i}.mp4"),
            )
            video_ids.append(cursor.lastrowid)
        for r in rows:
            cursor.execute(
                "INSERT INTO video_metrics"
                " (video_id, metric_date, impressions, dwell_time_seconds,"
                "  circulation, revenue) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    video_ids[r.get("video_index", 0)],
                    r["metric_date"],
                    r["impressions"],
                    r.get("dwell_time_seconds", 5.0),
                    r.get("circulation", 0),
                    r["revenue"],
                ),
            )
    return {"campaign_id": campaign_id, "video_ids": video_ids}


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()
```

Add to `class TestGetCampaignMetrics`:

```python
    def test_no_data_returns_error_status(self, test_db):
        """Normalized contract: no activated metrics -> status error, never
        summary=None under status success."""
        from app.tools.campaign_tools import create_campaign
        from app.tools.metrics_tools import get_campaign_metrics

        created = create_campaign(
            product_id=1, store_name="No Data Store", city="Austin", state="TX"
        )
        result = get_campaign_metrics(campaign_id=created["campaign"]["id"])

        assert result["status"] == "error"
        assert "No metrics data available" in result["message"]

    def test_summary_rpi_is_ratio_of_sums(self, test_db):
        """Summary RPI == compute_rpi over summed rows; daily rows carry
        revenue and per-day RPI parity (thin-wrapper check)."""
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import get_campaign_metrics

        rows = [
            {"metric_date": _days_ago(1), "impressions": 1000, "revenue": 10.0},
            {"metric_date": _days_ago(2), "impressions": 500, "revenue": 50.0},
            {"metric_date": _days_ago(3), "impressions": 2000, "revenue": 20.0},
        ]
        made = _make_campaign_with_metrics(rows)
        result = get_campaign_metrics(campaign_id=made["campaign_id"], days=30)

        assert result["status"] == "success"
        expected = compute_rpi(80.0, 3500)
        assert result["summary"]["revenue_per_impression"] == expected
        # Non-probative-equality guard: ratio-of-sums must differ from the
        # mean of daily ratios for this deliberately unequal data.
        daily_rpis = [d["revenue_per_impression"] for d in result["daily_metrics"]]
        assert expected != round(sum(daily_rpis) / len(daily_rpis), 4)
        for d in result["daily_metrics"]:
            assert "revenue" in d
            assert d["revenue_per_impression"] == compute_rpi(
                d["revenue"], d["impressions"]
            )
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py -v`
Expected: all pass, including the two new tests and the pre-existing `test_no_metrics_campaign_returns_clean_error` (its asserted message is unchanged — the error now originates in `get_campaign_metrics` and propagates through the visualization's existing `status == "error"` early return).

- [ ] **Step 6: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Centralize get_campaign_metrics RPI; normalize no-data contract"
```

---

### Task 3: `get_top_performing_ads` — optional filters + `compute_rpi`

**Files:**
- Modify: `app/tools/metrics_tools.py` (function `get_top_performing_ads`, currently starting at line 283)
- Test: `tests/unit/test_metrics_tools.py`

**Interfaces:**
- Consumes: `compute_rpi` (imported in Task 2); `_make_campaign_with_metrics`/`_days_ago` helpers (Task 2, same test file).
- Produces: signature `get_top_performing_ads(metric: str = "revenue_per_impression", limit: int = 5, campaign_id: int = None, days: int = None) -> dict` — defaults preserve today's global/all-time contract exactly.

- [ ] **Step 1: Change signature and docstring**

Replace:

```python
def get_top_performing_ads(metric: str = "revenue_per_impression", limit: int = 5) -> dict:
    """Get top performing video ads across all campaigns.

    Identifies the best ads and their key characteristics for insights.
    Uses NEW schema: video_metrics + campaign_videos + products (HITL workflow).
    Only includes activated videos.

    Args:
        metric: Metric to rank by - one of: revenue_per_impression, impressions, dwell_time, circulation
        limit: Number of top ads to return

    Returns:
        Dictionary with top ads and their characteristics
    """
    print(f"[DEBUG get_top_performing_ads] Starting with metric={metric}, limit={limit}")
```

with:

```python
def get_top_performing_ads(
    metric: str = "revenue_per_impression",
    limit: int = 5,
    campaign_id: int = None,
    days: int = None,
) -> dict:
    """Get top performing video ads across all campaigns.

    Identifies the best ads and their key characteristics for insights.
    Uses NEW schema: video_metrics + campaign_videos + products (HITL workflow).
    Only includes activated videos. By default the ranking is global (all
    campaigns, all time); the optional filters narrow it when provided.

    Args:
        metric: Metric to rank by - one of: revenue_per_impression, impressions, dwell_time, circulation
        limit: Number of top ads to return
        campaign_id: Optional - restrict ranking to one campaign
        days: Optional - restrict ranking to the last N days of metrics

    Returns:
        Dictionary with top ads and their characteristics
    """
    print(f"[DEBUG get_top_performing_ads] Starting with metric={metric}, limit={limit}, campaign_id={campaign_id}, days={days}")
```

- [ ] **Step 2: Make the query filterable and annotate the surviving SQL ratio**

Replace the `metric_column_map` comment line directly above the dict (currently `# RPI must be computed, not a direct column`) with:

```python
    # SQL ratio-of-sums used for ORDER BY ranking only — every RPI value
    # RETURNED to the caller comes from compute_rpi() (see the loop below).
```

Then replace the `cursor.execute(f'''...''', (limit,))` call (currently lines 314-343) with:

```python
        vm_join = "LEFT JOIN video_metrics vm ON cv.id = vm.video_id"
        params: list = []
        if days:
            vm_join += " AND vm.metric_date >= date('now', ?)"
            params.append(f"-{days} days")
        where_clause = "WHERE cv.status = 'activated'"
        if campaign_id:
            where_clause += " AND cv.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)

        cursor.execute(f'''
            SELECT
                cv.id as video_id,
                c.id as campaign_id,
                c.name as campaign_name,
                c.category,
                c.city,
                c.state,
                cv.video_filename,
                cv.variation_name,
                cv.variation_params,
                p.name as product_name,
                p.category as product_category,
                p.color as product_color,
                p.style as product_style,
                {metric_column_map[metric]} as metric_value,
                SUM(vm.impressions) as total_impressions,
                AVG(vm.dwell_time_seconds) as avg_dwell_time,
                SUM(vm.circulation) as total_circulation,
                SUM(vm.revenue) as total_revenue
            FROM campaign_videos cv
            JOIN campaigns c ON cv.campaign_id = c.id
            LEFT JOIN products p ON cv.product_id = p.id
            {vm_join}
            {where_clause}
            GROUP BY cv.id
            HAVING metric_value IS NOT NULL AND total_revenue > 0
            ORDER BY metric_value DESC
            LIMIT ?
        ''', params)
```

(The `days` condition lives in the JOIN's ON clause, not WHERE, to preserve the LEFT JOIN shape; the HAVING clause already excludes metric-less videos in both cases.)

- [ ] **Step 3: Migrate the returned RPI values**

In the row loop, replace:

```python
            # Compute RPI
            rpi = round(total_revenue / total_impressions, 4) if total_impressions > 0 else 0
```

with:

```python
            rpi = compute_rpi(total_revenue, total_impressions)
```

and replace the metrics-dict line:

```python
                    f"{metric}": round(row["metric_value"], 4) if row["metric_value"] else 0,
```

with:

```python
                    f"{metric}": rpi if metric == "revenue_per_impression"
                    else (round(row["metric_value"], 4) if row["metric_value"] else 0),
```

- [ ] **Step 4: Add tests**

Add to `class TestGetTopPerformingAds` in `tests/unit/test_metrics_tools.py`:

```python
    def test_optional_filters_narrow_results(self, test_db):
        """campaign_id restricts to one campaign; days excludes old metrics;
        the default stays global/all-time."""
        from app.tools.metrics_tools import get_top_performing_ads

        recent = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 100, "revenue": 90.0}]
        )
        old = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(60), "impressions": 100, "revenue": 80.0}]
        )

        unfiltered = get_top_performing_ads(limit=100)
        assert unfiltered["status"] == "success"
        returned_campaigns = {a["campaign"]["id"] for a in unfiltered["top_ads"]}
        assert recent["campaign_id"] in returned_campaigns
        assert old["campaign_id"] in returned_campaigns  # all-time default

        scoped = get_top_performing_ads(limit=100, campaign_id=recent["campaign_id"])
        assert {a["campaign"]["id"] for a in scoped["top_ads"]} == {recent["campaign_id"]}

        windowed = get_top_performing_ads(limit=100, days=30)
        windowed_campaigns = {a["campaign"]["id"] for a in windowed["top_ads"]}
        assert recent["campaign_id"] in windowed_campaigns
        assert old["campaign_id"] not in windowed_campaigns

    def test_returned_rpi_is_thin_wrapper_over_compute_rpi(self, test_db):
        """Every returned RPI equals compute_rpi over the ad's own totals."""
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import get_top_performing_ads

        result = get_top_performing_ads(limit=100)
        assert result["status"] == "success"
        assert result["top_ads"], "demo DB should have activated ads with metrics"
        for ad in result["top_ads"]:
            m = ad["metrics"]
            assert m["revenue_per_impression"] == compute_rpi(
                m["total_revenue"], m["total_impressions"]
            )
            assert m["revenue_per_impression"] == m[result["ranked_by"]]
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py -v`
Expected: all pass (pre-existing TestGetTopPerformingAds tests unchanged — they call with no filters).

- [ ] **Step 6: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Add optional filters to get_top_performing_ads; return RPI via compute_rpi"
```

---

### Task 4: Repair `get_campaign_insights` (date scoping, real RPI trend, day-grouped best/worst)

**Files:**
- Modify: `app/tools/metrics_tools.py` (function `get_campaign_insights`, currently starting at line 413)
- Test: `tests/unit/test_metrics_tools.py`

**Interfaces:**
- Consumes: `compute_rpi` (Task 2 import); test helpers from Task 2.
- Produces: signature `get_campaign_insights(campaign_id: int, days: int = 30) -> dict`; return gains `"period": f"last_{days}_days"`; `best_day`/`worst_day` keep their existing keys (`date`, `revenue_per_impression`, `impressions`, `dwell_time`).

- [ ] **Step 1: Change signature and docstring args**

Replace `def get_campaign_insights(campaign_id: int) -> dict:` with:

```python
def get_campaign_insights(campaign_id: int, days: int = 30) -> dict:
```

In its docstring Args section, replace:

```python
    Args:
        campaign_id: The ID of the campaign
```

with:

```python
    Args:
        campaign_id: The ID of the campaign
        days: Number of days of metrics to analyze (default: 30)
```

- [ ] **Step 2: Date-scope the weekly trend query and fix the trend to compare RPI**

Replace (currently lines 465-489):

```python
        # Get performance trend (weekly aggregates) - using RPI as key metric
        cursor.execute('''
            SELECT
                strftime('%Y-W%W', vm.metric_date) as week,
                SUM(vm.impressions) as impressions,
                SUM(vm.revenue) as revenue,
                AVG(vm.dwell_time_seconds) as avg_dwell
            FROM video_metrics vm
            JOIN campaign_videos cv ON vm.video_id = cv.id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
            GROUP BY week
            ORDER BY week
        ''', (campaign_id,))

        weeks = cursor.fetchall()

        trend = "stable"
        if len(weeks) >= 2:
            first_half_rev = sum(w["revenue"] for w in weeks[:len(weeks)//2] if w["revenue"])
            second_half_rev = sum(w["revenue"] for w in weeks[len(weeks)//2:] if w["revenue"])
            if first_half_rev > 0 and second_half_rev > first_half_rev * 1.1:
                trend = "improving"
            elif first_half_rev > 0 and second_half_rev < first_half_rev * 0.9:
                trend = "declining"
```

with:

```python
        # Get performance trend (weekly aggregates) - using RPI as key metric
        cursor.execute('''
            SELECT
                strftime('%Y-W%W', vm.metric_date) as week,
                SUM(vm.impressions) as impressions,
                SUM(vm.revenue) as revenue,
                AVG(vm.dwell_time_seconds) as avg_dwell
            FROM video_metrics vm
            JOIN campaign_videos cv ON vm.video_id = cv.id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
              AND vm.metric_date >= date('now', ?)
            GROUP BY week
            ORDER BY week
        ''', (campaign_id, f'-{days} days'))

        weeks = cursor.fetchall()

        # Trend compares RPI (ratio of sums per half), not raw revenue —
        # revenue can rise while RPI falls if impressions rise faster.
        trend = "stable"
        if len(weeks) >= 2:
            half = len(weeks) // 2
            first_half_rpi = compute_rpi(
                sum(w["revenue"] or 0 for w in weeks[:half]),
                sum(w["impressions"] or 0 for w in weeks[:half]),
            )
            second_half_rpi = compute_rpi(
                sum(w["revenue"] or 0 for w in weeks[half:]),
                sum(w["impressions"] or 0 for w in weeks[half:]),
            )
            if first_half_rpi > 0 and second_half_rpi > first_half_rpi * 1.1:
                trend = "improving"
            elif first_half_rpi > 0 and second_half_rpi < first_half_rpi * 0.9:
                trend = "declining"
```

- [ ] **Step 3: Replace the two per-row best/worst queries with one day-grouped query**

Replace (currently lines 491-515, both `cursor.execute` blocks for best_day and worst_day):

```python
        # Get best and worst performing days by RPI
        cursor.execute('''
            SELECT vm.metric_date as date, vm.revenue, vm.impressions, vm.dwell_time_seconds,
                   vm.revenue * 1.0 / NULLIF(vm.impressions, 0) as rpi
            FROM video_metrics vm
            JOIN campaign_videos cv ON vm.video_id = cv.id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
            ORDER BY rpi DESC
            LIMIT 1
        ''', (campaign_id,))
        best_day = cursor.fetchone()

        cursor.execute('''
            SELECT vm.metric_date as date, vm.revenue, vm.impressions, vm.dwell_time_seconds,
                   vm.revenue * 1.0 / NULLIF(vm.impressions, 0) as rpi
            FROM video_metrics vm
            JOIN campaign_videos cv ON vm.video_id = cv.id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
              AND vm.impressions > 0
            ORDER BY rpi ASC
            LIMIT 1
        ''', (campaign_id,))
        worst_day = cursor.fetchone()
```

with:

```python
        # Best and worst performing days by RPI — a "day" is the aggregate
        # across ALL activated videos that day (GROUP BY date), not one
        # video_metrics row. RPI per day via compute_rpi (ratio of sums).
        cursor.execute('''
            SELECT
                vm.metric_date as date,
                SUM(vm.revenue) as revenue,
                SUM(vm.impressions) as impressions,
                AVG(vm.dwell_time_seconds) as avg_dwell
            FROM video_metrics vm
            JOIN campaign_videos cv ON vm.video_id = cv.id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
              AND vm.metric_date >= date('now', ?)
            GROUP BY vm.metric_date
        ''', (campaign_id, f'-{days} days'))

        day_aggregates = [
            {
                "date": r["date"],
                "revenue_per_impression": compute_rpi(r["revenue"], r["impressions"]),
                "impressions": int(r["impressions"]) if r["impressions"] else 0,
                "dwell_time": round(r["avg_dwell"], 1) if r["avg_dwell"] else 0,
            }
            for r in cursor.fetchall()
        ]
        best_day = max(
            day_aggregates, key=lambda d: d["revenue_per_impression"], default=None
        )
        days_with_impressions = [d for d in day_aggregates if d["impressions"] > 0]
        worst_day = min(
            days_with_impressions,
            key=lambda d: d["revenue_per_impression"],
            default=None,
        )
```

- [ ] **Step 4: Date-scope the video-performance query and migrate its RPI**

Replace (currently lines 517-532):

```python
        # Get video performance comparison
        cursor.execute('''
            SELECT
                cv.id,
                cv.variation_name,
                cv.variation_params,
                SUM(vm.revenue) as total_revenue,
                SUM(vm.impressions) as total_impressions,
                AVG(vm.dwell_time_seconds) as avg_dwell
            FROM campaign_videos cv
            LEFT JOIN video_metrics vm ON cv.id = vm.video_id
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
            GROUP BY cv.id
            ORDER BY total_revenue DESC
        ''', (campaign_id,))
```

with:

```python
        # Get video performance comparison
        cursor.execute('''
            SELECT
                cv.id,
                cv.variation_name,
                cv.variation_params,
                SUM(vm.revenue) as total_revenue,
                SUM(vm.impressions) as total_impressions,
                AVG(vm.dwell_time_seconds) as avg_dwell
            FROM campaign_videos cv
            LEFT JOIN video_metrics vm ON cv.id = vm.video_id
                AND vm.metric_date >= date('now', ?)
            WHERE cv.campaign_id = ?
              AND cv.status = 'activated'
            GROUP BY cv.id
            ORDER BY total_revenue DESC
        ''', (f'-{days} days', campaign_id))
```

and further down replace:

```python
                video_rpi = round(best_video["total_revenue"] / best_video["total_impressions"], 4)
```

with:

```python
                video_rpi = compute_rpi(best_video["total_revenue"], best_video["total_impressions"])
```

- [ ] **Step 5: Update the insight line and the return dict for the new best/worst shape**

Replace (currently lines 546-549):

```python
        if best_day:
            rpi = round(best_day["rpi"], 4) if best_day["rpi"] else 0
            dwell = round(best_day["dwell_time_seconds"], 1) if best_day["dwell_time_seconds"] else 0
            insights.append(f"Best performing day: {best_day['date']} (RPI: ${rpi:.4f}, Dwell: {dwell}s)")
```

with:

```python
        if best_day:
            insights.append(
                f"Best performing day: {best_day['date']} "
                f"(RPI: ${best_day['revenue_per_impression']:.4f}, "
                f"Dwell: {best_day['dwell_time']}s)"
            )
```

In the final return dict, add `"period": f"last_{days}_days",` directly after the `"activated_videos": activated_count,` line, and replace the two trailing dict-building blocks:

```python
            "best_day": {
                "date": best_day["date"],
                "revenue_per_impression": round(best_day["rpi"], 4) if best_day["rpi"] else 0,
                "impressions": int(best_day["impressions"]),
                "dwell_time": round(best_day["dwell_time_seconds"], 1) if best_day["dwell_time_seconds"] else 0
            } if best_day else None,
            "worst_day": {
                "date": worst_day["date"],
                "revenue_per_impression": round(worst_day["rpi"], 4) if worst_day["rpi"] else 0,
                "impressions": int(worst_day["impressions"]),
                "dwell_time": round(worst_day["dwell_time_seconds"], 1) if worst_day["dwell_time_seconds"] else 0
            } if worst_day else None
```

with:

```python
            "best_day": best_day,
            "worst_day": worst_day
```

(the day_aggregates dicts already carry exactly the keys `date`, `revenue_per_impression`, `impressions`, `dwell_time`).

- [ ] **Step 6: Add the three repair tests**

Add to `class TestGetCampaignInsights` in `tests/unit/test_metrics_tools.py`:

```python
    def test_date_scoping_excludes_old_metrics(self, test_db):
        """days=30 must ignore a 200-day-old outlier; a wide window sees it."""
        from app.tools.metrics_tools import get_campaign_insights

        made = _make_campaign_with_metrics([
            {"metric_date": _days_ago(200), "impressions": 100, "revenue": 1000.0},
            {"metric_date": _days_ago(1), "impressions": 1000, "revenue": 50.0},
        ])

        scoped = get_campaign_insights(campaign_id=made["campaign_id"], days=30)
        assert scoped["status"] == "success"
        assert scoped["best_day"]["date"] == _days_ago(1)

        wide = get_campaign_insights(campaign_id=made["campaign_id"], days=365)
        assert wide["best_day"]["date"] == _days_ago(200)

    def test_trend_compares_rpi_not_revenue(self, test_db):
        """Revenue rises while RPI falls -> trend must be 'declining'.
        (The old code compared raw revenue and would say 'improving'.)"""
        from app.tools.metrics_tools import get_campaign_insights

        rows = []
        for n in range(27, 13, -1):  # older half: low revenue, HIGH RPI (0.1)
            rows.append({"metric_date": _days_ago(n), "impressions": 500, "revenue": 50.0})
        for n in range(13, 0, -1):  # newer half: high revenue, LOW RPI (0.02)
            rows.append({"metric_date": _days_ago(n), "impressions": 5000, "revenue": 100.0})
        made = _make_campaign_with_metrics(rows)

        result = get_campaign_insights(campaign_id=made["campaign_id"], days=30)
        assert result["status"] == "success"
        assert result["performance_trend"] == "declining"

    def test_best_day_groups_by_day_not_row(self, test_db):
        """Day A holds the single best ROW (RPI 1.0) but day B is the best
        aggregated DAY: A = (100+1)/(100+1000) ≈ 0.0918 < B = 50/500 = 0.1."""
        from app.tools.metrics_tools import get_campaign_insights

        made = _make_campaign_with_metrics(
            [
                {"metric_date": _days_ago(2), "impressions": 100, "revenue": 100.0, "video_index": 0},
                {"metric_date": _days_ago(2), "impressions": 1000, "revenue": 1.0, "video_index": 1},
                {"metric_date": _days_ago(1), "impressions": 500, "revenue": 50.0, "video_index": 0},
            ],
            num_videos=2,
        )

        result = get_campaign_insights(campaign_id=made["campaign_id"], days=30)
        assert result["status"] == "success"
        assert result["best_day"]["date"] == _days_ago(1)
        assert result["best_day"]["revenue_per_impression"] == 0.1
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Repair get_campaign_insights: date scoping, RPI trend, day-grouped best/worst"
```

---

### Task 5: Mechanical migrations (`compare_campaigns`, `get_campaign`, `get_video_details`) + phase-doc amendment

**Files:**
- Modify: `app/tools/metrics_tools.py` (`compare_campaigns`, currently line 658)
- Modify: `app/tools/campaign_tools.py` (`get_campaign`, currently line 254)
- Modify: `app/tools/review_tools.py` (`get_video_details`, currently line 862)
- Modify: `.docs/version2-plan/04-centralize-rpi-metrics.md`
- Test: `tests/unit/test_metrics_tools.py`, `tests/unit/test_campaign_tools.py`, `tests/unit/test_review_tools.py`

**Interfaces:**
- Consumes: `compute_rpi` (Task 1); `_make_campaign_with_metrics`/`_days_ago` (Task 2, importable across test files as `from tests.unit.test_metrics_tools import _make_campaign_with_metrics, _days_ago` — pytest rootdir is the repo root and `tests/unit/` has no `__init__.py`, so instead REPEAT the two helpers verbatim at module level in each test file that needs them; they are 40 lines and duplication across test files is acceptable here).
- Produces: nothing new — behavior-identical swaps.

- [ ] **Step 1: `compare_campaigns`**

In `app/tools/metrics_tools.py`, replace:

```python
                # Compute RPI on the fly
                rpi = round(total_revenue / total_impressions, 4) if total_impressions > 0 else 0
```

with:

```python
                rpi = compute_rpi(total_revenue, total_impressions)
```

- [ ] **Step 2: `get_campaign`**

In `app/tools/campaign_tools.py`: add `from .metrics_shared import compute_rpi` with the other relative imports at the top (near `from ..database.db import get_db_cursor, get_product`). Then replace (currently line 254):

```python
            rpi = round(total_revenue / total_impressions, 4) if total_impressions > 0 else 0
```

with:

```python
            rpi = compute_rpi(total_revenue, total_impressions)
```

- [ ] **Step 3: `get_video_details`**

In `app/tools/review_tools.py`: add `from .metrics_shared import compute_rpi` with the other relative imports at the top. Then replace (currently line 862):

```python
                    "rpi": round(m["total_revenue"] / m["total_impressions"], 4) if m["total_impressions"] > 0 else 0
```

with:

```python
                    "rpi": compute_rpi(m["total_revenue"], m["total_impressions"])
```

- [ ] **Step 4: Verify the mock generators need no change, then amend the phase doc**

Run: `grep -n "revenue" app/database/mock_data.py app/tools/review_tools.py | grep "/"`
Expected: no division lines in either `_generate_mock_video_metrics` (both synthesize revenue by multiplication).

In `.docs/version2-plan/04-centralize-rpi-metrics.md`, directly below the Steps list item beginning `5. Do not touch `_generate_mock_video_metrics()``, add:

```markdown
> **Amended (workstream 04, 2026-07-16):** Step 5 is vacuous as written — neither `_generate_mock_video_metrics()` stores an RPI figure or divides revenue by impressions; both synthesize `revenue` as impressions × an RNG rate (multiplication only: `mock_data.py:223-224`, `review_tools.py:482/503`). Verified during this workstream's migration sweep; no change made to either generator. Phase 5 still owns their unification.
```

- [ ] **Step 5: Add parity tests**

Add to `class TestCompareCampaigns` in `tests/unit/test_metrics_tools.py`:

```python
    def test_comparison_rpi_is_thin_wrapper(self, test_db):
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import compare_campaigns

        a = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 1000, "revenue": 10.0},
             {"metric_date": _days_ago(2), "impressions": 500, "revenue": 50.0}]
        )
        b = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 200, "revenue": 4.0}]
        )
        result = compare_campaigns(campaign_ids=[a["campaign_id"], b["campaign_id"]])
        assert result["status"] == "success"
        for comp in result["comparisons"]:
            m = comp["metrics"]
            assert m["revenue_per_impression"] == compute_rpi(
                m["total_revenue"], m["total_impressions"]
            )
```

In `tests/unit/test_campaign_tools.py`, add at module level (below the existing imports) the two helpers `_make_campaign_with_metrics` and `_days_ago` copied VERBATIM from `tests/unit/test_metrics_tools.py` (Task 2 Step 4 above shows the exact code), then add to `class TestGetCampaign`:

```python
    def test_metrics_summary_rpi_is_thin_wrapper(self, test_db):
        from app.tools.campaign_tools import get_campaign
        from app.tools.metrics_shared import compute_rpi

        made = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 1000, "revenue": 10.0},
             {"metric_date": _days_ago(2), "impressions": 500, "revenue": 50.0}]
        )
        result = get_campaign(campaign_id=made["campaign_id"])
        assert result["status"] == "success"
        summary = result["campaign"]["metrics_summary"]
        assert summary is not None
        assert summary["revenue_per_impression"] == compute_rpi(
            summary["total_revenue"], summary["total_impressions"]
        )
```

(If the campaign dict nests metrics under a different key, locate it by the `"period": "last_30_days"` marker in `get_campaign`'s return and adjust the two access lines — the assertion itself must stay identical.)

In `tests/unit/test_review_tools.py`, add the same two helpers verbatim at module level, then add to `class TestGetVideoDetails`:

```python
    def test_rpi_is_thin_wrapper(self, test_db):
        from app.tools.metrics_shared import compute_rpi
        from app.tools.review_tools import get_video_details

        made = _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 1000, "revenue": 10.0},
             {"metric_date": _days_ago(2), "impressions": 500, "revenue": 50.0}]
        )
        result = get_video_details(video_id=made["video_ids"][0])
        assert result["status"] == "success"
        metrics = result["video"]["metrics_summary"]
        assert metrics is not None
        assert metrics["rpi"] == compute_rpi(
            metrics["total_revenue"], metrics["total_impressions"]
        )
```

(Same note: if `metrics_summary` sits under a different key in `get_video_details`' return, locate by the `"days_tracked"` marker and adjust access only.)

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py tests/unit/test_campaign_tools.py tests/unit/test_review_tools.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app/tools/metrics_tools.py app/tools/campaign_tools.py app/tools/review_tools.py tests/unit/test_metrics_tools.py tests/unit/test_campaign_tools.py tests/unit/test_review_tools.py .docs/version2-plan/04-centralize-rpi-metrics.md
git commit -m "Migrate compare_campaigns, get_campaign, get_video_details to compute_rpi"
```

---

### Task 6: `maps_tools.py` migrations + weighted regional dwell

**Files:**
- Modify: `app/tools/maps_tools.py` (lines 558, 584 in `get_campaign_map_data`; 962, 988-1013 in `generate_map_visualization`)
- Test: `tests/unit/test_maps_tools.py`

**Interfaces:**
- Consumes: `compute_rpi`, `compute_weighted_average` (Task 1).
- Produces: nothing new — same return shapes; regional `avg_dwell_time` becomes impressions-weighted (a deliberate fix, per the phase doc's "dwell time needs its own correctly-weighted rule").

- [ ] **Step 1: Add the import**

In `app/tools/maps_tools.py`, with the other relative imports at the top, add:

```python
from .metrics_shared import compute_rpi, compute_weighted_average
```

- [ ] **Step 2: Migrate `get_campaign_map_data`'s two sites**

Replace (currently line 558):

```python
                    rpi = round(camp_revenue / camp_impressions, 4) if camp_impressions > 0 else 0
```

with:

```python
                    rpi = compute_rpi(camp_revenue, camp_impressions)
```

Replace (currently line 584, in the summary dict):

```python
                "overall_rpi": round(total_revenue / total_impressions, 4) if total_impressions > 0 else 0
```

with:

```python
                "overall_rpi": compute_rpi(total_revenue, total_impressions)
```

- [ ] **Step 3: Migrate `generate_map_visualization`'s per-campaign RPI**

Replace (currently lines 961-962):

```python
        # Compute RPI on the fly
        rpi = round(revenue / impressions, 4) if impressions > 0 else 0
```

with:

```python
        rpi = compute_rpi(revenue, impressions)
```

- [ ] **Step 4: Weight the regional dwell aggregation and migrate regional RPI**

First verify `dwell_time_sum` has no other consumers:
Run: `grep -n "dwell_time_sum" app/tools/maps_tools.py`
Expected: exactly two matches (the dict initializer ~989 and the `+=` accumulation ~993) plus the average computation ~1008-1009. If it appears anywhere else, STOP and report BLOCKED.

Replace (currently lines 988-994):

```python
        if region not in regional_data:
            regional_data[region] = {"revenue": 0, "impressions": 0, "campaigns": 0, "dwell_time_sum": 0, "circulation": 0}
        regional_data[region]["revenue"] += revenue
        regional_data[region]["impressions"] += impressions
        regional_data[region]["campaigns"] += 1
        regional_data[region]["dwell_time_sum"] += dwell_time
        regional_data[region]["circulation"] += circulation
```

with:

```python
        if region not in regional_data:
            regional_data[region] = {"revenue": 0, "impressions": 0, "campaigns": 0, "dwell_rows": [], "circulation": 0}
        regional_data[region]["revenue"] += revenue
        regional_data[region]["impressions"] += impressions
        regional_data[region]["campaigns"] += 1
        regional_data[region]["dwell_rows"].append(
            {"dwell_time": dwell_time, "impressions": impressions}
        )
        regional_data[region]["circulation"] += circulation
```

Replace (currently lines 1005-1013):

```python
    # Calculate regional averages and RPI
    for region in regional_data:
        if regional_data[region]["campaigns"] > 0:
            regional_data[region]["avg_dwell_time"] = round(
                regional_data[region]["dwell_time_sum"] / regional_data[region]["campaigns"], 1
            )
            regional_data[region]["rpi"] = round(
                regional_data[region]["revenue"] / regional_data[region]["impressions"], 4
            ) if regional_data[region]["impressions"] > 0 else 0
```

with:

```python
    # Calculate regional averages and RPI. Dwell is impressions-weighted:
    # an unweighted mean of per-campaign averages over-weights small
    # campaigns (see docs/METRICS.md / metrics_shared).
    for region in regional_data:
        if regional_data[region]["campaigns"] > 0:
            regional_data[region]["avg_dwell_time"] = round(
                compute_weighted_average(
                    regional_data[region]["dwell_rows"], "dwell_time", "impressions"
                ), 1
            )
            regional_data[region]["rpi"] = compute_rpi(
                regional_data[region]["revenue"],
                regional_data[region]["impressions"],
            )
        del regional_data[region]["dwell_rows"]
```

(Note `del regional_data[region]["dwell_rows"]` sits OUTSIDE the `if`, in the loop body, so no list ever leaks into the downstream prompt formatting regardless of the campaigns count.)

- [ ] **Step 5: Add tests**

In `tests/unit/test_maps_tools.py`, add the two helpers `_make_campaign_with_metrics` and `_days_ago` verbatim at module level (same code as Task 2 Step 4), then add a new class:

```python
class TestRpiCentralization:
    def test_map_data_rpi_is_thin_wrapper(self, test_db):
        from app.tools.maps_tools import get_campaign_map_data
        from app.tools.metrics_shared import compute_rpi

        _make_campaign_with_metrics(
            [{"metric_date": _days_ago(1), "impressions": 1000, "revenue": 10.0},
             {"metric_date": _days_ago(2), "impressions": 500, "revenue": 50.0}]
        )
        result = get_campaign_map_data(include_metrics=True)
        assert result["status"] == "success"
        for loc in result["locations"]:
            if loc.get("metrics"):
                m = loc["metrics"]
                assert m["rpi"] == compute_rpi(
                    m["total_revenue"], m["total_impressions"]
                )
        s = result["summary"]
        assert s["overall_rpi"] == compute_rpi(
            s["total_revenue"], s["total_impressions"]
        )
```

(Check `get_campaign_map_data`'s actual signature first — if `include_metrics` defaults to True, call it with no arguments; the assertions stay identical.)

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/unit/test_maps_tools.py tests/unit/test_campaign_tools.py -v -m "not slow"`
Expected: all pass (test_campaign_tools included because it hosts maps-tool test classes too).

- [ ] **Step 7: Commit**

```bash
git add app/tools/maps_tools.py tests/unit/test_maps_tools.py
git commit -m "Migrate maps_tools RPI sites to compute_rpi; weight regional dwell by impressions"
```

---

### Task 7: Fix the weekly-chart aggregation + weekly-RPI regression test

**Files:**
- Modify: `app/tools/metrics_tools.py` (`generate_metrics_visualization`: guard at 768-779, data_points at 797-807, bar_chart weekly block at 910-925 — all currently-cited numbers shift after Tasks 2-5; locate by quoted code)
- Test: `tests/unit/test_metrics_tools.py`

**Interfaces:**
- Consumes: `compute_rpi`, `compute_weighted_average` (imported in Task 2); Task 2's daily rows now carrying `"revenue"`; Task 2's no-data error contract; test helpers from Task 2.
- Produces: module-level `_aggregate_week(week_slice: list, metric: str) -> float` in `metrics_tools.py` (private helper, unit-tested directly).

- [ ] **Step 1: Remove the now-redundant guard**

In `generate_metrics_visualization`, delete this entire block (the `status == "error"` early-return three lines above it now covers the no-data case at the source, per Task 2):

```python
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
```

- [ ] **Step 2: Enrich data_points with the raw fields**

Replace:

```python
    data_points = []
    for day in daily_metrics[:min(days, len(daily_metrics))]:
        data_points.append({
            "date": day["date"],
            "value": day.get(metric, 0)
        })
```

with:

```python
    data_points = []
    for day in daily_metrics[:min(days, len(daily_metrics))]:
        data_points.append({
            "date": day["date"],
            "value": day.get(metric, 0),
            "revenue": day.get("revenue", 0),
            "impressions": day.get("impressions", 0),
            "dwell_time": day.get("dwell_time", 0),
        })
```

- [ ] **Step 3: Add the module-level weekly aggregator**

Directly above `async def generate_metrics_visualization(`, add:

```python
def _aggregate_week(week_slice: list, metric: str) -> float:
    """Aggregate one week of enriched daily rows using the metric's rule.

    Ratio metrics recompute ratio-of-sums via compute_rpi; dwell time is an
    impressions-weighted average; additive metrics (impressions,
    circulation) sum. This is the per-metric aggregation rule Phase 4
    centralized — the old code summed daily values for every metric, which
    is meaningless for ratios (see docs/METRICS.md).
    """
    if metric == "revenue_per_impression":
        return compute_rpi(
            sum(d["revenue"] for d in week_slice),
            sum(d["impressions"] for d in week_slice),
        )
    if metric == "dwell_time":
        return round(
            compute_weighted_average(week_slice, "dwell_time", "impressions"), 1
        )
    return sum(d["value"] for d in week_slice)
```

- [ ] **Step 4: Use it in the bar_chart block**

Replace:

```python
            if week_slice:
                # KNOWN BUG (flagged, fix in Phase 4 / 04-centralize-rpi-metrics):
                # summing per-day values is wrong for ratio metrics like
                # revenue_per_impression — a weekly RPI must be recomputed as
                # sum(revenue)/sum(impressions), not sum(daily ratios).
                # Phase 4 centralizes per-metric aggregation rules.
                week_total = sum(d["value"] for d in week_slice)
                weekly_data.append({"week": f"Week {len(weekly_data)+1}", "value": week_total})
                print(f"[DEBUG VIZ]     Week {len(weekly_data)}: {len(week_slice)} days, total={week_total:.2f}")
```

with:

```python
            if week_slice:
                week_value = _aggregate_week(week_slice, metric)
                weekly_data.append({"week": f"Week {len(weekly_data)+1}", "value": week_value})
                print(f"[DEBUG VIZ]     Week {len(weekly_data)}: {len(week_slice)} days, value={week_value:.4f}")
```

- [ ] **Step 5: Add the regression tests**

Add to `tests/unit/test_metrics_tools.py` (new class after `TestGenerateMetricsVisualization`):

```python
class TestWeeklyAggregation:
    """The weekly-RPI regression tests the phase doc's validation requires
    (discovered during kickoff: no such test previously existed)."""

    def test_aggregate_week_rpi_is_ratio_of_sums(self):
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import _aggregate_week

        week = [
            {"value": 0.01, "revenue": 10.0, "impressions": 1000, "dwell_time": 5.0},
            {"value": 0.1, "revenue": 50.0, "impressions": 500, "dwell_time": 5.0},
        ]
        result = _aggregate_week(week, "revenue_per_impression")
        assert result == compute_rpi(60.0, 1500) == 0.04
        assert result != sum(d["value"] for d in week)  # the old buggy sum (0.11)

    def test_aggregate_week_dwell_is_impressions_weighted(self):
        from app.tools.metrics_tools import _aggregate_week

        week = [
            {"value": 10.0, "revenue": 0, "impressions": 900, "dwell_time": 10.0},
            {"value": 2.0, "revenue": 0, "impressions": 100, "dwell_time": 2.0},
        ]
        assert _aggregate_week(week, "dwell_time") == 9.2

    def test_aggregate_week_additive_metrics_still_sum(self):
        from app.tools.metrics_tools import _aggregate_week

        week = [
            {"value": 100, "revenue": 0, "impressions": 100, "dwell_time": 0},
            {"value": 200, "revenue": 0, "impressions": 200, "dwell_time": 0},
        ]
        assert _aggregate_week(week, "impressions") == 300

    async def test_weekly_bar_chart_prompt_carries_ratio_of_sums(
        self, test_db, mock_storage_module
    ):
        """End-to-end: the prompt sent to the (mocked) image API contains the
        ratio-of-sums weekly RPI, not the summed daily ratios."""
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import generate_metrics_visualization

        rows = []
        for n in range(14, 7, -1):  # week 1 (older 7 days): unequal days
            rows.append({"metric_date": _days_ago(n), "impressions": 1000, "revenue": 10.0})
        for n in range(7, 0, -1):  # week 2
            rows.append({"metric_date": _days_ago(n), "impressions": 500, "revenue": 50.0})
        made = _make_campaign_with_metrics(rows)

        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            result = await generate_metrics_visualization(
                campaign_id=made["campaign_id"],
                chart_type="bar_chart",
                metric="revenue_per_impression",
                days=14,
            )
            assert result["status"] == "error"  # mocked API — expected

            call = mock_client.return_value.models.generate_content.call_args
            prompt = call.kwargs["contents"][0]

        week1_rpi = compute_rpi(70.0, 7000)   # 0.01
        week2_rpi = compute_rpi(350.0, 3500)  # 0.1
        assert f"${week1_rpi:.4f}" in prompt
        assert f"${week2_rpi:.4f}" in prompt
        # The buggy sums (0.07 and 0.70) must NOT appear as weekly values
        assert "$0.0700" not in prompt
        assert "$0.7000" not in prompt
```

- [ ] **Step 6: Run the full unit suite and the exit-criteria grep**

Run: `.venv/bin/pytest tests/unit/ -v -m "not slow"`
Expected: all pass.

Run: `grep -rnE "revenue[^,)]*/[^,)]*impressions" app/tools/ app/database/ --include="*.py"`
Expected: matches ONLY in `app/tools/metrics_shared.py` (the implementation) and the annotated ORDER-BY-only SQL line in `metrics_tools.py`'s `metric_column_map`. Any other match is an unmigrated site — STOP and migrate it before committing.

- [ ] **Step 7: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Fix weekly chart aggregation: ratio-of-sums RPI, weighted dwell"
```

---

## Verification & finish (lifecycle, not plan tasks)

- Full `make test` (unit + integration) green in the worktree venv.
- **Demo scenario:** `docs/demo-scenarios/fashion.md` Scenario F2, both scenes (F2.1 chart-with-defaults, F2.2 two-turn visualization), via `verifying-with-demo-scenarios` — the weekly chart is the user-visible behavior change.
- `requesting-code-review` on the whole branch (focus: exit criteria — no inline RPI division outside `metrics_shared.py`; the two intentional output changes are the weekly chart and the insights trend; `get_top_performing_ads` default behavior unchanged).
- `finishing-a-development-branch`: PR into `version_2`, owner-confirmed self-merge, STATUS/WORK_LOG finish.
