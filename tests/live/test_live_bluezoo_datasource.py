"""Live-tier BlueZoo conformer test (Phase 11b) — REAL reads against MO_92.

Byte budget per run: two queries x ~8 KB (2 sensors x 1 day x 41 B/row x
96 rows) ~= 16 KB, against a 500 GB/sensor-location monthly allowance.
Flakiness watchlist: sensors 77/80 are currently-reporting MO_92 sensors
(evidence: tests/unit/data/bluezoo_sensor_visits_sample.md, top valid-row
producers with full 96-slot/day coverage 2026-07-19..2026-07-26); if both go
dark the non-empty assertions fail — swap ids per SETUP_INSTRUCTIONS.md's
live-tier section.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import config
from app.audience.live_bluezoo import LiveBlueZooAudienceDataSource

pytestmark = pytest.mark.live

# Yesterday (UTC) — a complete day with data for reporting sensors.
_DAY = datetime.now(UTC).date() - timedelta(days=1)


@pytest.fixture(autouse=True)
def _sensor_map(monkeypatch):
    monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:77,102:80")


class TestLiveMO92:
    def test_valid_only_default_read(self):
        out = LiveBlueZooAudienceDataSource().get_visit_intervals(
            screen_ids=[101, 102], date_from=_DAY, date_to=_DAY
        )
        assert out, "expected rows for currently-reporting MO_92 sensors"
        assert all(iv.valid for iv in out)  # Rule R: SQL-side `and valid`
        assert all(iv.timestamp.tzinfo is None for iv in out)
        assert all(
            iv.timestamp.minute % 15 == 0 and iv.timestamp.second == 0 for iv in out
        )
        assert {iv.screen_id for iv in out} <= {101, 102}
        assert all(iv.average_visitors_inner is None for iv in out)

    def test_include_all_is_superset_of_valid_only(self, monkeypatch):
        source = LiveBlueZooAudienceDataSource()
        n_valid = len(
            source.get_visit_intervals(screen_ids=[101], date_from=_DAY, date_to=_DAY)
        )
        monkeypatch.setattr(
            config, "BLUEZOO_VALID_POLICY", config.BlueZooValidPolicy.INCLUDE_ALL
        )
        n_all = len(
            source.get_visit_intervals(screen_ids=[101], date_from=_DAY, date_to=_DAY)
        )
        assert n_all >= n_valid  # the policy knob really changes the query
