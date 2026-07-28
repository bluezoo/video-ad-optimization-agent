"""LiveBlueZooAudienceDataSource unit tests (Phase 11b) — NO network.

Everything here runs against pure helpers or a stubbed `_call`; the fast
tier must never touch BlueZoo (owner directive: `make test` stays
network-free — the live tier in tests/live/ carries the real reads).
"""

from datetime import date, datetime

import pytest

from app.audience.live_bluezoo import (
    _COLUMNS,
    BlueZooConfigError,
    BlueZooError,
    BlueZooQuotaExceeded,  # noqa: F401
    _build_sql,
    _coerce_valid,
    _guard_sql,
    _parse_sensor_map,
    _parse_utc_naive,
)
from app.config import BlueZooValidPolicy

D_FROM = date(2026, 7, 20)
D_TO = date(2026, 7, 21)


class TestParseSensorMap:
    def test_parses_pairs(self):
        assert _parse_sensor_map("101:87,102:433") == {101: 87, 102: 433}

    def test_tolerates_whitespace_and_trailing_comma(self):
        assert _parse_sensor_map(" 101:87 , 102:433 ,") == {101: 87, 102: 433}

    def test_empty_fails_closed(self):
        with pytest.raises(BlueZooConfigError, match="BLUEZOO_SENSOR_MAP"):
            _parse_sensor_map("")

    def test_malformed_entry_fails_closed(self):
        for bad in ("101", "101:", ":87", "101:eightyseven", "101=87"):
            with pytest.raises(BlueZooConfigError, match="screen_id:sensor_id"):
                _parse_sensor_map(bad)

    def test_duplicate_screen_rejected(self):
        with pytest.raises(BlueZooConfigError, match="twice"):
            _parse_sensor_map("101:87,101:433")

    def test_duplicate_sensor_rejected(self):
        with pytest.raises(BlueZooConfigError, match="one-to-one"):
            _parse_sensor_map("101:87,102:87")


class TestBuildSql:
    def test_names_exactly_the_seven_columns_never_star(self):
        sql = _build_sql([87, 433], D_FROM, D_TO, BlueZooValidPolicy.VALID_ONLY)
        assert "*" not in sql
        assert ", ".join(_COLUMNS) in sql
        assert _COLUMNS == (
            "timestamp",
            "sensor_id",
            "incoming_inner_count",
            "outgoing_inner_count",
            "incoming_outer_count",
            "outgoing_outer_count",
            "valid",
        )

    def test_half_open_utc_day_window(self):
        sql = _build_sql([87], D_FROM, D_TO, BlueZooValidPolicy.VALID_ONLY)
        assert "timestamp >= '2026-07-20'" in sql
        assert "timestamp < '2026-07-22'" in sql  # date_to inclusive -> +1 day exclusive

    def test_valid_only_appends_rule_r_filter(self):
        sql = _build_sql([87], D_FROM, D_TO, BlueZooValidPolicy.VALID_ONLY)
        assert sql.endswith(" and valid")

    def test_include_all_has_no_valid_filter(self):
        sql = _build_sql([87], D_FROM, D_TO, BlueZooValidPolicy.INCLUDE_ALL)
        assert " and valid" not in sql

    def test_sensor_ids_sorted_into_in_clause(self):
        sql = _build_sql([433, 87], D_FROM, D_TO, BlueZooValidPolicy.INCLUDE_ALL)
        assert "sensor_id in (87, 433)" in sql

    def test_passes_its_own_guard(self):
        _guard_sql(_build_sql([87], D_FROM, D_TO, BlueZooValidPolicy.VALID_ONLY))


class TestGuardSql:
    def test_rejects_non_select(self):
        with pytest.raises(BlueZooError, match="SELECT"):
            _guard_sql("delete from sensor_visits where timestamp > '2026-01-01'")

    def test_rejects_missing_time_constraint(self):
        with pytest.raises(BlueZooError, match="constrain"):
            _guard_sql("select sensor_id from sensor_visits")


class TestParseUtcNaive:
    def test_z_suffix_becomes_naive_utc(self):
        assert _parse_utc_naive("2026-07-20T14:45:00Z") == datetime(2026, 7, 20, 14, 45)

    def test_offset_is_converted_then_stripped(self):
        assert _parse_utc_naive("2026-07-20T10:45:00-04:00") == datetime(2026, 7, 20, 14, 45)

    def test_naive_passes_through(self):
        assert _parse_utc_naive("2026-07-20 14:45:00") == datetime(2026, 7, 20, 14, 45)


class TestCoerceValid:
    def test_bools_pass_through(self):
        assert _coerce_valid(True) is True
        assert _coerce_valid(False) is False

    def test_strings_parse_case_insensitively(self):
        assert _coerce_valid("true") is True
        assert _coerce_valid("True") is True
        assert _coerce_valid("false") is False  # bool("false") would be True — the bug this exists for
