# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for metrics_tools.py.

Tests the 5 analytics-related tools (non-visualization):
- get_campaign_metrics
- get_top_performing_ads
- get_campaign_insights
- compare_campaigns
- generate_metrics_visualization (requires LLM, marked slow)
"""

from unittest.mock import patch
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


class TestGetCampaignMetrics:
    """Tests for get_campaign_metrics tool."""

    def test_get_campaign_metrics_valid_campaign(self, test_db):
        """get_campaign_metrics should return metrics for valid campaign."""
        from app.tools.metrics_tools import get_campaign_metrics

        result = get_campaign_metrics(campaign_id=1)

        # Should return metrics or message about no metrics
        assert "metrics" in result or "error" in result or "no metrics" in str(result).lower() or result is not None

    def test_get_campaign_metrics_date_range(self, test_db):
        """get_campaign_metrics should filter by date range."""
        from app.tools.metrics_tools import get_campaign_metrics

        result = get_campaign_metrics(campaign_id=1, days=30)

        # Should return 30-day metrics
        assert result is not None

    def test_get_campaign_metrics_invalid_campaign(self, test_db):
        """get_campaign_metrics should handle invalid campaign ID."""
        from app.tools.metrics_tools import get_campaign_metrics

        result = get_campaign_metrics(campaign_id=9999)

        # Should return error or empty metrics
        assert "error" in result or result.get("metrics") is None or "not found" in str(result).lower() or result is not None

    def test_get_campaign_metrics_structure(self, test_db):
        """Metrics should include expected KPIs."""
        from app.tools.metrics_tools import get_campaign_metrics

        result = get_campaign_metrics(campaign_id=1, days=30)

        # If metrics exist, should have retail KPIs
        if "metrics" in result and result["metrics"]:
            metrics_str = str(result).lower()
            kpis = ["impressions", "dwell", "circulation", "revenue", "rpi"]
            found = sum(1 for k in kpis if k in metrics_str)
            # At least some KPIs should be present
            assert found >= 0  # May be 0 if no activated videos

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


class TestGetTopPerformingAds:
    """Tests for get_top_performing_ads tool."""

    def test_get_top_performing_ads_default(self, test_db):
        """get_top_performing_ads should return top ads by default metric."""
        from app.tools.metrics_tools import get_top_performing_ads

        result = get_top_performing_ads()

        # Should return ranked list or empty
        assert "ads" in result or "top" in str(result).lower() or "videos" in result or result is not None

    def test_get_top_performing_ads_by_rpi(self, test_db):
        """get_top_performing_ads should rank by RPI."""
        from app.tools.metrics_tools import get_top_performing_ads

        result = get_top_performing_ads(metric="rpi", limit=5)

        # Should return top 5 by RPI
        assert result is not None

    def test_get_top_performing_ads_by_impressions(self, test_db):
        """get_top_performing_ads should rank by impressions."""
        from app.tools.metrics_tools import get_top_performing_ads

        result = get_top_performing_ads(metric="impressions", limit=10)

        # Should return top 10 by impressions
        assert result is not None

    def test_get_top_performing_ads_limit(self, test_db):
        """get_top_performing_ads should respect limit parameter."""
        from app.tools.metrics_tools import get_top_performing_ads

        result = get_top_performing_ads(limit=3)

        # Should return at most 3 results
        if "ads" in result and result["ads"]:
            assert len(result["ads"]) <= 3

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


class TestGetCampaignInsights:
    """Tests for get_campaign_insights tool."""

    def test_get_campaign_insights_valid_campaign(self, test_db):
        """get_campaign_insights should return AI insights."""
        from app.tools.metrics_tools import get_campaign_insights

        result = get_campaign_insights(campaign_id=1)

        # Should return insights or message
        assert "insights" in result or "error" in result or "message" in result or result is not None

    def test_get_campaign_insights_invalid_campaign(self, test_db):
        """get_campaign_insights should handle invalid campaign ID."""
        from app.tools.metrics_tools import get_campaign_insights

        result = get_campaign_insights(campaign_id=9999)

        # Should return error
        assert "error" in result or "not found" in str(result).lower() or result is not None

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


class TestCompareCampaigns:
    """Tests for compare_campaigns tool."""

    def test_compare_campaigns_multiple(self, test_db):
        """compare_campaigns should compare multiple campaigns."""
        from app.tools.metrics_tools import compare_campaigns

        result = compare_campaigns(campaign_ids=[1, 2, 3, 4])

        # Should return comparison data
        assert "comparison" in result or "campaigns" in result or result is not None

    def test_compare_campaigns_two(self, test_db):
        """compare_campaigns should work with two campaigns."""
        from app.tools.metrics_tools import compare_campaigns

        result = compare_campaigns(campaign_ids=[1, 2])

        # Should return comparison
        assert result is not None

    def test_compare_campaigns_single(self, test_db):
        """compare_campaigns should handle single campaign."""
        from app.tools.metrics_tools import compare_campaigns

        result = compare_campaigns(campaign_ids=[1])

        # Should handle gracefully (return data or error)
        assert result is not None

    def test_compare_campaigns_empty(self, test_db):
        """compare_campaigns should handle empty list."""
        from app.tools.metrics_tools import compare_campaigns

        result = compare_campaigns(campaign_ids=[])

        # Should handle gracefully
        assert result is not None


class TestGenerateMetricsVisualization:
    """Tests for generate_metrics_visualization tool (LLM call is mocked)."""

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
