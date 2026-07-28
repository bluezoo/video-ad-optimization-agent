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
    BlueZooQuotaExceeded,
    LiveBlueZooAudienceDataSource,
    _build_sql,
    _classify_http_error,
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


@pytest.fixture
def live_env(monkeypatch):
    monkeypatch.setenv("BLUEZOO_BASE_URL", "https://stub.invalid/v2/dwh")
    monkeypatch.setenv("BLUEZOO_ACCESS_KEY", "stub-key")
    monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:87,102:433")
    monkeypatch.setattr("app.audience.live_bluezoo._RETRY_BACKOFF_SECONDS", 0)


class TestConstructorFailsClosed:
    def test_missing_base_url_and_key_named_exactly(self, monkeypatch):
        for var in ("BLUEZOO_BASE_URL", "BLUEZOO_ACCESS_KEY", "BLUEZOO_SENSOR_MAP"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(BlueZooConfigError) as excinfo:
            LiveBlueZooAudienceDataSource()
        assert "BLUEZOO_BASE_URL" in str(excinfo.value)
        assert "BLUEZOO_ACCESS_KEY" in str(excinfo.value)

    def test_missing_map_fails_closed(self, monkeypatch, live_env):
        monkeypatch.delenv("BLUEZOO_SENSOR_MAP")
        with pytest.raises(BlueZooConfigError, match="BLUEZOO_SENSOR_MAP"):
            LiveBlueZooAudienceDataSource()

    def test_base_url_has_no_default(self, monkeypatch, live_env):
        monkeypatch.delenv("BLUEZOO_BASE_URL")
        with pytest.raises(BlueZooConfigError, match="BLUEZOO_BASE_URL"):
            LiveBlueZooAudienceDataSource()

    def test_full_env_constructs(self, live_env):
        source = LiveBlueZooAudienceDataSource()
        assert isinstance(source, LiveBlueZooAudienceDataSource)


class TestClassifyHttpError:
    def test_quota_body_maps_to_quota_exceeded(self):
        exc = _classify_http_error(400, "fair use limit: data scanned this month ...")
        assert isinstance(exc, BlueZooQuotaExceeded)
        assert "raise" in str(exc)  # remediation: BlueZoo raises it on request

    def test_bad_token_maps_to_config_error_naming_the_pair(self):
        exc = _classify_http_error(403, '{"error": "BAD_TOKEN"}')
        assert isinstance(exc, BlueZooConfigError)
        assert "BLUEZOO_BASE_URL" in str(exc)  # cluster-scoped pair hint

    def test_other_4xx_is_generic_bluezoo_error(self):
        exc = _classify_http_error(400, "syntax error near WHERE")
        assert type(exc) is BlueZooError


class _FlakyOnce(LiveBlueZooAudienceDataSource):
    """First _call raises the given transient error; second succeeds."""

    def __init__(self, first_error):
        super().__init__()
        self._first_error = first_error
        self.calls = 0

    def _call(self, sql):
        self.calls += 1
        if self.calls == 1:
            raise self._first_error
        return []


class TestRetry:
    def test_transient_failure_retried_once_then_succeeds(self, live_env):
        from app.audience.live_bluezoo import _Retryable

        source = _FlakyOnce(_Retryable("HTTP 503"))
        assert source._query(
            "select timestamp from sensor_visits where timestamp >= '2026-07-20'"
        ) == []
        assert source.calls == 2

    def test_second_transient_failure_surfaces_typed_error(self, live_env):
        from app.audience.live_bluezoo import _Retryable

        class _AlwaysDown(LiveBlueZooAudienceDataSource):
            def _call(self, sql):
                raise _Retryable("HTTP 503")

        with pytest.raises(BlueZooError, match="after one retry"):
            _AlwaysDown()._query(
                "select timestamp from sensor_visits where timestamp >= '2026-07-20'"
            )

    def test_quota_is_never_retried(self, live_env):
        source = _FlakyOnce(BlueZooQuotaExceeded("allowance exhausted"))
        with pytest.raises(BlueZooQuotaExceeded):
            source._query(
                "select timestamp from sensor_visits where timestamp >= '2026-07-20'"
            )
        assert source.calls == 1

    def test_config_error_is_never_retried(self, live_env):
        source = _FlakyOnce(BlueZooConfigError("BAD_TOKEN"))
        with pytest.raises(BlueZooConfigError):
            source._query(
                "select timestamp from sensor_visits where timestamp >= '2026-07-20'"
            )
        assert source.calls == 1
