# Workstream 11a — Audience Provider Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put demo mode behind the same `AudienceDataSource` interface live mode will use — one seam, APP_MODE-selected, fail-closed for `connected` — plus ws10 carried items 1+2.

**Architecture:** New `app/audience/` package: `AudienceDataSource` ABC (one read: visit intervals for screens+window, returning `BlueZooVisitInterval`), `SyntheticAudienceDataSource` wrapping `app/demo_data/seed.py` as-is, and a factory ported from the donor's mechanics (lazy dotted-path registry keyed by `AppMode`, thread-safe singleton, test-override seam, fail-closed error for `connected`). `derive_rows_from_windows` becomes the seam's one production caller. A shared `app/demo_data/windows.py` helper de-duplicates the window-load SQL and adds the empty-list guard.

**Tech Stack:** Python 3.12, ABC/abstractmethod, Pydantic v2 (existing DTOs), sqlite3, pytest. No new dependencies.

## Global Constraints

- No `Co-Authored-By: Claude` or any AI-attribution trailer in commit messages.
- Donor repo `/Users/lavi/gwork/ad-campaign-agent` is strictly read-only — never modify, never run its code.
- `APP_MODE` stays the ONLY user-facing mode knob (`app/config.py` comment, Phase 6). No new env vars.
- `app/demo_data/seed.py`: algorithm untouched; the only permitted edit is its docstring seam-promise line (Task 6).
- **Existing test files must pass UNMODIFIED** — they pin the refactor invariant. Names existing tests import must survive: `review_tools._load_attribution_windows` (tests/unit/test_review_tools.py:630,678,715; tests/unit/test_mock_data_attribution.py:37) and `attribution._campaign_seed_config` (tests/unit/test_demo_attribution.py:127). Keep both as aliases.
- Byte-identical `video_metrics`: `derive_video_metrics_rows` output must not change for any input (Task 5's golden test pins it).
- ruff clean on every touched file (`make lint` is red repo-wide with ~40 pre-existing errors — the gate is zero NEW errors; check with `.venv/bin/ruff check <touched files>`).
- Relative imports inside `app/` (match existing style, e.g. `from ..models.attribution import ...`).
- A `PostToolUse` hook runs `make test-unit` automatically after edits to `app/**/*.py` — expect it, don't fight it.
- Layering: `app/database` must never import `app/tools`. `app/audience` may import `app/models`, `app/config`, `app/demo_data`; nothing in `app/demo_data` imports `app/audience` at module top level (Task 5 uses a function-level import for the factory default).
- Run tests with `.venv/bin/pytest`; fast loop is `make test-unit` (~4s).

## File Structure

- Create: `app/demo_data/windows.py` (shared window load, empty-list guard), `app/audience/__init__.py` (factory), `app/audience/datasource.py` (ABC), `app/audience/synthetic.py` (synthetic source), `tests/unit/test_windows_helper.py`, `tests/unit/test_audience_datasource.py`, `tests/unit/test_audience_factory.py`, `tests/unit/test_seam_refactor_golden.py`.
- Modify: `app/tools/review_tools.py` (helper → alias), `app/database/mock_data.py` (inline SQL → helper call), `app/demo_data/attribution.py` (public seed-config name; join reads through the seam), `app/demo_data/seed.py` (docstring line only), `app/demo_data/constants.py` (docstring only), `.docs/version2-plan/demo_guide.md` (APP_MODE part).

---

### Task 1: Shared window-load helper (ws10 carried items 1 + 2)

**Files:**
- Create: `app/demo_data/windows.py`
- Modify: `app/tools/review_tools.py:117-137` (replace `_load_attribution_windows` def with alias import)
- Modify: `app/database/mock_data.py:361-374` (replace inline 4-line load block with helper call)
- Test: `tests/unit/test_windows_helper.py`

**Interfaces:**
- Consumes: `video_attribution` table (video_id, screen_id, active_from, active_to), existing at `app/database/db.py`.
- Produces: `load_attribution_windows(cursor, video_ids) -> list[dict]` — dicts with keys `video_id`, `screen_id`, `active_from: datetime`, `active_to: datetime | None`. Task 5's join consumes this exact shape (unchanged from today).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_windows_helper.py`:

```python
"""Shared attribution-window loader (ws10 carried items 1+2)."""

import sqlite3
from datetime import datetime

from app.demo_data.windows import load_attribution_windows


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE video_attribution ("
        "video_id INTEGER, ad_campaign_id INTEGER, screen_id INTEGER, "
        "active_from TEXT NOT NULL, active_to TEXT)"
    )
    conn.execute(
        "INSERT INTO video_attribution VALUES (7, 101, 10100, '2026-06-01T00:00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO video_attribution VALUES "
        "(7, 101, 10101, '2026-06-01T00:00:00', '2026-06-05T12:00:00')"
    )
    conn.execute(
        "INSERT INTO video_attribution VALUES (8, 101, 10100, '2026-06-02T00:00:00', NULL)"
    )
    return conn


class _ExplodingCursor:
    """Fails the test if any SQL is executed."""

    def execute(self, *a, **k):
        raise AssertionError("empty video_ids must not touch the DB")


class TestLoadAttributionWindows:
    def test_empty_video_ids_returns_empty_without_sql(self):
        # Carried item 1: '... IN ()' is invalid SQLite; guard must short-circuit.
        assert load_attribution_windows(_ExplodingCursor(), []) == []

    def test_loads_windows_in_join_ready_shape(self):
        cur = _make_db().cursor()
        windows = load_attribution_windows(cur, [7])
        assert len(windows) == 2
        w_open = next(w for w in windows if w["screen_id"] == 10100)
        assert w_open == {
            "video_id": 7,
            "screen_id": 10100,
            "active_from": datetime(2026, 6, 1),
            "active_to": None,
        }
        w_closed = next(w for w in windows if w["screen_id"] == 10101)
        assert w_closed["active_to"] == datetime(2026, 6, 5, 12)

    def test_works_with_sqlite3_row_factory(self):
        # review_tools cursors use sqlite3.Row (app/database/db.py:29);
        # mock_data cursors may be plain tuples — helper must serve both.
        conn = _make_db()
        conn.row_factory = sqlite3.Row
        windows = load_attribution_windows(conn.cursor(), [7, 8])
        assert {w["video_id"] for w in windows} == {7, 8}

    def test_review_tools_alias_is_the_shared_helper(self):
        # Carried item 2: one implementation, two import sites.
        from app.tools import review_tools

        assert review_tools._load_attribution_windows is load_attribution_windows
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_windows_helper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.demo_data.windows'`

- [ ] **Step 3: Implement the helper**

Create `app/demo_data/windows.py`:

```python
"""Shared attribution-window DB load (ws10 carried items 1+2).

Lives in app/demo_data so both app/tools (review_tools) and app/database
(mock_data) can share one implementation without breaking the layering
rule that app.database never imports app.tools.

Rows are indexed positionally so the helper serves both sqlite3.Row
cursors (review_tools, via app/database/db.py's row_factory) and plain
tuple cursors (mock_data's bulk path).
"""

from datetime import datetime


def load_attribution_windows(cursor, video_ids) -> list[dict]:
    """Read the video set's attribution windows in join-ready dict shape.

    An empty video_ids returns [] without touching the DB — building
    ``IN ()`` is invalid SQLite (ws10 carried item 1).
    """
    video_ids = list(video_ids)
    if not video_ids:
        return []
    placeholders = ",".join("?" for _ in video_ids)
    cursor.execute(
        f"SELECT video_id, screen_id, active_from, active_to FROM video_attribution "
        f"WHERE video_id IN ({placeholders})",
        video_ids,
    )
    return [
        {
            "video_id": row[0],
            "screen_id": row[1],
            "active_from": datetime.fromisoformat(row[2]),
            "active_to": datetime.fromisoformat(row[3]) if row[3] else None,
        }
        for row in cursor.fetchall()
    ]
```

- [ ] **Step 4: Rewire review_tools**

In `app/tools/review_tools.py`, delete the whole `_load_attribution_windows` function (currently lines 117-137, from `def _load_attribution_windows(...)` through its `return windows`) and add to the import block at the top of the file (next to the existing `from ..demo_data.derive import derive_video_metrics_rows`):

```python
# Shared with mock_data (ws10 carried item 2); the underscore alias keeps
# the historical import site (tests import it from here) working.
from ..demo_data.windows import load_attribution_windows as _load_attribution_windows
```

- [ ] **Step 5: Rewire mock_data**

In `app/database/mock_data.py`, add to the import block (next to `from ..demo_data.derive import derive_video_metrics_rows`):

```python
from ..demo_data.windows import load_attribution_windows
```

Then replace the inline block (currently lines ~361-374 — the comment `# (4-line inline window load — mock_data must not import app.tools)`, the `placeholders = ...` line, the `cursor.execute(...)` call, and the `windows = [...]` list comprehension) with:

```python
        # Shared loader in app/demo_data — legal layering (no app.tools import).
        windows = load_attribution_windows(cursor, campaign_video_ids)
```

Keep the preceding comment line `# Generate deterministic metrics through the stored windows` and everything after (`for row in derive_video_metrics_rows(...)`) untouched.

- [ ] **Step 6: Run the new tests and the full unit suite**

Run: `.venv/bin/pytest tests/unit/test_windows_helper.py -v` — Expected: 4 PASS.
Run: `make test-unit` — Expected: all pass, zero modified existing tests.
Run: `.venv/bin/ruff check app/demo_data/windows.py app/tools/review_tools.py app/database/mock_data.py tests/unit/test_windows_helper.py` — Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add app/demo_data/windows.py app/tools/review_tools.py app/database/mock_data.py tests/unit/test_windows_helper.py
git commit -m "feat: shared attribution-window loader with empty-list guard (ws10 items 1+2)"
```

---

### Task 2: AudienceDataSource ABC

**Files:**
- Create: `app/audience/datasource.py`
- Create: `app/audience/__init__.py` (minimal for now — Task 4 fills in the factory)
- Test: `tests/unit/test_audience_datasource.py` (structural tests + reusable contract battery skeleton)

**Interfaces:**
- Consumes: `BlueZooVisitInterval` from `app/models/attribution.py:43` (extra="forbid"; fields: timestamp, screen_id, optional ad_campaign_id, 4 in/out counts, 6 min/max/avg visitors, valid).
- Produces: `AudienceDataSource` ABC with exactly one abstract method: `get_visit_intervals(self, *, screen_ids: list[int], date_from: date, date_to: date) -> list[BlueZooVisitInterval]`. Task 3 subclasses it; Task 4's factory returns it; Task 5's join calls it. Also produces the `AudienceDataSourceContract` test battery that Task 3 plugs into.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_audience_datasource.py`:

```python
"""AudienceDataSource ABC: structure + reusable conformance battery (Phase 11a).

The battery (AudienceDataSourceContract) is deliberately subclass-pluggable:
Phase 11b's cached/live conformers add their own TestXxxConformance class
with a make_source() override and inherit every check for free.
"""

import inspect
from datetime import date, timedelta

import pytest

from app.audience.datasource import AudienceDataSource
from app.models.attribution import BlueZooVisitInterval

D_FROM = date(2026, 6, 1)
D_TO = date(2026, 6, 3)


class TestAbstractInterface:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            AudienceDataSource()

    def test_get_visit_intervals_is_abstract_and_keyword_only(self):
        assert "get_visit_intervals" in AudienceDataSource.__abstractmethods__
        sig = inspect.signature(AudienceDataSource.get_visit_intervals)
        params = list(sig.parameters.values())[1:]  # drop self
        assert [p.name for p in params] == ["screen_ids", "date_from", "date_to"]
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)


class AudienceDataSourceContract:
    """Conformance battery. Subclasses provide make_source() and screen ids."""

    # 2-3 screens of one demo campaign (ws10 convention: cid*100+k).
    SCREEN_IDS: list[int] = []

    def make_source(self) -> AudienceDataSource:
        raise NotImplementedError

    def test_returns_dto_instances(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        assert intervals, "expected at least one interval for a live demo screen"
        assert all(isinstance(iv, BlueZooVisitInterval) for iv in intervals)

    def test_respects_screen_filter(self):
        one = self.SCREEN_IDS[:1]
        intervals = self.make_source().get_visit_intervals(
            screen_ids=one, date_from=D_FROM, date_to=D_TO
        )
        assert intervals and {iv.screen_id for iv in intervals} == set(one)

    def test_respects_date_window(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_FROM
        )
        assert intervals
        assert {iv.timestamp.date() for iv in intervals} == {D_FROM}

    def test_deterministic_across_calls_and_instances(self):
        a = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        b = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        assert a == b

    def test_slot_grain_is_15_minutes(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS[:1], date_from=D_FROM, date_to=D_FROM
        )
        stamps = sorted(iv.timestamp for iv in intervals)
        assert len(stamps) == 48  # 09:00-21:00 at 15-min grain (seed.py contract)
        deltas = {b - a for a, b in zip(stamps, stamps[1:])}
        assert deltas == {timedelta(minutes=15)}

    def test_unknown_screen_returns_empty_not_error(self):
        # A sensor the source doesn't know = no data, like a real sensor API.
        intervals = self.make_source().get_visit_intervals(
            screen_ids=[999_999_99], date_from=D_FROM, date_to=D_TO
        )
        assert intervals == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_audience_datasource.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.audience'`
(The `AudienceDataSourceContract` battery has no subclass yet, so only `TestAbstractInterface` collects — that's intended; Task 3 plugs the battery in.)

- [ ] **Step 3: Implement the ABC**

Create `app/audience/datasource.py`:

```python
"""AudienceDataSource — the audience-measurement seam (Phase 11a).

One interface, two worlds: demo mode's synthetic source (this phase) and
Phase 11b's live/cached BlueZoo conformers answer the same read. The
signature is deliberately BlueZoo-shaped — screens + a date window in,
sensor_visits-shaped intervals out — so nothing synthetic-only (campaign
ids, seed configs) leaks into what a real adapter must implement.

Read-only by design: attribution windows are this app's own domain (the
CMS/ad-play side, written by review_tools' bridge), not audience data.
"""

from abc import ABC, abstractmethod
from datetime import date

from ..models.attribution import BlueZooVisitInterval


class AudienceDataSource(ABC):
    """Read-only source of per-(screen, 15-min slot) visit intervals."""

    @abstractmethod
    def get_visit_intervals(
        self, *, screen_ids: list[int], date_from: date, date_to: date
    ) -> list[BlueZooVisitInterval]:
        """Visit intervals for the given screens, covering the inclusive
        day range [date_from, date_to]. Unknown screens yield no rows."""
```

Create `app/audience/__init__.py`:

```python
"""Audience data-source seam (Phase 11a). Factory lands in this module in
the same workstream — see get_audience_datasource()."""

from .datasource import AudienceDataSource

__all__ = ["AudienceDataSource"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_audience_datasource.py -v`
Expected: 2 PASS (TestAbstractInterface), battery classes collect no tests yet.
Run: `.venv/bin/ruff check app/audience/ tests/unit/test_audience_datasource.py` — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/audience/ tests/unit/test_audience_datasource.py
git commit -m "feat: AudienceDataSource ABC + provider conformance battery (Phase 11a)"
```

---

### Task 3: SyntheticAudienceDataSource

**Files:**
- Modify: `app/demo_data/attribution.py:123` (publish `campaign_seed_config`; keep `_campaign_seed_config` alias)
- Create: `app/audience/synthetic.py`
- Test: `tests/unit/test_audience_datasource.py` (plug the battery in + equivalence test)

**Interfaces:**
- Consumes: `AudienceDataSource` (Task 2), `generate_frames`/`SeedConfig` from `app/demo_data/seed.py`, `campaign_seed_config`/`screens_for_campaign` from `app/demo_data/attribution.py`.
- Produces: `SyntheticAudienceDataSource()` (no-arg constructor) implementing `get_visit_intervals`. Task 4 registers it under `AppMode.DEMO`; Task 5's refactored join gets byte-identical data through it.

- [ ] **Step 1: Publish the seed-config helper**

In `app/demo_data/attribution.py`, rename `def _campaign_seed_config(` (line 123) to `def campaign_seed_config(`, update its one internal call site (line 158: `frames = generate_frames(_campaign_seed_config(...))` → `campaign_seed_config(...)`), and add directly below the function:

```python
# Historical import site (tests/unit/test_demo_attribution.py) — keep the
# underscore alias; app/audience/synthetic.py uses the public name.
_campaign_seed_config = campaign_seed_config
```

Run: `make test-unit` — Expected: all pass (alias keeps test_demo_attribution.py:127 working).

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_audience_datasource.py`:

```python
class TestSyntheticConformance(AudienceDataSourceContract):
    SCREEN_IDS_CAMPAIGN = 101

    @property
    def SCREEN_IDS(self):
        from app.demo_data.attribution import screens_for_campaign

        return screens_for_campaign(self.SCREEN_IDS_CAMPAIGN)

    def make_source(self):
        from app.audience.synthetic import SyntheticAudienceDataSource

        return SyntheticAudienceDataSource()


class TestSyntheticEquivalence:
    """The synthetic source is seed.py behind the seam — same rows exactly."""

    def test_intervals_equal_screen_visits_frame(self):
        from app.audience.synthetic import SyntheticAudienceDataSource
        from app.demo_data.attribution import campaign_seed_config, screens_for_campaign
        from app.demo_data.seed import generate_frames

        cid = 101
        screens = screens_for_campaign(cid)
        frames = generate_frames(campaign_seed_config(cid, D_FROM, D_TO))
        expected = sorted(
            (BlueZooVisitInterval(**row) for row in frames["screen_visits"]),
            key=lambda iv: (iv.screen_id, iv.timestamp),
        )
        got = SyntheticAudienceDataSource().get_visit_intervals(
            screen_ids=screens, date_from=D_FROM, date_to=D_TO
        )
        assert got == expected

    def test_subset_request_does_not_change_values(self):
        # Frames must be generated with the FULL campaign screen set, then
        # filtered — generating from a subset config could reseed values.
        from app.audience.synthetic import SyntheticAudienceDataSource
        from app.demo_data.attribution import screens_for_campaign

        screens = screens_for_campaign(101)
        full = SyntheticAudienceDataSource().get_visit_intervals(
            screen_ids=screens, date_from=D_FROM, date_to=D_TO
        )
        subset = SyntheticAudienceDataSource().get_visit_intervals(
            screen_ids=screens[:1], date_from=D_FROM, date_to=D_TO
        )
        assert subset == [iv for iv in full if iv.screen_id == screens[0]]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_audience_datasource.py -v`
Expected: `TestAbstractInterface` passes; every `TestSyntheticConformance`/`TestSyntheticEquivalence` test FAILS with `ModuleNotFoundError: No module named 'app.audience.synthetic'`.

- [ ] **Step 4: Implement the synthetic source**

Create `app/audience/synthetic.py`:

```python
"""SyntheticAudienceDataSource — seed.py behind the seam (Phase 11a).

Wraps the Phase 5 deterministic generator as-is: frames are generated with
the same campaign_seed_config the join built directly before this phase
(full campaign screen set, then filtered), so values are byte-identical.
Campaign context derives from the ws10 screen-id convention
(screen_id = ad_campaign_id * 100 + k) — the interface itself stays free
of synthetic-only parameters.
"""

from datetime import date

from ..demo_data.attribution import campaign_seed_config
from ..demo_data.seed import generate_frames
from ..models.attribution import BlueZooVisitInterval
from .datasource import AudienceDataSource


class SyntheticAudienceDataSource(AudienceDataSource):
    """Deterministic demo audience data, per-(screen, 15-min slot)."""

    def get_visit_intervals(
        self, *, screen_ids: list[int], date_from: date, date_to: date
    ) -> list[BlueZooVisitInterval]:
        wanted = set(screen_ids)
        out: list[BlueZooVisitInterval] = []
        for cid in sorted({sid // 100 for sid in wanted}):
            frames = generate_frames(campaign_seed_config(cid, date_from, date_to))
            out.extend(
                BlueZooVisitInterval(**row)
                for row in frames["screen_visits"]
                if row["screen_id"] in wanted
            )
        out.sort(key=lambda iv: (iv.screen_id, iv.timestamp))
        return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_audience_datasource.py -v`
Expected: all PASS (2 structural + 6 battery + 2 equivalence).
Run: `make test-unit` — Expected: all pass.
Run: `.venv/bin/ruff check app/audience/ app/demo_data/attribution.py tests/unit/test_audience_datasource.py` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/audience/synthetic.py app/demo_data/attribution.py tests/unit/test_audience_datasource.py
git commit -m "feat: SyntheticAudienceDataSource wrapping the Phase 5 generator"
```

---

### Task 4: Selection factory — APP_MODE wiring + fail-closed connected mode

**Files:**
- Modify: `app/audience/__init__.py` (full factory)
- Test: `tests/unit/test_audience_factory.py`

**Interfaces:**
- Consumes: `AppMode` + module attribute `APP_MODE` from `app/config.py` (read at call time so tests can monkeypatch `app.config.APP_MODE`); `SyntheticAudienceDataSource` (Task 3, resolved lazily by dotted path).
- Produces: `get_audience_datasource() -> AudienceDataSource` (singleton), `register_datasource_for_tests(source)`, `reset_audience_datasource()`. Task 5's join calls the getter; Phase 11b later adds an `AppMode.CONNECTED` registry entry.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_audience_factory.py`:

```python
"""APP_MODE → audience-source selection; Phase 6's fail-closed guard, built."""

import pytest

import app.config
from app.audience import (
    get_audience_datasource,
    register_datasource_for_tests,
    reset_audience_datasource,
)
from app.audience.synthetic import SyntheticAudienceDataSource
from app.config import AppMode


@pytest.fixture(autouse=True)
def _reset():
    reset_audience_datasource()
    yield
    reset_audience_datasource()


class TestDemoMode:
    def test_demo_resolves_to_synthetic(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        assert isinstance(get_audience_datasource(), SyntheticAudienceDataSource)

    def test_singleton_same_instance_across_calls(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        assert get_audience_datasource() is get_audience_datasource()


class TestConnectedFailsClosed:
    def test_connected_raises_specific_error(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)
        with pytest.raises(RuntimeError) as exc:
            get_audience_datasource()
        msg = str(exc.value)
        # Specific, actionable, honest — the Phase 6 deferred guard contract.
        assert "APP_MODE" in msg and "connected" in msg
        assert "Phase 11b" in msg
        assert "APP_MODE=demo" in msg

    def test_no_silent_fallback_to_demo(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)
        with pytest.raises(RuntimeError):
            get_audience_datasource()
        # And it stays closed on retry — no cached demo source snuck in.
        with pytest.raises(RuntimeError):
            get_audience_datasource()


class TestTestSeam:
    def test_override_bypasses_mode_resolution(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)

        class _Fake(SyntheticAudienceDataSource):
            pass

        fake = _Fake()
        register_datasource_for_tests(fake)
        assert get_audience_datasource() is fake  # even in connected mode

    def test_reset_clears_override_and_singleton(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        first = get_audience_datasource()
        register_datasource_for_tests(SyntheticAudienceDataSource())
        reset_audience_datasource()
        assert get_audience_datasource() is not first  # fresh singleton
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_audience_factory.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_audience_datasource' from 'app.audience'`

- [ ] **Step 3: Implement the factory**

Replace `app/audience/__init__.py` with:

```python
"""Audience data-source selection (Phase 11a).

APP_MODE is the only mode knob (Phase 6): demo → SyntheticAudienceDataSource;
connected → fail closed until Phase 11b lands the live BlueZoo conformer.

Ported from the donor factory's mechanics — lazy dotted-path registry,
thread-safe singleton, test-override seam — minus its traps: no GCS_BUCKET
coupling (the donor gated its BQ provider on an env var the provider never
used), no BigQuery-by-default, no reach-in to other services for seeding.
Entry-points packaging deliberately skipped (phase doc): the builtin dict
is the registry.
"""

import importlib
import threading

from ..config import AppMode
from .datasource import AudienceDataSource

__all__ = [
    "AudienceDataSource",
    "get_audience_datasource",
    "register_datasource_for_tests",
    "reset_audience_datasource",
]

# Phase 11b registers AppMode.CONNECTED here (its live/cached conformer).
# Until then, connected mode fails closed in _instantiate_for_mode().
_BUILTIN_SOURCES: dict[AppMode, str] = {
    AppMode.DEMO: "app.audience.synthetic:SyntheticAudienceDataSource",
}

_lock = threading.Lock()
_singleton: AudienceDataSource | None = None
_test_override: AudienceDataSource | None = None


def get_audience_datasource() -> AudienceDataSource:
    """Process-wide audience source, resolved from config.APP_MODE."""
    if _test_override is not None:
        return _test_override
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = _instantiate_for_mode()
    return _singleton


def _instantiate_for_mode() -> AudienceDataSource:
    from .. import config  # attribute read at call time: tests monkeypatch APP_MODE

    mode = config.APP_MODE
    dotted = _BUILTIN_SOURCES.get(mode)
    if dotted is None:
        # Phase 6's deferred fail-closed guard, now real: a clear, specific
        # error — never NotImplementedError, never a silent demo fallback.
        raise RuntimeError(
            f"APP_MODE={mode.value!r} requires the live BlueZoo audience "
            "adapter (Phase 11b), which is not implemented yet — no live "
            "data source or credentials are configured, and silently "
            "falling back to demo data is not allowed. Set APP_MODE=demo "
            "(or leave it unset) to use the synthetic demo source."
        )
    module_name, _, class_name = dotted.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    return cls()


def register_datasource_for_tests(source: AudienceDataSource) -> None:
    """Bypass mode resolution entirely — for tests only."""
    global _test_override
    _test_override = source


def reset_audience_datasource() -> None:
    """Clear singleton and test override (test isolation)."""
    global _singleton, _test_override
    with _lock:
        _singleton = None
        _test_override = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_audience_factory.py tests/unit/test_audience_datasource.py tests/unit/test_config.py -v`
Expected: all PASS.
Run: `.venv/bin/ruff check app/audience/ tests/unit/test_audience_factory.py` — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/audience/__init__.py tests/unit/test_audience_factory.py
git commit -m "feat: APP_MODE-keyed audience-source factory with fail-closed connected mode"
```

---

### Task 5: Route the join through the seam (golden-pinned refactor)

**Files:**
- Test: `tests/unit/test_seam_refactor_golden.py` (written and committed BEFORE the refactor)
- Modify: `app/demo_data/attribution.py:142-184` (`derive_rows_from_windows` reads via the seam)

**Interfaces:**
- Consumes: `get_audience_datasource()` (Task 4, imported inside the function — no top-level `demo_data → audience` import), `AudienceDataSource.get_visit_intervals` (Task 2).
- Produces: `derive_rows_from_windows(ad_campaign_id, video_ids, windows, date_from, date_to, source: AudienceDataSource | None = None)` — same return shape, byte-identical values; `source=None` resolves via the factory. `derive.py`'s facade signature stays untouched (its call flows through the new default).

- [ ] **Step 1: Capture golden output with CURRENT code**

Run:

```bash
.venv/bin/python - <<'EOF'
from datetime import date
from pprint import pprint
from app.demo_data.derive import derive_video_metrics_rows
rows = derive_video_metrics_rows(101, [1, 2], date(2026, 6, 1), date(2026, 6, 7))
assert rows, "fixture campaign must produce rows"
pprint(rows)
EOF
```

Expected: a non-empty list of dicts (video_id, metric_date, impressions, dwell_time_seconds, circulation, revenue). Copy the printed literal — it becomes `GOLDEN` in Step 2.

- [ ] **Step 2: Write the golden test (passes BEFORE the refactor)**

Create `tests/unit/test_seam_refactor_golden.py`:

```python
"""Refactor invariant: routing the join through AudienceDataSource must not
change a single derived value. GOLDEN was captured from the pre-seam code
(ws11a Task 5 Step 1) — if this test ever needs updating, the seam changed
demo data, which is a bug by definition in this workstream."""

from datetime import date

from app.demo_data.derive import derive_video_metrics_rows

GOLDEN = [
    # PASTE the exact pprint output from Step 1 here (list of row dicts).
]


def test_derive_output_is_byte_identical_to_pre_seam_capture():
    rows = derive_video_metrics_rows(101, [1, 2], date(2026, 6, 1), date(2026, 6, 7))
    assert rows == GOLDEN
```

(The `GOLDEN` placeholder comment MUST be replaced with the real captured literal — a plan-execution step, not a leave-in.)

Run: `.venv/bin/pytest tests/unit/test_seam_refactor_golden.py -v` — Expected: PASS (still pre-refactor).

Commit the pin:

```bash
git add tests/unit/test_seam_refactor_golden.py
git commit -m "test: golden pin of derive output ahead of seam refactor"
```

- [ ] **Step 3: Refactor derive_rows_from_windows**

In `app/demo_data/attribution.py`:

1. Extend the signature (line 142-148) with a trailing optional parameter:

```python
def derive_rows_from_windows(
    ad_campaign_id: int,
    video_ids: list,
    windows: list[dict],
    date_from: date,
    date_to: date,
    source=None,
) -> list[dict]:
```

2. Replace the two frame lines (158-159):

```python
    frames = generate_frames(campaign_seed_config(ad_campaign_id, date_from, date_to))
    visits_ix = {(v["screen_id"], v["timestamp"]): v for v in frames["screen_visits"]}
```

with:

```python
    if source is None:
        # Function-level import: app/audience imports app/demo_data (the
        # synthetic source wraps seed.py), so the reverse edge must not
        # exist at module import time.
        from ..audience import get_audience_datasource

        source = get_audience_datasource()
    intervals = source.get_visit_intervals(
        screen_ids=screens_for_campaign(ad_campaign_id),
        date_from=date_from,
        date_to=date_to,
    )
    visits_ix = {(iv.screen_id, iv.timestamp): iv for iv in intervals}
```

3. In the aggregation loop, switch the two dict accesses to attribute access (`v` is now a `BlueZooVisitInterval`):

```python
        a["inner"] += v.incoming_inner_count
        a["outer_out"] += v.outgoing_outer_count
```

4. Update the docstring's mention if it references frames directly, and drop now-unused imports if `generate_frames` is no longer referenced in this file (`campaign_seed_config` keeps using `SeedConfig`; `generate_frames` is still imported by `synthetic.py` from seed — remove the import here only if ruff flags it unused; `_seeded_rng` and `_slot_starts` stay, they're used elsewhere in the file).

5. Add a one-line note to the module docstring's determinism section: "Data now arrives via app/audience's AudienceDataSource (demo: seed.py behind the seam) — same values, same seeds."

- [ ] **Step 4: Run the golden test + full suite**

Run: `.venv/bin/pytest tests/unit/test_seam_refactor_golden.py -v` — Expected: PASS (byte-identical through the seam).
Run: `make test-unit` — Expected: ALL pass with zero test-file modifications (test_demo_attribution, test_review_tools, test_mock_data_attribution, test_metrics_tools all green).
Run: `make test-e2e` — Expected: pass.
Run: `.venv/bin/ruff check app/demo_data/attribution.py tests/unit/test_seam_refactor_golden.py` — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/demo_data/attribution.py
git commit -m "refactor: derive join reads visit intervals through AudienceDataSource"
```

---

### Task 6: Docstring corrections + owner demo guide

**Files:**
- Modify: `app/demo_data/seed.py:19-20` (docstring line only)
- Modify: `app/demo_data/constants.py:1-9` (docstring only)
- Modify: `.docs/version2-plan/demo_guide.md` (new APP_MODE part)

**Interfaces:**
- Consumes: the shipped behavior of Tasks 3-5 (synthetic-behind-seam; connected fail-closed).
- Produces: docs only — no code contract.

- [ ] **Step 1: seed.py docstring**

In `app/demo_data/seed.py`, replace the docstring line:

```
Deliberately import-light: stdlib + numpy only, no app modules, no DB — Phase 11a moves this file behind the AudienceProvider seam as-is.
```

with:

```
Deliberately import-light: stdlib + numpy only, no app modules, no DB — Phase 11a moved this file behind the AudienceDataSource seam as-is (app/audience/synthetic.py wraps it; nothing here changed).
```

(Exact current wording may wrap differently across lines 19-20 — preserve the file's wrapping style; only the sentence content changes.)

- [ ] **Step 2: constants.py docstring**

In `app/demo_data/constants.py`, update the docstring sentence claiming the donor duplicated `0.05` "in two places" to "in three places (two class attributes and a raw SQL literal)" — per the ws11a donor audit (`mock_inmemory.py:100`, `mock_bigquery.py:115`, `mock_bigquery.py:500`).

- [ ] **Step 3: demo_guide.md — APP_MODE part**

Add a new part to `.docs/version2-plan/demo_guide.md` (after the ws10 Part 0, matching its heading style), titled "Part 0b — What workstream 11a changed (APP_MODE now does something)". Content requirements:

- One paragraph: demo behavior is byte-identical by design (the seam refactor is invisible; all ws10 journeys still apply verbatim).
- Journey: **demo mode unchanged** — `make dev`, run any ws10 journey (e.g. 0.2 metrics check), expect identical numbers.
- Journey: **connected mode fails closed** — terminal check (no browser needed):

```bash
cd <worktree> && APP_MODE=connected .venv/bin/python -c \
  "from app.audience import get_audience_datasource; get_audience_datasource()"
```

Expected: `RuntimeError` whose message names `APP_MODE='connected'`, Phase 11b, and the `APP_MODE=demo` way back. Also note where this surfaces in the app: any flow that derives metrics (video activation, demo-data seeding) raises this error in connected mode — that's the fail-closed principle from Phase 6, deliberately not a silent demo fallback.
- Journey: **invalid APP_MODE still rejected at startup** — `APP_MODE=banana make dev` fails with the Phase 6 `ValueError` (unchanged behavior, listed so the owner knows the two errors are different layers).
- Update the guide's "what's fixed / what's deliberately not done" section: fixed = ws10 carried items 1+2 (empty-list guard, shared window loader); deliberately not done = 11b (live/cached conformers), carried items 3+4.

- [ ] **Step 4: Verify and commit**

Run: `make test-unit` — Expected: pass (docstring edits trigger the hook; nothing behavioral).
Run: `.venv/bin/ruff check app/demo_data/seed.py app/demo_data/constants.py` — Expected: clean.

```bash
git add app/demo_data/seed.py app/demo_data/constants.py .docs/version2-plan/demo_guide.md
git commit -m "docs: seam docstrings current + demo guide APP_MODE part (ws11a)"
```

---

### Task 7: Demo-scenario verification (verify phase)

Run per `verifying-with-demo-scenarios` (STATUS → `verify in progress` in the main checkout first; results append to WORK_LOG as checkpoint 5). Not a subagent-implementer task — the controller dispatches the `demo-scenario-verifier` per scenario, sequentially (port 8501).

- [ ] **Step 1:** `make reset-db` in the worktree, kill any stale :8501 server, start `make dev`.
- [ ] **Step 2:** Dispatch `demo-scenario-verifier` for `docs/demo-scenarios/fashion.md` **F3** (campaign metrics/RPI). Expected: PASS with values identical to ws10's run (byte-identical invariant, observed end-to-end).
- [ ] **Step 3:** Dispatch `demo-scenario-verifier` for **F4** (creatives comparison chart). Expected: PASS.
- [ ] **Step 4:** Connected-mode fail-closed smoke (scripted, no browser): run the demo_guide Part 0b terminal check from Task 6 Step 3. Expected: the specific RuntimeError. Capture output as evidence.
- [ ] **Step 5:** Append checkpoint 5 (scenarios, pass/fail, evidence paths) to WORK_LOG.md; commit.

---

## Self-Review

- **Spec coverage:** working-doc approach → Tasks 2-5 (interface, synthetic, factory+guard, join through seam); carried items 1+2 → Task 1; docstrings + demo_guide → Task 6; test plan (contract battery, factory tests, helper tests, unchanged-existing-tests invariant, F3/F4 + smoke) → Tasks 1-5 test steps + Task 7. QueryGuard/entry-points/BQ provider/11b: excluded by design (Out of scope).
- **Placeholder scan:** one deliberate execution-time fill — Task 5's `GOLDEN` literal, which by construction cannot be authored ahead of running the capture; the step marks it MUST-replace with the exact command that produces it. No other TBDs.
- **Type consistency:** `get_visit_intervals(*, screen_ids: list[int], date_from: date, date_to: date) -> list[BlueZooVisitInterval]` identical in Tasks 2 (ABC), 3 (impl), 5 (caller). Factory names (`get_audience_datasource`, `register_datasource_for_tests`, `reset_audience_datasource`) identical in Tasks 4 and 5. `load_attribution_windows(cursor, video_ids) -> list[dict]` identical in Task 1's helper, both rewires, and tests. `campaign_seed_config` public name introduced in Task 3 Step 1 and used in Task 3 tests/impl and Task 5 refactor.
