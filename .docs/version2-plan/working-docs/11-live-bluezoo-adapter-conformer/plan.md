# Workstream 11b: Live BlueZoo Adapter (Conformer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register one class — `LiveBlueZooAudienceDataSource` — under `AppMode.CONNECTED` in the 11a seam, so `APP_MODE=connected` produces real MO_92 impressions through the existing attribution join.

**Architecture:** One new module `app/audience/live_bluezoo.py` containing the class plus private helpers (thin urllib transport with client-side read-only guards, typed errors, sensor-map/SQL builders). One fixed parameterized SELECT against `sensor_visits` only; the DTO's six unconsumed occupancy fields become optional. Rule R ships as a logged, configurable `app/config.py` knob, never a silent constant.

**Tech Stack:** Python stdlib only (urllib, json, datetime) — no new dependencies. Pydantic DTO (existing). Pytest fast tier (stubbed transport) + live tier (`tests/live/`, marked `live`).

## Global Constraints

- **Read-only against BlueZoo, ever.** SELECT-only + mandatory-time-constraint guards refuse client-side before anything leaves the process (probe pattern, `scripts/bluezoo_probe.py:159-183`).
- **`make test` stays network-free** (owner directive). All network tests live in `tests/live/` with `pytestmark = pytest.mark.live`. The fast tier's live-source tests use a stubbed `_call` only.
- **Rule R is policy, not a constant:** `BLUEZOO_VALID_POLICY` env knob, values `valid-only` (default) | `include-all`; every live read logs `policy=<value> ... rows=<n>`.
- **`BLUEZOO_BASE_URL` has NO default** — cluster-scoped, travels with the AccessKey as a `{base_url, access_key}` pair.
- **Named columns always, never `select *`** — exactly: `timestamp, sensor_id, incoming_inner_count, outgoing_inner_count, incoming_outer_count, outgoing_outer_count, valid` (~41 B/row).
- **One class, one method.** No registry changes beyond the one `_BUILTIN_SOURCES` entry, no pagination, no query builder, no `list_tables` capability framework, no caching layer, no `sensor_pulses`, no BlueZoo `campaign_id`.
- **Timestamps normalize to NAIVE UTC** — `timestamp` is UTC (semantics findings); the join keys visits by `(screen_id, timestamp)` against naive play slots (`app/demo_data/seed.py:89-92`), so a tz-aware datetime silently matches nothing.
- **Redaction:** the checked-in fixture holds ids/timestamps/counts/valid only — no venue/operator names, never a key. Numeric sensor ids are acceptable per merged-workstream precedent.
- **No AI-attribution trailers** in commits or PR bodies.
- **Lint:** `make lint` clean after every task.

---

### Task 1: DTO — occupancy fields become optional, divergence documented in the model

**Files:**
- Modify: `app/models/attribution.py:43-61`
- Test: `tests/unit/test_attribution_models.py`

**Interfaces:**
- Produces: `BlueZooVisitInterval` constructible WITHOUT the six occupancy fields (they default to `None`); all existing call sites (which pass them) unchanged. Tasks 5–7 construct it flow-fields-only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_attribution_models.py`:

```python
class TestOccupancyFieldsOptional:
    """Phase 11b: occupancy (sensor_visitors) fields are demo-populated only —
    the live conformer queries sensor_visits alone and leaves them None."""

    FLOW_ONLY = {
        "timestamp": datetime(2026, 7, 20, 14, 45),
        "screen_id": 101,
        "incoming_inner_count": 3.2,
        "outgoing_inner_count": 2.9,
        "incoming_outer_count": 8.1,
        "outgoing_outer_count": 7.7,
        "valid": True,
    }

    def test_constructible_without_occupancy_fields(self):
        iv = BlueZooVisitInterval(**self.FLOW_ONLY)
        assert iv.minimum_visitors_inner is None
        assert iv.maximum_visitors_inner is None
        assert iv.average_visitors_inner is None
        assert iv.minimum_visitors_outer is None
        assert iv.maximum_visitors_outer is None
        assert iv.average_visitors_outer is None

    def test_occupancy_fields_still_accept_floats(self):
        iv = BlueZooVisitInterval(**self.FLOW_ONLY, average_visitors_inner=4.5)
        assert iv.average_visitors_inner == 4.5

    def test_extra_forbid_still_enforced(self):
        with pytest.raises(ValidationError):
            BlueZooVisitInterval(**self.FLOW_ONLY, not_a_field=1)
```

Add to that file's imports if missing: `from datetime import datetime`, `import pytest`, `from pydantic import ValidationError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_attribution_models.py -v`
Expected: `test_constructible_without_occupancy_fields` FAILS with pydantic `ValidationError` (6 missing fields).

- [ ] **Step 3: Make the DTO change**

In `app/models/attribution.py`, replace lines 55–60 (the six `float` fields) with:

```python
    # Occupancy fields (BlueZoo `sensor_visitors` columns, NOT `sensor_visits`)
    # — DEMO-POPULATED ONLY. The live conformer (Phase 11b) queries
    # sensor_visits alone and leaves these None: populating them would cost a
    # second table scan against BlueZoo's metered bytes-scanned allowance, for
    # values nothing in this app reads (the attribution join consumes only
    # incoming_inner_count and outgoing_outer_count). If a real metric ever
    # needs occupancy, add the sensor_visitors query then — do NOT assume
    # these are live-populated. See docs/METRICS.md (circulation entry).
    minimum_visitors_inner: float | None = None
    maximum_visitors_inner: float | None = None
    average_visitors_inner: float | None = None
    minimum_visitors_outer: float | None = None
    maximum_visitors_outer: float | None = None
    average_visitors_outer: float | None = None
```

Also update the module docstring's parenthetical `(replan amendment: scoped to sensor_visits fields only; extra="forbid" enforces it)` to:

```
(replan amendment: scoped to sensor_visits fields only — the six occupancy
fields below are acknowledged sensor_visitors drift, kept optional and
demo-only rather than removed; extra="forbid" still rejects anything new)
```

- [ ] **Step 4: Run tests to verify they pass, and nothing regressed**

Run: `pytest tests/unit/test_attribution_models.py tests/unit/test_demo_seed.py tests/unit/test_audience_datasource.py -v` then `make test-unit`
Expected: all PASS (the synthetic path still supplies values — byte-identical golden tests stay green).

- [ ] **Step 5: Commit**

```bash
git add app/models/attribution.py tests/unit/test_attribution_models.py
git commit -m "feat(11b): occupancy fields on BlueZooVisitInterval optional, demo-only (documented in model)"
```

---

### Task 2: Config knob `BLUEZOO_VALID_POLICY`

**Files:**
- Modify: `app/config.py` (insert after the `DEMO_DATASET` block, ~line 58)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `config.BlueZooValidPolicy` StrEnum (`VALID_ONLY = "valid-only"`, `INCLUDE_ALL = "include-all"`) and module attribute `config.BLUEZOO_VALID_POLICY` (default `VALID_ONLY`). Task 5 reads `config.BLUEZOO_VALID_POLICY` as an attribute at call time (tests monkeypatch it).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py` (same reload pattern as `TestAppMode`, lines 67–104):

