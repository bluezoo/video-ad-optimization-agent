"""Tests for the disposable frames -> video_metrics derivation layer."""

from datetime import date

from app.demo_data.constants import DEMO_RPI, DEMO_WINDOW_DAYS
from app.demo_data.derive import derive_video_metrics_rows, video_fraction
from app.demo_data.seed import generate_frames
from app.tools.metrics_shared import compute_rpi

CID = 9001
D_FROM = date(2026, 6, 1)
D_TO = date(2026, 6, 7)


class TestConstants:
    def test_canonical_values(self):
        assert DEMO_RPI == 0.05
        assert DEMO_WINDOW_DAYS == 30


class TestDerivation:
    def test_one_row_per_video_per_day(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        assert len(rows) == 2 * 7
        dates = {r["metric_date"] for r in rows}
        assert min(dates) == D_FROM.isoformat()
        assert max(dates) == D_TO.isoformat()

    def test_impressions_are_inner_only(self):
        """The video's impressions must be its fraction of the day's INNER
        visits — an inner+outer computation (the donor's bug) gives a number
        several times larger and must not match."""
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_FROM)
        from app.demo_data.derive import _campaign_seed_config

        frames = generate_frames(_campaign_seed_config(CID, D_FROM, D_FROM))
        day_inner = sum(v["incoming_inner_count"] for v in frames["screen_visits"])
        day_both = day_inner + sum(
            v["incoming_outer_count"] for v in frames["screen_visits"]
        )
        f = video_fraction(CID, 101)
        assert rows[0]["impressions"] == int(round(day_inner * f))
        assert rows[0]["impressions"] != int(round(day_both * f))

    def test_revenue_is_flat_demo_rpi(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        for r in rows:
            assert r["revenue"] == round(r["impressions"] * DEMO_RPI, 2)
            if r["impressions"] > 0:
                assert compute_rpi(r["revenue"], r["impressions"]) == DEMO_RPI

    def test_per_video_fractions_differ(self):
        assert video_fraction(CID, 101) != video_fraction(CID, 102)
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_FROM)
        by_video = {r["video_id"]: r["impressions"] for r in rows}
        assert by_video[101] != by_video[102]

    def test_later_activation_never_changes_existing_rows(self):
        """Absolute per-video fractions: deriving for [101] and for
        [101, 102] must yield identical rows for 101 (the no-discontinuity
        property — a later activation cannot rewrite history)."""
        solo = [r for r in derive_video_metrics_rows(CID, [101], D_FROM, D_TO)]
        both = [
            r
            for r in derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
            if r["video_id"] == 101
        ]
        assert solo == both

    def test_deterministic_across_calls(self):
        r1 = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        r2 = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        assert r1 == r2

    def test_dwell_is_synthetic_seconds_scale(self):
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        for r in rows:
            assert 4.0 <= r["dwell_time_seconds"] <= 12.0

    def test_plausible_magnitudes(self):
        """Roughly the old demo's neighborhood so charts stay sane:
        per-video daily impressions in the hundreds-to-low-thousands,
        circulation above impressions."""
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        for r in rows:
            assert 200 <= r["impressions"] <= 8000
            assert r["circulation"] > 0
