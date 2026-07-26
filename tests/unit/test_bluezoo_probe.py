"""Unit tests for the BlueZoo probe's pure helpers (no network).

The probe's value is that it works against ANY BlueZoo tenant, so the things
worth pinning are the tenant-variable behaviors: the undocumented mandatory
time filter, per-table time-column disagreement, table entitlements differing
per account, and a missing key failing loudly instead of silently.
"""

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bluezoo_probe.py"
_spec = importlib.util.spec_from_file_location("bluezoo_probe", _MODULE_PATH)
bluezoo_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bluezoo_probe)

BlueZooError = bluezoo_probe.BlueZooError
BlueZooProbe = bluezoo_probe.BlueZooProbe


class FakeProbe(BlueZooProbe):
    """Probe with the HTTP layer replaced by canned responses."""

    def __init__(self, tables, schemas, counts=None):
        super().__init__(access_key="fake-key")
        self._tables = tables
        self._schemas = schemas
        self._counts = counts or {}
        self.queries = []

    def list_tables(self):
        return sorted(self._tables)

    def describe(self, table):
        return self._schemas[table]

    def query(self, sql):
        super_check = BlueZooProbe.query
        # Reuse the real guard, then answer from canned counts.
        lowered = sql.lower()
        if not any(c in lowered for c in bluezoo_probe.TIME_CONSTRAINT_COLUMNS):
            raise BlueZooError(f"no time constraint: {sql}")
        assert super_check  # keep the reference meaningful for readers
        self.queries.append(sql)
        table = sql.split(" from ")[1].split(" ")[0]
        return [{"n": self._counts.get(table, 0)}]


def _cols(*names):
    return [{"column_name": n, "data_type": "INT64"} for n in names]


class TestMissingKey:
    def test_empty_key_raises_actionable_error(self):
        with pytest.raises(BlueZooError, match="AccessKey"):
            BlueZooProbe(access_key="")


class TestTimeConstraintGuard:
    """BlueZoo rejects any query lacking a date_start/date_end/timestamp
    filter — undocumented, and their own published example would fail."""

    def test_query_without_time_constraint_is_refused(self):
        probe = BlueZooProbe(access_key="fake-key")
        with pytest.raises(BlueZooError, match="time constraint|constrain"):
            probe.query("select * from sensor_visitors limit 1")

    @pytest.mark.parametrize("column", ["timestamp", "date_start", "date_end", "date"])
    def test_each_accepted_time_column_passes_the_guard(self, column, monkeypatch):
        probe = BlueZooProbe(access_key="fake-key")
        monkeypatch.setattr(probe, "_call", lambda *a, **k: [{"n": 1}])
        assert probe.query(f"select count(*) as n from t where {column} >= '2026-01-01'")


class TestTimeColumnSelection:
    """Tables disagree on which column is filterable."""

    def test_sensor_tables_use_timestamp(self):
        assert bluezoo_probe.time_column_for(_cols("sensor_id", "timestamp")) == "timestamp"

    def test_group_uv_daily_uses_date_not_timestamp(self):
        assert bluezoo_probe.time_column_for(_cols("group_id", "date")) == "date"

    def test_group_convert_uses_date_start(self):
        assert bluezoo_probe.time_column_for(_cols("campaign_id", "date_start")) == "date_start"

    def test_table_with_no_time_column_returns_none(self):
        assert bluezoo_probe.time_column_for(_cols("group_id", "sensor_id")) is None


class TestTenantVariability:
    """Table availability is a per-account entitlement, so the scan must
    degrade rather than fail when a tenant lacks an optional table."""

    def test_missing_optional_table_is_skipped_not_an_error(self):
        probe = FakeProbe(
            tables=["sensor_visits"],
            schemas={"sensor_visits": _cols("sensor_id", "timestamp")},
            counts={"sensor_visits": 42},
        )
        result = bluezoo_probe.scan(
            probe, count_tables=("sensor_visits", "sensor_visitors_per_minute")
        )
        assert result["row_counts"] == {"sensor_visits": 42}
        assert "sensor_visitors_per_minute" not in result["row_counts"]

    def test_scan_records_entitlements_and_schemas(self):
        probe = FakeProbe(
            tables=["sensor_visits", "group_sensor_history"],
            schemas={
                "sensor_visits": _cols("sensor_id", "timestamp"),
                "group_sensor_history": _cols("group_id", "sensor_id", "timestamp"),
            },
        )
        result = bluezoo_probe.scan(probe, count_tables=("sensor_visits",))
        assert result["table_count"] == 2
        assert set(result["schemas"]) == {"sensor_visits", "group_sensor_history"}
        assert result["schema_errors"] == {}

    def test_zero_rows_is_a_valid_answer_not_a_failure(self):
        probe = FakeProbe(
            tables=["sensor_visits"],
            schemas={"sensor_visits": _cols("sensor_id", "timestamp")},
            counts={"sensor_visits": 0},
        )
        result = bluezoo_probe.scan(probe, count_tables=("sensor_visits",))
        assert result["row_counts"]["sensor_visits"] == 0

    def test_counted_query_carries_the_time_filter(self):
        probe = FakeProbe(
            tables=["sensor_visits"], schemas={"sensor_visits": _cols("sensor_id", "timestamp")}
        )
        bluezoo_probe.scan(probe, count_tables=("sensor_visits",))
        assert "where timestamp >=" in probe.queries[0]


class TestRendering:
    def test_markdown_digest_includes_counts_and_columns(self):
        probe = FakeProbe(
            tables=["sensor_visits"],
            schemas={"sensor_visits": _cols("sensor_id", "timestamp")},
            counts={"sensor_visits": 7},
        )
        markdown = bluezoo_probe.render_markdown(
            bluezoo_probe.scan(probe, count_tables=("sensor_visits",))
        )
        assert "`sensor_visits`" in markdown
        assert "| 7 |" in markdown
        assert "`timestamp`" in markdown

    def test_scan_never_contains_the_access_key(self):
        probe = FakeProbe(
            tables=["sensor_visits"], schemas={"sensor_visits": _cols("sensor_id", "timestamp")}
        )
        payload = bluezoo_probe.render_markdown(
            bluezoo_probe.scan(probe, count_tables=("sensor_visits",))
        )
        assert "fake-key" not in payload