```python
class TestBlueZooValidPolicy:
    """Phase 11b: Rule R as explicit, configurable policy — never baked in."""

    def test_unset_defaults_to_valid_only(self, monkeypatch):
        monkeypatch.delenv("BLUEZOO_VALID_POLICY", raising=False)
        cfg = importlib.reload(config_module)
        assert cfg.BLUEZOO_VALID_POLICY is cfg.BlueZooValidPolicy.VALID_ONLY

    def test_include_all_is_valid(self, monkeypatch):
        monkeypatch.setenv("BLUEZOO_VALID_POLICY", "include-all")
        cfg = importlib.reload(config_module)
        assert cfg.BLUEZOO_VALID_POLICY is cfg.BlueZooValidPolicy.INCLUDE_ALL

    def test_value_is_normalized(self, monkeypatch):
        monkeypatch.setenv("BLUEZOO_VALID_POLICY", "  Valid-Only ")
        cfg = importlib.reload(config_module)
        assert cfg.BLUEZOO_VALID_POLICY is cfg.BlueZooValidPolicy.VALID_ONLY

    def test_empty_value_means_unset(self, monkeypatch):
        monkeypatch.setenv("BLUEZOO_VALID_POLICY", "")
        cfg = importlib.reload(config_module)
        assert cfg.BLUEZOO_VALID_POLICY is cfg.BlueZooValidPolicy.VALID_ONLY

    def test_invalid_value_raises_valueerror_at_load(self, monkeypatch):
        monkeypatch.setenv("BLUEZOO_VALID_POLICY", "garbage")
        with pytest.raises(ValueError, match="BLUEZOO_VALID_POLICY"):
            importlib.reload(config_module)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py::TestBlueZooValidPolicy -v`
Expected: FAIL with `AttributeError: ... has no attribute 'BLUEZOO_VALID_POLICY'`.

- [ ] **Step 3: Implement the knob**

Insert into `app/config.py` immediately after the `DEMO_DATASET` block:

```python
# BlueZoo `valid` policy (Phase 11b). Rule R — count only rows BlueZoo marked
# `valid` (a one-way commissioning-acceptance flag; see docs/METRICS.md) — is
# OUR recommendation, NOT yet confirmed by BlueZoo. It therefore ships as the
# DEFAULT of this explicit, configurable knob, never as a silent constant:
# flipping it requires zero code, and the live conformer logs the active
# policy + row count on every read. include-all = no filter, for
# reconciliation/debugging or the day BlueZoo answers differently. Consumed
# only by app/audience/live_bluezoo.py; demo mode ignores it.
class BlueZooValidPolicy(StrEnum):
    VALID_ONLY = "valid-only"
    INCLUDE_ALL = "include-all"


_raw_bluezoo_valid_policy = (os.environ.get("BLUEZOO_VALID_POLICY") or "").strip().lower()
try:
    BLUEZOO_VALID_POLICY = (
        BlueZooValidPolicy(_raw_bluezoo_valid_policy)
        if _raw_bluezoo_valid_policy
        else BlueZooValidPolicy.VALID_ONLY
    )
except ValueError:
    raise ValueError(
        f"Invalid BLUEZOO_VALID_POLICY={_raw_bluezoo_valid_policy!r}. Allowed values: "
        f"{', '.join(p.value for p in BlueZooValidPolicy)}; unset defaults to 'valid-only'."
    ) from None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: all PASS (including the pre-existing classes — the reload pattern is shared).

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/unit/test_config.py
git commit -m "feat(11b): BLUEZOO_VALID_POLICY config knob (Rule R as explicit policy, default valid-only)"
```

---

### Task 3: `live_bluezoo.py` foundations — errors, sensor map, SQL builder, guards

**Files:**
- Create: `app/audience/live_bluezoo.py`
- Test: `tests/unit/test_live_bluezoo_datasource.py` (new)

**Interfaces:**
- Produces (module-level, consumed by Tasks 4–7):
  - `class BlueZooError(RuntimeError)`; `class BlueZooConfigError(BlueZooError)`; `class BlueZooQuotaExceeded(BlueZooError)`
  - `_parse_sensor_map(raw: str) -> dict[int, int]` (screen→sensor; fail-closed, one-to-one)
  - `_build_sql(sensor_ids: list[int], date_from: date, date_to: date, policy: BlueZooValidPolicy) -> str`
  - `_guard_sql(sql: str) -> None`
  - `_parse_utc_naive(value) -> datetime`; `_coerce_valid(value) -> bool`
  - `_COLUMNS` tuple (the seven named columns, in order)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_live_bluezoo_datasource.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'app.audience.live_bluezoo'`.

- [ ] **Step 3: Create the module with the helpers**

Create `app/audience/live_bluezoo.py`:

```python
"""LiveBlueZooAudienceDataSource — the connected-mode conformer (Phase 11b).

ONE class implementing the seam's ONE method against BlueZoo's REST Data
Warehouse (`run_query`), plus private helpers. Deliberately NOT a framework:
one fixed parameterized SELECT against `sensor_visits`, no pagination, no
query builder, no capability probing (scope guard: the pre-kickoff decisions
at the foot of .docs/version2-plan/11-live-bluezoo-adapter.md).

Conforming rules (findings: bluezoo-live-verification Part 5 +
bluezoo-semantics-resolution):
- Read-only: SELECT-only + mandatory time predicate, both refused
  client-side before anything leaves the process.
- Named columns always — bytes scanned are metered per month; `select *`
  is the expensive mistake.
- Rule R (count only `valid` rows) is config policy (BLUEZOO_VALID_POLICY),
  logged with the row count on every read, never baked in — it is OUR
  recommendation, not yet confirmed by BlueZoo.
- `timestamp` is UTC (proven empirically); rows normalize to NAIVE UTC to
  match the play-slot convention (seed.py's UTC day buckets) — a tz-aware
  datetime would silently match nothing in the attribution join.
- Quota exhaustion is a named, non-retryable operational state; retry makes
  it worse. Bad credentials and wrong-cluster hosts get their own faces too.
- Zero rows is a legitimate result, never an error (fail-closed applies to
  configuration, not to data).
- BLUEZOO_BASE_URL has NO default: the URL is cluster-scoped and travels
  with the AccessKey as a {base_url, access_key} pair — a wrong default
  would fail looking like a bad credential.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta

from .. import config
from ..models.attribution import BlueZooVisitInterval
from .datasource import AudienceDataSource

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60  # probe-proven against MO_92's 5.1M-row tables
_RETRY_BACKOFF_SECONDS = 2.0  # tests monkeypatch to 0

# The one query's column list — named, never *, ~41 bytes/row.
_COLUMNS = (
    "timestamp",
    "sensor_id",
    "incoming_inner_count",
    "outgoing_inner_count",
    "incoming_outer_count",
    "outgoing_outer_count",
    "valid",
)

# BlueZoo rejects any run_query without a constraint on one of these columns
# (undocumented, enforced server-side — probe finding). Belt-and-braces here:
# refusing locally makes "read-only, time-bounded" a property of this module.
_TIME_CONSTRAINT_COLUMNS = ("timestamp", "date_start", "date_end", "date")


class BlueZooError(RuntimeError):
    """A BlueZoo Data Warehouse call failed or returned an unusable response."""


class BlueZooConfigError(BlueZooError):
    """Missing/invalid configuration, rejected credentials, or a wrong
    cluster host — connected mode fails closed with the specific cause."""


class BlueZooQuotaExceeded(BlueZooError):
    """Monthly bytes-scanned allowance exhausted. NON-retryable: every
    run_query fails until it resets or BlueZoo raises it (they do, on
    request — contact BlueZoo). Metadata and the Real-time API keep working."""


class _Retryable(BlueZooError):
    """Internal marker: transient transport failure (timeout / 5xx) worth
    exactly one retry. Never leaves this module."""


def _parse_sensor_map(raw: str) -> dict[int, int]:
    """Parse BLUEZOO_SENSOR_MAP: "101:87,102:433" -> {101: 87, 102: 433}.

    Fail-closed on anything malformed. One-to-one required (duplicate screen
    OR sensor ids rejected) so result rows map back unambiguously.
    """
    mapping: dict[int, int] = {}
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    if not entries:
        raise BlueZooConfigError(
            "BLUEZOO_SENSOR_MAP is empty or unset — connected mode needs at "
            "least one screen_id:sensor_id pair (e.g. '101:87,102:433'). "
            "See SETUP_INSTRUCTIONS.md (connected mode)."
        )
    for entry in entries:
        screen_raw, sep, sensor_raw = entry.partition(":")
        try:
            if not sep:
                raise ValueError
            screen_id, sensor_id = int(screen_raw), int(sensor_raw)
        except ValueError:
            raise BlueZooConfigError(
                f"BLUEZOO_SENSOR_MAP entry {entry!r} is not 'screen_id:sensor_id' "
                "with integer ids (e.g. '101:87')."
            ) from None
        if screen_id in mapping:
            raise BlueZooConfigError(f"BLUEZOO_SENSOR_MAP maps screen {screen_id} twice.")
        mapping[screen_id] = sensor_id
    if len(set(mapping.values())) != len(mapping):
        raise BlueZooConfigError(
            "BLUEZOO_SENSOR_MAP must be one-to-one: a sensor id appears for "
            "two screens, which would make result rows ambiguous."
        )
    return mapping


def _build_sql(
    sensor_ids: list[int],
    date_from: date,
    date_to: date,
    policy: config.BlueZooValidPolicy,
) -> str:
    """The one fixed SELECT. Half-open UTC window [date_from, date_to + 1 day)
    — `timestamp` is UTC and the interface's dates are inclusive UTC days.
    sensor_ids are ints validated at map parse, so interpolation is safe."""
    end_exclusive = date_to + timedelta(days=1)
    ids = ", ".join(str(s) for s in sorted(sensor_ids))
    sql = (
        f"select {', '.join(_COLUMNS)} from sensor_visits"
        f" where timestamp >= '{date_from.isoformat()}'"
        f" and timestamp < '{end_exclusive.isoformat()}'"
        f" and sensor_id in ({ids})"
    )
    if policy is config.BlueZooValidPolicy.VALID_ONLY:
        sql += " and valid"
    return sql


def _guard_sql(sql: str) -> None:
    """Client-side read-only + time-bound refusals, before any network I/O.

    Best-effort (scans the statement, doesn't parse the WHERE clause) — same
    trade-off as the probe: catches the realistic mistake and names the real
    cause instead of surfacing BlueZoo's message after a round trip.
    """
    lowered = sql.lower()
    if not lowered.lstrip().startswith("select"):
        raise BlueZooError(f"live conformer issues SELECT statements only: {sql}")
    if not any(column in lowered for column in _TIME_CONSTRAINT_COLUMNS):
        raise BlueZooError(
            "BlueZoo requires every query to constrain one of "
            f"{', '.join(_TIME_CONSTRAINT_COLUMNS)} in its WHERE clause: {sql}"
        )


def _parse_utc_naive(value) -> datetime:
    """Normalize a BlueZoo timestamp to NAIVE UTC.

    The attribution join indexes visits by (screen_id, timestamp) against
    play slots built as naive datetimes (seed.py, UTC-day convention); a
    tz-aware value here would silently match nothing.
    """
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _coerce_valid(value) -> bool:
    """BlueZoo may serialize BOOL as JSON bool or string; bool("false") is
    True, hence this exists."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)
```

(The class itself arrives in Tasks 4–5; this module compiles and the helper tests pass without it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py -v` then `make lint`
Expected: all PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add app/audience/live_bluezoo.py tests/unit/test_live_bluezoo_datasource.py
git commit -m "feat(11b): live_bluezoo foundations — typed errors, sensor map, guarded SQL builder"
```

---

### Task 4: Transport — `_call`, error classification, one-shot retry, constructor

**Files:**
- Modify: `app/audience/live_bluezoo.py` (append)
- Test: `tests/unit/test_live_bluezoo_datasource.py` (append)

**Interfaces:**
- Produces: `class LiveBlueZooAudienceDataSource(AudienceDataSource)` with `__init__()` (env-driven, fail-closed), `_call(sql) -> list[dict]` (the ONLY networked method — unit tests override it), `_query(sql) -> list[dict]` (guard + retry wrapper), and module fn `_classify_http_error(code, detail) -> BlueZooError`.
- Consumes: Task 3's helpers and exceptions.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_live_bluezoo_datasource.py`:

```python
from app.audience.live_bluezoo import (  # noqa: E402  (grouped with the top import in practice)
    LiveBlueZooAudienceDataSource,
    _classify_http_error,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py -v`
Expected: FAIL at import — `ImportError: cannot import name 'LiveBlueZooAudienceDataSource'`.

- [ ] **Step 3: Implement transport + constructor**

Append to `app/audience/live_bluezoo.py`:

```python
def _classify_http_error(code: int, detail: str) -> BlueZooError:
    """Map a non-retryable HTTP error body to the right exception.

    (5xx never reaches here — the transport wraps those in _Retryable.)
    """
    if "fair use limit" in detail or "data scanned" in detail:
        return BlueZooQuotaExceeded(
            "BlueZoo monthly bytes-scanned allowance exhausted — every "
            "run_query fails until it resets or BlueZoo raises it (they "
            "raise it on request: contact BlueZoo; metadata and the "
            f"Real-time API keep working). Server said: {detail}"
        )
    if "BAD_TOKEN" in detail:
        return BlueZooConfigError(
            "BlueZoo rejected the AccessKey (BAD_TOKEN). Keys are "
            "CLUSTER-scoped: check that BLUEZOO_ACCESS_KEY and "
            "BLUEZOO_BASE_URL are the matching {base_url, access_key} pair "
            f"for this tenant's cluster. Server said: {detail}"
        )
    return BlueZooError(f"run_query: HTTP {code} {detail}")


class LiveBlueZooAudienceDataSource(AudienceDataSource):
    """Real MO_92-shaped audience data through the 11a seam (REST-first)."""

    def __init__(self) -> None:
        self._base_url = os.environ.get("BLUEZOO_BASE_URL", "").strip().rstrip("/")
        self._access_key = os.environ.get("BLUEZOO_ACCESS_KEY", "").strip()
        missing = [
            name
            for name, value in (
                ("BLUEZOO_BASE_URL", self._base_url),
                ("BLUEZOO_ACCESS_KEY", self._access_key),
            )
            if not value
        ]
        if missing:
            raise BlueZooConfigError(
                f"APP_MODE=connected requires BLUEZOO_BASE_URL and "
                f"BLUEZOO_ACCESS_KEY (missing: {', '.join(missing)}). Set them "
                "in app/.env locally, or inject both from Secret Manager at "
                "deploy time — they are a cluster-scoped pair; BLUEZOO_BASE_URL "
                "deliberately has no default. See SETUP_INSTRUCTIONS.md "
                "(connected mode)."
            )
        self._sensor_by_screen = _parse_sensor_map(os.environ.get("BLUEZOO_SENSOR_MAP", ""))
        self._screen_by_sensor = {s: c for c, s in self._sensor_by_screen.items()}

    def _call(self, sql: str) -> list[dict]:
        """POST one already-guarded SELECT to run_query; JSON rows back.

        The ONLY method that touches the network — unit tests override it,
        keeping the fast tier network-free by construction.
        """
        request = urllib.request.Request(f"{self._base_url}/run_query", data=sql.encode())
        request.add_header("Authorization", f"AccessKey {self._access_key}")
        request.add_header("Content-Type", "text/plain")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            if exc.code >= 500:
                raise _Retryable(f"run_query: HTTP {exc.code} {detail}") from exc
            raise _classify_http_error(exc.code, detail) from exc
        except urllib.error.URLError as exc:  # includes socket timeouts
            raise _Retryable(f"run_query: {exc.reason}") from exc
        try:
            rows = json.loads(body)
        except ValueError as exc:
            raise BlueZooConfigError(
                "run_query returned non-JSON — likeliest cause is "
                "BLUEZOO_BASE_URL pointing at the wrong cluster host (a "
                f"proxy or login page answered). Got: {body[:200]!r}"
            ) from exc
        if not isinstance(rows, list):
            raise BlueZooError(f"run_query returned an unexpected shape: {rows!r}")
        return rows

    def _query(self, sql: str) -> list[dict]:
        """Guard, send, and retry exactly once on transient failures only.

        Quota, credential, and other 4xx errors are never retried — the
        remedy for each is different and none of them is 'try again'.
        """
        _guard_sql(sql)
        try:
            return self._call(sql)
        except _Retryable as first:
            logger.warning("bluezoo run_query transient failure, retrying once: %s", first)
            time.sleep(_RETRY_BACKOFF_SECONDS)
            try:
                return self._call(sql)
            except _Retryable as second:
                raise BlueZooError(f"run_query failed after one retry: {second}") from second
```

Note: `get_visit_intervals` is still missing — the class is abstract until Task 5, so instantiation in these tests requires a temporary stub. **Instead of a stub, implement a minimal passthrough now** so the class is concrete (Task 5 replaces its body):

```python
    def get_visit_intervals(
        self, *, screen_ids: list[int], date_from: date, date_to: date
    ) -> list[BlueZooVisitInterval]:
        raise NotImplementedError("Task 5")  # pragma: no cover — replaced next task
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py -v && make lint`
Expected: all PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add app/audience/live_bluezoo.py tests/unit/test_live_bluezoo_datasource.py
git commit -m "feat(11b): transport with typed errors and single-retry discipline"
```

---

### Task 5: `get_visit_intervals` + factory registration + conformance battery

**Files:**
- Modify: `app/audience/live_bluezoo.py` (replace the Task 4 placeholder)
- Modify: `app/audience/__init__.py:1-31` (docstring + `_BUILTIN_SOURCES`), `app/audience/__init__.py:50-64` (`_instantiate_for_mode` message)
- Modify: `tests/unit/test_audience_factory.py:32-50` (`TestConnectedFailsClosed` — behavior changed)
- Test: `tests/unit/test_live_bluezoo_datasource.py` (append), `tests/unit/test_audience_datasource.py` (append conformance subclass)

**Interfaces:**
- Consumes: the contract battery `AudienceDataSourceContract` (`tests/unit/test_audience_datasource.py:33`, provides `make_source()` + `SCREEN_IDS` hooks), `config.BLUEZOO_VALID_POLICY` (Task 2), DTO with optional occupancy fields (Task 1).
- Produces: `AppMode.CONNECTED` resolvable via `get_audience_datasource()`; connected mode without env now raises `BlueZooConfigError` (previously `RuntimeError("…Phase 11b…not implemented…")` — that message is now false and must go).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_live_bluezoo_datasource.py`:

```python
import logging
import re
from datetime import timedelta

_SQL_IDS = re.compile(r"sensor_id in \(([\d, ]+)\)")
_SQL_WINDOW = re.compile(r"timestamp >= '([^']+)' and timestamp < '([^']+)'")


class _StubbedLive(LiveBlueZooAudienceDataSource):
    """Deterministic fake server: honors the SQL's sensor + window predicates
    (so screen filtering and windowing are genuinely exercised end-to-end),
    returns rows on the 15-min UTC grid, all valid."""

    def _call(self, sql):
        ids = [int(x) for x in _SQL_IDS.search(sql).group(1).split(",")]
        start = date.fromisoformat(_SQL_WINDOW.search(sql).group(1))
        end = date.fromisoformat(_SQL_WINDOW.search(sql).group(2))
        rows = []
        d = start
        while d < end:
            for hour in (9, 10):
                for minute in (0, 15, 30, 45):
                    for sensor_id in ids:
                        rows.append(
                            {
                                "timestamp": f"{d.isoformat()}T{hour:02d}:{minute:02d}:00Z",
                                "sensor_id": sensor_id,
                                "incoming_inner_count": float(sensor_id % 7) + minute / 60.0,
                                "outgoing_inner_count": 1.5,
                                "incoming_outer_count": 4.0,
                                "outgoing_outer_count": float(sensor_id % 5) + hour / 24.0,
                                "valid": True,
                            }
                        )
            d += timedelta(days=1)
        return rows


class TestGetVisitIntervals:
    def test_maps_sensors_back_to_screens(self, live_env):
        out = _StubbedLive().get_visit_intervals(
            screen_ids=[101, 102], date_from=D_FROM, date_to=D_FROM
        )
        assert out and {iv.screen_id for iv in out} == {101, 102}

    def test_unmapped_screens_yield_no_rows_not_error(self, live_env):
        assert (
            _StubbedLive().get_visit_intervals(
                screen_ids=[999], date_from=D_FROM, date_to=D_FROM
            )
            == []
        )

    def test_occupancy_fields_are_none(self, live_env):
        iv = _StubbedLive().get_visit_intervals(
            screen_ids=[101], date_from=D_FROM, date_to=D_FROM
        )[0]
        assert iv.average_visitors_inner is None and iv.maximum_visitors_outer is None

    def test_timestamps_are_naive_utc(self, live_env):
        out = _StubbedLive().get_visit_intervals(
            screen_ids=[101], date_from=D_FROM, date_to=D_FROM
        )
        assert all(iv.timestamp.tzinfo is None for iv in out)

    def test_counts_stay_float(self, live_env):
        iv = _StubbedLive().get_visit_intervals(
            screen_ids=[101], date_from=D_FROM, date_to=D_FROM
        )[0]
        assert isinstance(iv.incoming_inner_count, float)

    def test_ad_campaign_id_is_none_live_rows_know_no_campaigns(self, live_env):
        iv = _StubbedLive().get_visit_intervals(
            screen_ids=[101], date_from=D_FROM, date_to=D_FROM
        )[0]
        assert iv.ad_campaign_id is None

    def test_policy_and_rowcount_logged_per_read(self, live_env, caplog):
        with caplog.at_level(logging.INFO, logger="app.audience.live_bluezoo"):
            _StubbedLive().get_visit_intervals(
                screen_ids=[101], date_from=D_FROM, date_to=D_FROM
            )
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "policy=valid-only" in joined and "rows=8" in joined

    def test_include_all_policy_reaches_the_sql(self, live_env, monkeypatch):
        from app import config as config_module

        monkeypatch.setattr(
            config_module, "BLUEZOO_VALID_POLICY", config_module.BlueZooValidPolicy.INCLUDE_ALL
        )
        seen = {}

        class _Spy(_StubbedLive):
            def _call(self, sql):
                seen["sql"] = sql
                return super()._call(sql)

        _Spy().get_visit_intervals(screen_ids=[101], date_from=D_FROM, date_to=D_FROM)
        assert " and valid" not in seen["sql"]

    def test_foreign_sensor_in_response_fails_loudly(self, live_env):
        class _Foreign(LiveBlueZooAudienceDataSource):
            def _call(self, sql):
                return [
                    {
                        "timestamp": "2026-07-20T09:00:00Z",
                        "sensor_id": 55555,
                        "incoming_inner_count": 1.0,
                        "outgoing_inner_count": 1.0,
                        "incoming_outer_count": 1.0,
                        "outgoing_outer_count": 1.0,
                        "valid": True,
                    }
                ]

        with pytest.raises(BlueZooError, match="unmapped sensor_id=55555"):
            _Foreign().get_visit_intervals(
                screen_ids=[101], date_from=D_FROM, date_to=D_FROM
            )
```

Append to `tests/unit/test_audience_datasource.py` (after `TestSyntheticConformance`):

```python
class TestLiveStubConformance(AudienceDataSourceContract):
    """The live conformer, transport stubbed (fast tier stays network-free),
    run through the same battery the synthetic source passes."""

    SCREEN_IDS = [101, 102]

    @pytest.fixture(autouse=True)
    def _live_env(self, monkeypatch):
        monkeypatch.setenv("BLUEZOO_BASE_URL", "https://stub.invalid/v2/dwh")
        monkeypatch.setenv("BLUEZOO_ACCESS_KEY", "stub-key")
        monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:87,102:433")

    def make_source(self):
        from tests.unit.test_live_bluezoo_datasource import _StubbedLive

        return _StubbedLive()
```

Rewrite `tests/unit/test_audience_factory.py`'s `TestConnectedFailsClosed` (the "Phase 11b not implemented" assertions are now false):

```python
class TestConnectedFailsClosed:
    """Connected mode still fails closed — now at conformer construction,
    naming the missing configuration instead of a missing implementation."""

    def _clear_bluezoo_env(self, monkeypatch):
        for var in ("BLUEZOO_BASE_URL", "BLUEZOO_ACCESS_KEY", "BLUEZOO_SENSOR_MAP"):
            monkeypatch.delenv(var, raising=False)

    def test_connected_without_config_raises_specific_error(self, monkeypatch):
        from app.audience.live_bluezoo import BlueZooConfigError

        monkeypatch.setattr(config, "APP_MODE", config.AppMode.CONNECTED)
        self._clear_bluezoo_env(monkeypatch)
        reset_audience_datasource()
        with pytest.raises(BlueZooConfigError, match="BLUEZOO_BASE_URL"):
            get_audience_datasource()

    def test_no_silent_fallback_to_demo(self, monkeypatch):
        monkeypatch.setattr(config, "APP_MODE", config.AppMode.CONNECTED)
        self._clear_bluezoo_env(monkeypatch)
        reset_audience_datasource()
        with pytest.raises(Exception):
            get_audience_datasource()
        # And the failure must not have cached a synthetic fallback:
        with pytest.raises(Exception):
            get_audience_datasource()

    def test_connected_with_full_env_resolves_to_live_source(self, monkeypatch):
        from app.audience.live_bluezoo import LiveBlueZooAudienceDataSource

        monkeypatch.setattr(config, "APP_MODE", config.AppMode.CONNECTED)
        monkeypatch.setenv("BLUEZOO_BASE_URL", "https://stub.invalid/v2/dwh")
        monkeypatch.setenv("BLUEZOO_ACCESS_KEY", "stub-key")
        monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:87")
        reset_audience_datasource()
        assert isinstance(get_audience_datasource(), LiveBlueZooAudienceDataSource)
        reset_audience_datasource()

    def test_construction_failure_is_not_cached(self, monkeypatch):
        """Owner-named property: a failed _instantiate_for_mode() must leave
        _singleton None, so fixing the env works WITHOUT a reset."""
        from app.audience.live_bluezoo import BlueZooConfigError, LiveBlueZooAudienceDataSource

        monkeypatch.setattr(config, "APP_MODE", config.AppMode.CONNECTED)
        self._clear_bluezoo_env(monkeypatch)
        reset_audience_datasource()
        with pytest.raises(BlueZooConfigError):
            get_audience_datasource()
        monkeypatch.setenv("BLUEZOO_BASE_URL", "https://stub.invalid/v2/dwh")
        monkeypatch.setenv("BLUEZOO_ACCESS_KEY", "stub-key")
        monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:87")
        # Deliberately NO reset between the failure and this call:
        assert isinstance(get_audience_datasource(), LiveBlueZooAudienceDataSource)
        reset_audience_datasource()
```

(Match the file's existing import style for `config`/factory helpers — read the file's top before editing; it already imports these for `TestDemoMode`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py tests/unit/test_audience_datasource.py tests/unit/test_audience_factory.py -v`
Expected: new tests FAIL (`NotImplementedError("Task 5")` / factory still raising the 11a RuntimeError).

- [ ] **Step 3: Implement**

Replace Task 4's `get_visit_intervals` placeholder in `app/audience/live_bluezoo.py` with:

```python
    def get_visit_intervals(
        self, *, screen_ids: list[int], date_from: date, date_to: date
    ) -> list[BlueZooVisitInterval]:
        # Attribute read at call time so tests (and future config reloads)
        # can monkeypatch the policy — same pattern as the factory's APP_MODE.
        policy = config.BLUEZOO_VALID_POLICY
        sensor_ids = sorted(
            self._sensor_by_screen[s]
            for s in set(screen_ids)
            if s in self._sensor_by_screen
        )
        if not sensor_ids:
            # Interface contract: unknown screens yield no rows, not an error.
            logger.info(
                "bluezoo live read: no mapped sensors for screens=%s — no rows",
                sorted(set(screen_ids)),
            )
            return []
        rows = self._query(_build_sql(sensor_ids, date_from, date_to, policy))
        out = [self._to_interval(row) for row in rows]
        out.sort(key=lambda iv: (iv.screen_id, iv.timestamp))
        # Rule R visibility: policy + row count logged on EVERY live read so
        # the exclusion (or its absence) is auditable per query.
        logger.info(
            "bluezoo live read: policy=%s sensors=%s window=%s..%s rows=%d",
            policy.value,
            sensor_ids,
            date_from.isoformat(),
            date_to.isoformat(),
            len(out),
        )
        return out

    def _to_interval(self, row: dict) -> BlueZooVisitInterval:
        sensor_id = int(row["sensor_id"])
        screen_id = self._screen_by_sensor.get(sensor_id)
        if screen_id is None:
            # The SQL filtered on our sensor ids; a foreign one back is a
            # server-side surprise worth failing loudly on, never dropping.
            raise BlueZooError(f"run_query returned unmapped sensor_id={sensor_id}")
        return BlueZooVisitInterval(
            timestamp=_parse_utc_naive(row["timestamp"]),
            screen_id=screen_id,
            # Live rows know nothing of this app's campaigns; occupancy
            # fields stay None (sensor_visits-only query — see module doc).
            incoming_inner_count=float(row["incoming_inner_count"]),
            outgoing_inner_count=float(row["outgoing_inner_count"]),
            incoming_outer_count=float(row["incoming_outer_count"]),
            outgoing_outer_count=float(row["outgoing_outer_count"]),
            valid=_coerce_valid(row["valid"]),
        )
```

In `app/audience/__init__.py`:
1. Register the conformer:
```python
_BUILTIN_SOURCES: dict[AppMode, str] = {
    AppMode.DEMO: "app.audience.synthetic:SyntheticAudienceDataSource",
    AppMode.CONNECTED: "app.audience.live_bluezoo:LiveBlueZooAudienceDataSource",
}
```
2. Delete the now-stale comment above it (`# Phase 11b registers AppMode.CONNECTED here…fails closed…`) and update the module docstring's line 3–4 to: `connected → LiveBlueZooAudienceDataSource (Phase 11b), which fails closed at construction if BlueZoo configuration is missing.`
3. Reword `_instantiate_for_mode`'s dict-miss error (now a defensive guard, not the 11b gap):
```python
        raise RuntimeError(
            f"No audience data source is registered for APP_MODE={mode.value!r} "
            "— this is a bug (every AppMode member must have a _BUILTIN_SOURCES "
            "entry). Silently falling back to demo data is not allowed."
        )
```
4. In `app/audience/datasource.py`, update the docstring phrase `Phase 11b's live/cached conformers answer` → `Phase 11b's live conformer answers` (the cached provider was dropped, owner-approved).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py tests/unit/test_audience_datasource.py tests/unit/test_audience_factory.py -v` then `make test-unit && make lint`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/audience/ tests/unit/
git commit -m "feat(11b): LiveBlueZooAudienceDataSource — connected mode goes live behind the seam"
```

---

### Task 6: Real-payload fixture (one-time live capture) + parsing test

**Files:**
- Create: `tests/unit/data/bluezoo_sensor_visits_sample.json` (captured), `tests/unit/data/bluezoo_sensor_visits_sample.md` (provenance)
- Test: `tests/unit/test_live_bluezoo_datasource.py` (append)

**Interfaces:**
- Consumes: `scripts/bluezoo_probe.py --sql` (guarded, reads `app/.env`), `_StubbedLive` pattern.
- Produces: the fast tier parses a genuinely real MO_92 payload on every `make test` run — the owner-approved replacement for `CachedBlueZooAudienceDataSource`.

**This task performs TWO tiny live reads (~30 KB scanned total vs a 500 GB/sensor-location allowance). Read-only. Never print or commit the key.**

- [ ] **Step 0: Pick sensors from evidence, not by assumption (owner condition)**

MO_92's recent grid coverage is only ~34% (≈32 of 96 slots/sensor/day) and 19 live sensors sit at `valid=false` — an unverified id makes downstream scenes fail for a data reason that looks like a code bug. Verify first (last 7 full UTC days; scans sensor_id+timestamp+valid over the window, ~20 KB):

```bash
python3 scripts/bluezoo_probe.py --sql "select sensor_id, count(*) as n from sensor_visits where timestamp >= '<D1-6d>' and timestamp < '<D2>' and valid group by sensor_id order by n desc"
```

Pick the top 2–3 sensors by valid-row count. These ids (call them `S1, S2[, S3]`) are THE sensors for everything downstream: this task's capture, Task 7's live test, Task 9's scenario map. Record the chosen ids, their counts, and the selection query in `tests/unit/data/bluezoo_sensor_visits_sample.md` (Step 2) — Task 9 copies the rationale into `connected-bluezoo.md`.

- [ ] **Step 1: Capture the payload**

Pick `D1` = the UTC date 3 days before today, `D2` = the day after `D1`. Run with `S1, S2` from Step 0 (the plan's examples use 87, 433 — replace with the verified ids):

```bash
python3 scripts/bluezoo_probe.py --sql "select timestamp, sensor_id, incoming_inner_count, outgoing_inner_count, incoming_outer_count, outgoing_outer_count, valid from sensor_visits where timestamp >= '<D1>' and timestamp < '<D2>' and sensor_id in (87, 433)" > tests/unit/data/bluezoo_sensor_visits_sample.json
```

Expected: a JSON array of ~192 rows (2 sensors x 96 slots). Inspect the first rows: confirm (a) the `timestamp` serialization format, (b) the `valid` serialization (JSON bool vs string), (c) counts numeric vs string. **If `_parse_utc_naive` or `_coerce_valid` (Task 3) cannot handle the real format, fix them in this task** — that verification is this fixture's whole purpose. Redaction check: the file must contain ONLY the seven named columns (ids/timestamps/counts/valid — no venue or operator strings can appear by construction; verify by eyeball anyway).

- [ ] **Step 2: Write the provenance note**

Create `tests/unit/data/bluezoo_sensor_visits_sample.md`:

```markdown
# bluezoo_sensor_visits_sample.json — provenance

One-time capture from BlueZoo Morpheus/MO_92 (real venue data, redacted by
construction: only ids/timestamps/counts/valid — the seven named columns of
the live conformer's fixed SELECT; no venue/operator identifiers, no key).

- Sensor selection (owner condition — evidence, not assumption): sensors
  <S1>, <S2> chosen as the top valid-row producers over <D1-6d>..<D2>
  (counts: <n1>, <n2>; selection query in plan.md Task 6 Step 0). MO_92's
  recent grid coverage is ~34% and 19 live sensors are valid=false, so
  unverified ids fail downstream for data reasons that look like code bugs.
- Captured: <capture date>, via `scripts/bluezoo_probe.py --sql` (read-only,
  client-side SELECT + time-constraint guards)
- Window: <D1> .. <D2> (UTC, half-open); sensors <S1>, <S2>; no `valid`
  filter (policy-neutral capture)
- Cost: ~8 KB scanned (~192 rows x 41 B)
- Purpose: every `make test` run parses a genuinely REAL payload shape —
  the owner-approved replacement for the dropped CachedBlueZooAudienceDataSource
  (see 11-live-bluezoo-adapter.md Exit criteria amendment, 2026-07-27).
```

- [ ] **Step 3: Write the failing test**

Append to `tests/unit/test_live_bluezoo_datasource.py` (set `FIXTURE_D_FROM`/`FIXTURE_D_TO` to the actual `D1`/`D1` values — `date_to` is inclusive, so both are `D1`):

```python
FIXTURE = Path(__file__).parent / "data" / "bluezoo_sensor_visits_sample.json"
FIXTURE_D_FROM = date(2026, 7, 24)  # <- set to the capture's D1
FIXTURE_D_TO = date(2026, 7, 24)


class TestRealPayloadFixture:
    """The dropped cached provider's replacement: a REAL MO_92 payload,
    parsed by the real conformer code on every fast-tier run."""

    def test_real_payload_parses_into_dtos(self, live_env):
        raw = json.loads(FIXTURE.read_text())
        assert raw, "fixture must not be empty"

        class _Replay(LiveBlueZooAudienceDataSource):
            def _call(self, sql):
                return raw

        # Fixture rows are for sensors 87/433 == mapped screens 101/102.
        out = _Replay().get_visit_intervals(
            screen_ids=[101, 102], date_from=FIXTURE_D_FROM, date_to=FIXTURE_D_TO
        )
        assert len(out) == len(raw)
        assert {iv.screen_id for iv in out} == {101, 102}
        assert all(iv.timestamp.tzinfo is None for iv in out)
        assert all(
            iv.timestamp.minute % 15 == 0 and iv.timestamp.second == 0 for iv in out
        )
        assert all(isinstance(iv.incoming_inner_count, float) for iv in out)
        assert all(isinstance(iv.valid, bool) for iv in out)
        assert all(iv.average_visitors_inner is None for iv in out)
```

Add `import json` and `from pathlib import Path` to the file's imports if missing.

- [ ] **Step 4: Run the test**

Run: `pytest tests/unit/test_live_bluezoo_datasource.py::TestRealPayloadFixture -v` then `make test-unit`
Expected: PASS (after any format fix from Step 1). Confirm no network: this test replays the file.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/data/bluezoo_sensor_visits_sample.json tests/unit/data/bluezoo_sensor_visits_sample.md tests/unit/test_live_bluezoo_datasource.py app/audience/live_bluezoo.py
git commit -m "feat(11b): redacted real MO_92 payload as fast-tier fixture (cached-provider replacement)"
```

---

### Task 7: Live-tier test (`make test-live`)

**Files:**
- Create: `tests/live/test_live_bluezoo_datasource.py`

**Interfaces:**
- Consumes: `tests/live/conftest.py`'s autouse `live_real_environment` (loads real `app/.env`), `LiveBlueZooAudienceDataSource`, `config.BLUEZOO_VALID_POLICY`, and the **verified sensor ids from Task 6 Step 0** (read them from `tests/unit/data/bluezoo_sensor_visits_sample.md`; replace the literal `87`/`433` below with `S1`/`S2` and update the docstring's watchlist line to name them).

- [ ] **Step 1: Write the test**

Create `tests/live/test_live_bluezoo_datasource.py`:

```python
"""Live-tier BlueZoo conformer test (Phase 11b) — REAL reads against MO_92.

Byte budget per run: two queries x ~8 KB (2 sensors x 1 day x 41 B/row x
96 rows) ~= 16 KB, against a 500 GB/sensor-location monthly allowance.
Flakiness watchlist: sensors 87/433 are currently-reporting MO_92 sensors
(semantics findings, 2026-07-27); if both go dark the non-empty assertions
fail — swap ids per SETUP_INSTRUCTIONS.md's live-tier section.
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
    monkeypatch.setenv("BLUEZOO_SENSOR_MAP", "101:87,102:433")


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
```

- [ ] **Step 2: Verify fast tier does NOT collect it**

Run: `make test 2>&1 | tail -5` and `pytest tests/unit tests/e2e --collect-only -q 2>/dev/null | grep -c live_bluezoo_datasource || true`
Expected: `make test` green with no live test run; the grep over unit/e2e collection finds only `tests/unit/test_live_bluezoo_datasource.py` items (stubbed), nothing from `tests/live/`.

- [ ] **Step 3: Run the live test for real (bills ~16 KB of quota — accepted)**

Run: `pytest tests/live/test_live_bluezoo_datasource.py -v`
Expected: 2 PASS against real MO_92. If credentials are missing the tier's guard fails loudly (by design — do not add a skip).

- [ ] **Step 4: Commit**

```bash
git add tests/live/test_live_bluezoo_datasource.py
git commit -m "test(11b): live-tier MO_92 conformer test (tiny window, policy knob exercised)"
```

---

### Task 8: `SETUP_INSTRUCTIONS.md` — connected mode section

**Files:**
- Modify: `SETUP_INSTRUCTIONS.md` (new section; place after the live-tier testing section — read the file's structure first and match its heading style)

**Interfaces:**
- Consumes: env names and error semantics from Tasks 2–5 (must match code exactly).

- [ ] **Step 1: Write the section**

Add a "Connected mode (`APP_MODE=connected`) — live BlueZoo adapter" section containing exactly these elements:

1. Env var table:

| Variable | Required | Meaning |
|---|---|---|
| `APP_MODE` | yes (`connected`) | Selects the live BlueZoo audience source (Phase 11b). |
| `BLUEZOO_BASE_URL` | yes | Cluster-specific DWH URL, e.g. `https://<cluster-host>/v2/dwh`. **No default** — cluster-scoped, pairs with the key. |
| `BLUEZOO_ACCESS_KEY` | yes | Bare AccessKey UUID (dashboard → Profile). The adapter adds the `AccessKey ` prefix itself. Never commit it. |
| `BLUEZOO_SENSOR_MAP` | yes | `screen_id:sensor_id,...` e.g. `101:87,102:433`. One-to-one; malformed values fail closed at startup. Phase 12's CMS integration decides the long-term source of this mapping. |
| `BLUEZOO_VALID_POLICY` | no (default `valid-only`) | `valid-only` = Rule R (count only commissioning-accepted rows; OUR recommendation, pending BlueZoo confirmation — see `docs/METRICS.md`). `include-all` = no filter. Every live read logs `policy=... rows=...`. |

2. The pair rule, verbatim intent: **secrets hold a `{base_url, access_key}` pair per tenant, never a lone key** — the base URL is cluster-scoped configuration that travels with the credential; separating them is how "wrong host" becomes a support ticket reading "auth is broken" (Phase 13 amendment).

3. The concrete deploy line (Cloud Run; note the `^@^` delimiter because `BLUEZOO_SENSOR_MAP` itself contains commas):

```bash
# One secret per half of the pair, same tenant prefix so they can't be mixed:
gcloud secrets create bluezoo-morpheus-base-url   --data-file=- <<< "https://<cluster-host>/v2/dwh"
gcloud secrets create bluezoo-morpheus-access-key --data-file=- <<< "<ACCESS_KEY_UUID>"

gcloud run deploy video-ad-agent \
  --set-secrets "BLUEZOO_BASE_URL=bluezoo-morpheus-base-url:latest,BLUEZOO_ACCESS_KEY=bluezoo-morpheus-access-key:latest" \
  --set-env-vars "^@^APP_MODE=connected@BLUEZOO_SENSOR_MAP=101:87,102:433@BLUEZOO_VALID_POLICY=valid-only"
```

Plus one line: Agent Engine deploys inject the same pair through the deploy script's env config; in-code Secret Manager SDK reads are deliberately Phase 13 Tier B.

4. Operational notes: quota exhaustion is a distinct, non-retryable error whose remediation is "ask BlueZoo to raise the allowance"; zero rows is a legitimate result; and append to the existing live-tier flakiness watchlist: `tests/live/test_live_bluezoo_datasource.py` assumes sensors 87/433 are reporting — swap ids if MO_92's fleet changes.

- [ ] **Step 2: Verify consistency**

Grep the section's env names and error phrases against the code: `grep -n "BLUEZOO_" app/audience/live_bluezoo.py app/config.py` — every variable named in the docs must appear in code and vice versa.

- [ ] **Step 3: Commit**

```bash
git add SETUP_INSTRUCTIONS.md
git commit -m "docs(11b): connected-mode setup — secret pair, concrete deploy line, ops notes"
```

---

### Task 9: Demo scenario doc + DEMO_GUIDE.md journeys

**Files:**
- Create: `docs/demo-scenarios/connected-bluezoo.md`
- Modify: `DEMO_GUIDE.md` (append to the "Workstream Testing Journeys" section — owner rule: always the root guide)

**Interfaces:**
- Consumes: `screens_for_campaign(cid)` roster (`python3 -c "from app.demo_data.attribution import screens_for_campaign; print(screens_for_campaign(1))"` — 2–3 screens, ids `1*100+k`), MO_92 currently-valid sensors 87/433/324, error text from Task 4, log line format from Task 5.

- [ ] **Step 1: Write the scenario doc**

Create `docs/demo-scenarios/connected-bluezoo.md` in the Act/Scene shape (per `verifying-with-demo-scenarios` — queries + explicit expected-tool-call assertions per scene). Required content:

- **Setup (per scene):** how to launch — `APP_MODE=connected` plus the BLUEZOO_* vars prepended to `make dev`; the sensor map built from campaign 1's actual screen roster mapped onto the **Task 6 Step 0 verified sensors** `S1,S2[,S3]` (compute the roster with the one-liner above and write the literal map into the doc — adjust to the actual roster size). Include a "why these sensors" line quoting the selection evidence from `tests/unit/data/bluezoo_sensor_visits_sample.md` (owner condition: sensors chosen from verified recent valid rows, so a scene failure means code, not a dark or never-commissioned sensor).
- **Scene 1 — fail-closed (no BlueZoo config):** start with `APP_MODE=connected` and all `BLUEZOO_*` unset. Query: ask the agent to activate a pending video (reuse the F3 activation prompt shape from `docs/demo-scenarios/fashion.md`). Expected: the activation tool call fires and its response/trace carries the `BlueZooConfigError` text naming `BLUEZOO_BASE_URL` and `BLUEZOO_ACCESS_KEY` — and NO metrics rows are silently generated from demo data (no silent fallback). PASS = error named in trace; FAIL = success response or synthetic metrics.
- **Scene 2 — happy path (real MO_92 rows):** start with full env + map. Query: activate a pending video for campaign 1, then ask for that campaign's video metrics. Expected tool calls: the review/activation tool, then the metrics tool; response reports non-zero impressions. Evidence that data is LIVE, all three checked: (a) the server log (captured `make dev` output) contains `bluezoo live read: policy=valid-only` lines with `rows=` > 0; (b) impressions values differ from the demo-mode values for the same video (they derive from real float counts, not the deterministic synthetic frames); (c) no error in trace. PASS requires (a) — the other two corroborate.
- **Scene 3 — policy knob:** relaunch with `BLUEZOO_VALID_POLICY=include-all`; repeat a metrics-affecting action; expected: server log shows `policy=include-all`. (Trace-level behavior otherwise identical — this scene verifies the knob is wired, not a metric delta.)
- A header note: **read-only against BlueZoo; each scene's reads scan a few hundred KB at most** (30-day window × ≤3 sensors × 41 B/row ≈ 350 KB) against a 500 GB/sensor-location allowance.

- [ ] **Step 2: Add DEMO_GUIDE.md journeys**

Append a "Workstream 11b — connected mode (live BlueZoo)" subsection to `DEMO_GUIDE.md`'s "Workstream Testing Journeys" with copy-paste journeys (commands + expected results), covering: connected-mode setup (env vars incl. building the sensor map), the happy path (activate → metrics from real MO_92 rows; what the log line looks like), the fail-closed path (missing config → the exact error), and the policy knob (`include-all` + the changed log line). Prune nothing — no existing journey is invalidated by this workstream (demo mode is byte-identical).

- [ ] **Step 3: Verify demo mode untouched**

Run: `make test` (full fast tier).
Expected: green — the scenario/journey docs change no code.

- [ ] **Step 4: Commit**

```bash
git add docs/demo-scenarios/connected-bluezoo.md DEMO_GUIDE.md
git commit -m "docs(11b): connected-bluezoo demo scenario + DEMO_GUIDE workstream journeys"
```

---

### Task 10: Demo-scenario verification (controller-executed — NOT a subagent implementer task)

Run per `verifying-with-demo-scenarios` (STATUS → `verify in progress` in the MAIN checkout first). Dispatch `demo-scenario-verifier` **sequentially** (port 8501 is fixed):

- [ ] **Dispatch 1 — demo-mode regression:** scenarios F2 + F3 from `docs/demo-scenarios/fashion.md`, plain `make dev` (demo mode). Expected: PASS unchanged — this workstream's demo path is byte-identical.
- [ ] **Dispatch 2 — connected-bluezoo:** all three scenes of `docs/demo-scenarios/connected-bluezoo.md`, with the real `app/.env` credentials (already in the worktree copy). The verifier must capture the `make dev` server log to assert the `bluezoo live read` lines (Scenes 2–3) and screenshot/trace evidence per scene.
- [ ] **Record:** append checkpoint 5 (pass/fail per scenario + evidence paths) to `WORK_LOG.md`. A failing scene blocks Task 11 — fix and re-verify.

---

### Task 11: Pre-PR sweep — credentials/PII, lint, full suite

- [ ] **Step 1: Credential/PII sweep of the whole branch diff**

```bash
git diff version_2...HEAD | grep -iE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|access_key.{0,4}=|AccessKey [0-9a-f]" | grep -v "ACCESS_KEY_UUID\|BLUEZOO_ACCESS_KEY=bluezoo\|AccessKey {" || echo CLEAN
git diff version_2...HEAD --stat   # eyeball: no app/.env, no scan artifacts
```

Also manually scan `tests/unit/data/bluezoo_sensor_visits_sample.json` once more: seven columns only, no strings other than timestamps. Expected: CLEAN.

- [ ] **Step 1b: Verify the DISCOVERY amendments shipped (owner condition b)**

The occupancy-fields discovery was amended with provenance at approval time (commit ffdfb43). Confirm all three are in the branch diff before the PR:

```bash
git diff version_2...HEAD -- .docs/version2-plan/11-live-bluezoo-adapter.md docs/METRICS.md .docs/version2-plan/99-open-questions.md | grep -c "Amended (workstream 11b, 2026-07-27)"
```

Expected: ≥ 4 (drift note + Exit criteria in `11-*.md`, METRICS.md circulation, Q5), and the WORK_LOG carries the `DISCOVERY` entry.

- [ ] **Step 2: Full gates**

Run: `make lint && make test`
Expected: lint clean; full fast tier green, zero network.

- [ ] **Step 3: Commit any stragglers, then hand off**

Proceed to the final whole-branch review (`requesting-code-review`, most capable model, package via `scripts/review-package $(git merge-base version_2 HEAD) HEAD`), then `finishing-a-development-branch` (PR into `version_2`, owner-confirmed self-merge).

---

## Self-Review (performed at plan time)

- **Spec coverage:** every working-doc element maps to a task — DTO change + model-documented divergence (T1, owner condition a), policy knob (T2), one class/one method with guards, typed errors, retry, mapping, logging (T3–T5), fixture replacing the cached provider (T6, owner decision 2), live tier (T7), secret-pair docs + concrete gcloud line (T8, owner condition on decision 3), scenario + DEMO_GUIDE journeys (T9, owner-mandated), verification (T10), sweep (T11). DISCOVERY amendments were already committed at approval time (ffdfb43).
- **Placeholder scan:** the only deliberate placeholders are Task 6's `<D1>/<D2>/<capture date>` (unknowable until capture day — the task says exactly how to compute them) and Task 8/9's "match the file's structure" instructions for prose docs.
- **Type consistency:** `_parse_sensor_map -> dict[int, int]`; `_build_sql(list[int], date, date, BlueZooValidPolicy) -> str`; `_call/_query -> list[dict]`; `get_visit_intervals` keyword-only per the ABC; `_StubbedLive` defined in `tests/unit/test_live_bluezoo_datasource.py` and imported from there by the conformance subclass — names match across tasks.
