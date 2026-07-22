# Playout Attribution (Workstream 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `derive.py`'s invented per-video-per-day metrics with a real attribution chain: activation-driven `video_attribution` windows → deterministic `AdPlayRecord` schedules per (video, screen, day) → join against seed.py's sensor visit frames — while keeping `video_metrics`' table shape, both derive call sites' signatures, and ws07's per-creative RPI invariants intact.

**Architecture:** A new `video_attribution` SQLite table (ported donor-bridge shape, renamed keys) is opened/closed by the HITL tools (dual-write bridge). A new `app/demo_data/attribution.py` module expands windows into seeded 15-min play slots per (video, screen, day), joins plays to `screen_visits` inner counts for impressions, and computes revenue as play-visits × the surviving `video_rpi()` constant. `derive.py` becomes a thin signature-stable facade over that join. Campaigns get 2–3 deterministic screens, killing the 1:1 campaign-as-screen proxy. New client-contract DTOs (`AdPlayRecord`, `BlueZooVisitInterval`) live in `app/models/attribution.py`.

**Tech Stack:** Python 3.12, SQLite, numpy (seeded RNG via `seed._seeded_rng`), pydantic, pytest.

## Global Constraints

- **`app/demo_data/seed.py` is untouched** (owner kickoff note (a)). Feed it multi-screen `screen_ids` via its existing `SeedConfig` only.
- **`video_metrics` schema unchanged** (replan amendment 2): same 6 columns, same UNIQUE(video_id, metric_date). All 8 reader tools and `tests/unit/test_metrics_tools.py` must pass unmodified.
- **Naming: `ad_campaign_id`, never bare `campaign_id`, in all NEW code, tables, and DTOs** (replan amendment 1). Existing tables keep their legacy names.
- **`BlueZooVisitInterval` carries ONLY `sensor_visits` fields** (replan amendment): timestamp, screen_id, ad_campaign_id, the 4 in/out counts, the 6 min/max/avg visitor fields, valid. `extra="forbid"`.
- **No sub-15-min windows**: play slots are exactly seed.py's 15-min slots (`_slot_starts`, 48/day 09:00–21:00).
- **Per-creative RPI invariants (owner note (b))**: `video_rpi(ad_campaign_id, video_id)` keyed by exactly those two args, band [0.03, 0.07], `DEMO_RPI = 0.05` stays the single canonical constant, per-day revenue = `round(impressions * rpi, 2)`, so `compute_rpi` over any creative's rows recovers its constant.
- **Absoluteness**: deriving for `[101]` and for `[101, 102]` yields byte-identical rows for 101. Play schedules are seeded per (ad_campaign_id, video_id, screen_id, day) — never normalized across a campaign's videos. Slot collisions between two creatives on one screen are accepted (same deliberate ws05 trade-off as fractions summing > 1).
- **Impressions are inner-only** (`incoming_inner_count`). Never inner+outer (donor's double-count bug).
- **A `PostToolUse` hook runs `make test-unit` after every `app/**/*.py` edit.** In Task 4, the old `test_demo_derive.py` is replaced FIRST so the hook goes red only transiently within the task; every task ends green.
- **Stale-DB pitfall**: `test_db`/`shared_test_db` fixtures COPY the local `campaigns.db`, which may predate the new table. Task 2 deletes the local `campaigns.db` so the next test run rebuilds it with the table. All new-table tests use `fresh_test_db`.
- Lint with `make lint` before each commit; no `Co-Authored-By: Claude` (or any AI-attribution) trailers in commits.
- `README.md` and `DEMO_GUIDE.md` untouched.

## File Structure

- Create: `app/models/attribution.py` — client-contract DTOs (Task 1)
- Modify: `app/models/__init__.py` — export the DTOs (Task 1)
- Create: `tests/unit/test_attribution_models.py` (Task 1)
- Modify: `app/database/db.py` — `video_attribution` table + indexes + reset drop (Task 2)
- Create: `tests/unit/test_video_attribution_table.py` (Task 2)
- Create: `app/demo_data/attribution.py` — screens, slot schedule, plays, join (Tasks 3–4)
- Create: `tests/unit/test_demo_attribution.py` (Tasks 3–4)
- Rewrite: `app/demo_data/derive.py` — facade; Delete: `tests/unit/test_demo_derive.py` (Task 4)
- Modify: `app/demo_data/__init__.py` — docstring (Task 4)
- Modify: `app/tools/review_tools.py` — bridge + windows-aware `_insert_derived_metrics` (Task 5)
- Modify: `tests/unit/test_review_tools.py` — bridge tests (Task 5)
- Modify: `app/database/mock_data.py` — seed windows on bulk path (Task 6)
- Create: `tests/unit/test_mock_data_attribution.py` (Task 6)
- Modify: `docs/METRICS.md`, `app/demo_data/BLUEZOO_MAPPING.md`, `docs/demo-scenarios/fashion.md`, `.docs/version2-plan/demo_guide.md` (Task 7)

---

### Task 1: Client-contract DTOs

**Files:**
- Create: `app/models/attribution.py`
- Modify: `app/models/__init__.py`
- Test: `tests/unit/test_attribution_models.py`

**Interfaces:**
- Consumes: nothing (pure pydantic).
- Produces: `AdPlayRecord(screen_id: int, ad_campaign_id: int, video_id: int, ad_name: str | None, product_ids: list[int], start: datetime, end: datetime)` and `BlueZooVisitInterval` (the 13 `sensor_visits` fields, `extra="forbid"`). Task 3's `expand_ad_plays` returns `list[AdPlayRecord]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_attribution_models.py`:

```python
"""Tests for the Phase 10 client-contract DTOs (Email 5 shapes)."""

from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo_data.seed import SeedConfig, generate_frames
from app.models.attribution import AdPlayRecord, BlueZooVisitInterval


class TestAdPlayRecord:
    def test_minimal_construction_and_defaults(self):
        rec = AdPlayRecord(
            screen_id=900101,
            ad_campaign_id=9001,
            video_id=101,
            start=datetime(2026, 6, 1, 9, 0),
            end=datetime(2026, 6, 1, 9, 15),
        )
        assert rec.ad_name is None
        assert rec.product_ids == []
        assert rec.end - rec.start == timedelta(minutes=15)


class TestBlueZooVisitInterval:
    def test_validates_seed_screen_visits_rows_verbatim(self):
        """The DTO must accept seed.py's screen_visits rows as-is — that is
        the whole point of the seam (Phase 11 swaps the producer, not the
        shape)."""
        cfg = SeedConfig(
            screen_ids=[900101, 900102],
            campaigns=[(9001, "campaign-9001", date(2026, 6, 1), date(2026, 6, 2), 1.0)],
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 2),
        )
        rows = generate_frames(cfg)["screen_visits"]
        assert len(rows) == 2 * 2 * 48  # 2 days x 2 screens x 48 slots
        for row in rows:
            interval = BlueZooVisitInterval.model_validate(row)
            assert interval.screen_id in (900101, 900102)
            assert interval.valid is True
            assert interval.ad_campaign_id == 9001

    def test_rejects_fields_outside_sensor_visits_scope(self):
        """Replan amendment: the interval is scoped to sensor_visits fields
        ONLY — extra keys must fail, not silently pass through."""
        cfg = SeedConfig(
            screen_ids=[900101],
            campaigns=[(9001, "c", date(2026, 6, 1), date(2026, 6, 1), 1.0)],
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 1),
        )
        row = dict(generate_frames(cfg)["screen_visits"][0])
        row["dwell_histogram"] = [1, 2, 3]
        with pytest.raises(ValidationError):
            BlueZooVisitInterval.model_validate(row)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_attribution_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.attribution'`

- [ ] **Step 3: Write the implementation**

Create `app/models/attribution.py`:

```python
"""Client-contract DTOs for playout attribution (Phase 10).

AdPlayRecord mirrors the client's CMS end-of-day batch record (Email 5,
project_context.md): which ad played on which screen, when, advertising
which products. BlueZooVisitInterval mirrors ONE row of BlueZoo's
sensor_visits — and nothing else (replan amendment: scoped to sensor_visits
fields only; extra="forbid" enforces it). In demo mode both shapes are
produced deterministically (app/demo_data/attribution.py, seed.py); Phase 11
connected mode fills the same shapes from the real CMS/BlueZoo feeds.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdPlayRecord(BaseModel):
    """One playout of one creative on one screen for one 15-min slot."""

    screen_id: int
    ad_campaign_id: int
    video_id: int
    ad_name: str | None = None
    product_ids: list[int] = Field(default_factory=list)
    start: datetime
    end: datetime


class BlueZooVisitInterval(BaseModel):
    """One sensor_visits row: visit counts at one screen for one 15-min slot."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    screen_id: int
    ad_campaign_id: int | None = None
    incoming_inner_count: float
    outgoing_inner_count: float
    incoming_outer_count: float
    outgoing_outer_count: float
    minimum_visitors_inner: float
    maximum_visitors_inner: float
    average_visitors_inner: float
    minimum_visitors_outer: float
    maximum_visitors_outer: float
    average_visitors_outer: float
    valid: bool = True
```

In `app/models/__init__.py`, extend the existing import block and `__all__`:

```python
from .attribution import AdPlayRecord, BlueZooVisitInterval
from .video_properties import (
    VideoProperties,
    MoodType,
    VisualStyle,
    EnergyLevel,
    ColorTemperature,
    AudioType,
)

__all__ = [
    "AdPlayRecord",
    "BlueZooVisitInterval",
    "VideoProperties",
    "MoodType",
    "VisualStyle",
    "EnergyLevel",
    "ColorTemperature",
    "AudioType",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_attribution_models.py -v`
Expected: 3 PASS

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add app/models/attribution.py app/models/__init__.py tests/unit/test_attribution_models.py
git commit -m "feat(ws10): AdPlayRecord + BlueZooVisitInterval client-contract DTOs"
```

---

### Task 2: `video_attribution` table

**Files:**
- Modify: `app/database/db.py` (table in `init_database`, index, drop in `reset_database`)
- Test: `tests/unit/test_video_attribution_table.py`

**Interfaces:**
- Produces: table `video_attribution(id, video_id, ad_campaign_id, screen_id, active_from NOT NULL, active_to NULL)`. Open window = `active_to IS NULL`. Tasks 5–6 write it; Task 5 reads it into the join.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_video_attribution_table.py`:

```python
"""Schema + open/close semantics for the video_attribution windows table."""

from app.database.db import get_db_cursor


class TestVideoAttributionTable:
    def test_schema(self, fresh_test_db):
        with get_db_cursor() as cursor:
            cursor.execute("PRAGMA table_info(video_attribution)")
            cols = {row[1] for row in cursor.fetchall()}
        assert cols == {
            "id",
            "video_id",
            "ad_campaign_id",
            "screen_id",
            "active_from",
            "active_to",
        }

    def test_open_close_roundtrip(self, fresh_test_db):
        with get_db_cursor() as cursor:
            cursor.execute("SELECT id FROM campaign_videos LIMIT 1")
            video_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO video_attribution
                (video_id, ad_campaign_id, screen_id, active_from, active_to)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (video_id, 1, 101, "2026-06-01T00:00:00"),
            )
            cursor.execute(
                "SELECT COUNT(*) AS n FROM video_attribution "
                "WHERE video_id = ? AND active_to IS NULL",
                (video_id,),
            )
            assert cursor.fetchone()["n"] == 1
            cursor.execute(
                "UPDATE video_attribution SET active_to = ? "
                "WHERE video_id = ? AND active_to IS NULL",
                ("2026-06-15T00:00:00", video_id),
            )
            cursor.execute(
                "SELECT COUNT(*) AS n FROM video_attribution "
                "WHERE video_id = ? AND active_to IS NULL",
                (video_id,),
            )
            assert cursor.fetchone()["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_video_attribution_table.py -v`
Expected: FAIL with `sqlite3.OperationalError: no such table: video_attribution`

- [ ] **Step 3: Add the table to `db.py`**

In `init_database()`, directly after the `video_metrics` CREATE TABLE block (after the statement ending `UNIQUE(video_id, metric_date)\n        )\n    ''')`), insert:

```python
    # Playout-attribution windows (Phase 10): which video was live on which
    # screen, from when to when. Open window = active_to IS NULL. Written by
    # the HITL dual-write bridge (activate/pause/archive) and the seed-time
    # bulk path; read by the ad-play join. Ported from the donor repo's
    # video_attribution with store_id->screen_id, campaign_id->ad_campaign_id.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_attribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            ad_campaign_id INTEGER NOT NULL,
            screen_id INTEGER NOT NULL,
            active_from TIMESTAMP NOT NULL,
            active_to TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES campaign_videos(id) ON DELETE CASCADE
        )
    ''')
```

In the base-index block (next to `idx_video_metrics_video`), add:

```python
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_attribution_video ON video_attribution(video_id)')
```

In `reset_database()`, add above the `video_metrics` drop:

```python
    cursor.execute('DROP TABLE IF EXISTS video_attribution')
```

- [ ] **Step 4: Clear the stale local DB so test copies include the table**

```bash
rm -f campaigns.db
```

(`_ensure_main_db_exists()` rebuilds it with the new schema on the next test run; `make dev` does the same at startup. Existing dev DBs elsewhere get the table via `CREATE TABLE IF NOT EXISTS` at startup.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_video_attribution_table.py -v && make test-unit`
Expected: 2 PASS, full unit suite green.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add app/database/db.py tests/unit/test_video_attribution_table.py
git commit -m "feat(ws10): video_attribution windows table (ported bridge shape, renamed keys)"
```

---

### Task 3: Screens roster and deterministic play schedule

**Files:**
- Create: `app/demo_data/attribution.py` (schedule half; the join lands in Task 4)
- Test: `tests/unit/test_demo_attribution.py` (schedule tests; Task 4 appends the join tests)

**Interfaces:**
- Consumes: `seed._seeded_rng`, `seed._slot_starts`, `AdPlayRecord` (Task 1).
- Produces (Task 4 and 5 rely on these exact signatures):
  - `screens_for_campaign(ad_campaign_id: int) -> list[int]` — 2–3 deterministic screen ids, `ad_campaign_id * 100 + k`.
  - `slot_budget(ad_campaign_id: int, video_id, screen_id: int) -> int` — stable slots/day in [10, 22].
  - `expand_ad_plays(ad_campaign_id: int, windows: list[dict], date_from: date, date_to: date) -> list[AdPlayRecord]` — windows are dicts with keys `video_id`, `screen_id`, `active_from: datetime`, `active_to: datetime | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_demo_attribution.py`:

```python
"""Tests for the Phase 10 ad-play attribution join (replaces test_demo_derive.py)."""

from datetime import date, datetime, timedelta

from app.demo_data.attribution import (
    expand_ad_plays,
    screens_for_campaign,
    slot_budget,
)

CID = 9001
D_FROM = date(2026, 6, 1)
D_TO = date(2026, 6, 7)


def _open_windows(video_ids, screens, active_from_date=D_FROM):
    return [
        {
            "video_id": vid,
            "screen_id": sid,
            "active_from": datetime.combine(active_from_date, datetime.min.time()),
            "active_to": None,
        }
        for vid in video_ids
        for sid in screens
    ]


class TestScreensRoster:
    def test_two_to_three_screens_decoupled_from_campaign_id(self):
        for cid in (1, 2, 3, 9001, 424242):
            screens = screens_for_campaign(cid)
            assert 2 <= len(screens) <= 3
            assert cid not in screens  # the 1:1 campaign-as-screen proxy is dead
            assert len(set(screens)) == len(screens)
            assert screens == screens_for_campaign(cid)  # deterministic

    def test_rosters_vary_in_size_across_campaigns(self):
        sizes = {len(screens_for_campaign(cid)) for cid in range(1, 40)}
        assert sizes == {2, 3}


class TestPlaySchedule:
    def test_slot_budget_band_and_determinism(self):
        for vid in (101, 102, 999):
            k = slot_budget(CID, vid, screens_for_campaign(CID)[0])
            assert 10 <= k <= 22
            assert k == slot_budget(CID, vid, screens_for_campaign(CID)[0])

    def test_plays_are_15min_aligned_within_open_hours(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_FROM)
        assert plays, "an open window must produce plays"
        for p in plays:
            assert p.ad_campaign_id == CID
            assert p.video_id == 101
            assert p.screen_id in screens
            assert p.end - p.start == timedelta(minutes=15)
            assert p.start.minute % 15 == 0
            assert 9 <= p.start.hour < 21

    def test_daily_play_count_matches_slot_budget(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_FROM)
        per_screen = {}
        for p in plays:
            per_screen[p.screen_id] = per_screen.get(p.screen_id, 0) + 1
        for sid in screens:
            assert per_screen[sid] == slot_budget(CID, 101, sid)

    def test_no_duplicate_slots_per_video_screen_day(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_TO)
        keys = [(p.screen_id, p.start) for p in plays]
        assert len(keys) == len(set(keys))

    def test_window_clamps_days(self):
        """Plays exist only on days the window covers."""
        screens = screens_for_campaign(CID)
        w = [
            {
                "video_id": 101,
                "screen_id": screens[0],
                "active_from": datetime.combine(D_FROM + timedelta(days=2), datetime.min.time()),
                "active_to": datetime.combine(D_FROM + timedelta(days=4), datetime.min.time()),
            }
        ]
        plays = expand_ad_plays(CID, w, D_FROM, D_TO)
        days = {p.start.date() for p in plays}
        assert days == {D_FROM + timedelta(days=2), D_FROM + timedelta(days=3), D_FROM + timedelta(days=4)}

    def test_schedule_is_absolute_per_video(self):
        """Adding a second video's windows never changes the first video's plays."""
        screens = screens_for_campaign(CID)
        solo = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_TO)
        both = [
            p
            for p in expand_ad_plays(CID, _open_windows([101, 102], screens), D_FROM, D_TO)
            if p.video_id == 101
        ]
        assert solo == both
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_demo_attribution.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.demo_data.attribution'`

- [ ] **Step 3: Write the implementation**

Create `app/demo_data/attribution.py`:

```python
"""Deterministic playout-attribution join (Phase 10).

The causal chain the demo now tells truthfully:

    video_attribution windows (who was live, on which screen, when)
      -> AdPlayRecord schedule (seeded 15-min play slots per video/screen/day)
      -> join vs seed.py's screen_visits (inner counts only -> impressions)
      -> revenue = play visits x video_rpi (the demo stand-in for the PoS
         revenue lookup by product + time window)
      -> daily aggregation -> the same video_metrics rows as before.

Determinism rules (all sha256-seeded via seed._seeded_rng):
- screens_for_campaign: 2-3 screens per campaign's store; screen_id is
  ad_campaign_id * 100 + k, never the campaign id itself (the ws05 1:1
  campaign-as-screen proxy is gone).
- Play schedules are ABSOLUTE per (ad_campaign_id, video_id, screen_id, day):
  activating another creative later never changes existing videos' plays.
  Two creatives may collide on a slot — same deliberate trade-off as ws05's
  fractions summing > 1 (history immutability beats physical exclusivity).
- video_rpi survives from ws07 unchanged: per-(campaign, video), band
  [0.03, 0.07], day- and screen-independent, so each creative's
  revenue/impressions stays one checkable constant.

dwell_time_seconds stays a synthetic scalar and circulation stays an
outgoing_outer-derived convention (now summed over played slots) — real
semantics are Phase 11's (docs/METRICS.md).
"""

from datetime import date, datetime, timedelta

from ..models.attribution import AdPlayRecord
from .constants import DEMO_RPI
from .seed import SeedConfig, _seeded_rng, _slot_starts, generate_frames

SLOTS_PER_DAY = 48  # seed.py's grain: 15-min slots, 09:00-21:00
SLOT_MINUTES = 15


def screens_for_campaign(ad_campaign_id: int) -> list[int]:
    """2-3 deterministic screens for the campaign's store.

    IDs are ad_campaign_id * 100 + k — stable, collision-free across
    campaigns, and never equal to the campaign id. Phase 11 maps real
    BlueZoo sensor ids onto this roster."""
    rng = _seeded_rng("screens", ad_campaign_id)
    n = 2 + int(rng.uniform() < 0.5)
    return [ad_campaign_id * 100 + k for k in range(1, n + 1)]


def campaign_uplift(ad_campaign_id: int) -> float:
    """Deterministic per-campaign performance uplift in [0.7, 1.4].

    (Moved from derive.py; unchanged. Phase 15's onboarding relies on any
    campaign id getting a plausible, stable value.)"""
    rng = _seeded_rng("uplift", ad_campaign_id)
    return float(round(0.7 + rng.uniform() * 0.7, 2))


def video_rpi(ad_campaign_id: int, video_id) -> float:
    """Deterministic per-(campaign, video) RPI in [0.03, 0.07].

    (Moved from derive.py; unchanged — ws07 owner decision. DEMO_RPI x a
    seeded factor in [0.6, 1.4], constant across days and screens: each
    creative's revenue/impressions ratio stays ONE checkable constant.)"""
    rng = _seeded_rng("rpi", ad_campaign_id, video_id)
    return float(round(DEMO_RPI * (0.6 + rng.uniform() * 0.8), 4))


def slot_budget(ad_campaign_id: int, video_id, screen_id: int) -> int:
    """Stable number of 15-min slots/day this creative plays on this screen.

    20-45% of the 48 daily slots — the schedule-world successor of ws05's
    video_fraction band. WHICH slots vary per day; how MANY does not."""
    rng = _seeded_rng("slot-budget", ad_campaign_id, video_id, screen_id)
    return int(round(SLOTS_PER_DAY * (0.20 + rng.uniform() * 0.25)))


def _window_covers(window: dict, d: date) -> bool:
    """Day-granularity clamp (windows store datetimes; demo grain is a day)."""
    if window["active_from"].date() > d:
        return False
    active_to = window.get("active_to")
    return active_to is None or d <= active_to.date()


def _plays_for_day(
    ad_campaign_id: int, video_id, screen_id: int, d: date
) -> list[AdPlayRecord]:
    k = slot_budget(ad_campaign_id, video_id, screen_id)
    rng = _seeded_rng("plays", ad_campaign_id, video_id, screen_id, d.isoformat())
    slots = sorted(rng.choice(SLOTS_PER_DAY, size=k, replace=False).tolist())
    starts = _slot_starts(d)
    return [
        AdPlayRecord(
            screen_id=screen_id,
            ad_campaign_id=ad_campaign_id,
            video_id=video_id,
            start=starts[i],
            end=starts[i] + timedelta(minutes=SLOT_MINUTES),
        )
        for i in slots
    ]


def expand_ad_plays(
    ad_campaign_id: int, windows: list[dict], date_from: date, date_to: date
) -> list[AdPlayRecord]:
    """Expand attribution windows into the deterministic play schedule.

    windows: dicts with video_id, screen_id, active_from (datetime),
    active_to (datetime | None; None = still live). Plays are emitted for
    every day in [date_from, date_to] each window covers."""
    plays: list[AdPlayRecord] = []
    for w in windows:
        d = date_from
        while d <= date_to:
            if _window_covers(w, d):
                plays.extend(_plays_for_day(ad_campaign_id, w["video_id"], w["screen_id"], d))
            d += timedelta(days=1)
    return plays
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_demo_attribution.py -v && make test-unit`
Expected: 8 PASS; full suite still green (nothing imports the new module yet).

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add app/demo_data/attribution.py tests/unit/test_demo_attribution.py
git commit -m "feat(ws10): deterministic screens roster and ad-play schedule"
```

---

### Task 4: The join, and derive.py as a facade

**Files:**
- Modify: `app/demo_data/attribution.py` (append `_campaign_seed_config`, `derive_rows_from_windows`)
- Rewrite: `app/demo_data/derive.py`
- Modify: `app/demo_data/__init__.py` (docstring line for derive.py)
- Delete: `tests/unit/test_demo_derive.py`
- Modify: `tests/unit/test_demo_attribution.py` (append join tests)

**Interfaces:**
- Consumes: Task 3's `screens_for_campaign`, `expand_ad_plays`, `slot_budget`, `video_rpi`, `campaign_uplift`; seed's `generate_frames`, `SeedConfig`, `_seeded_rng`.
- Produces:
  - `attribution.derive_rows_from_windows(ad_campaign_id: int, video_ids: list, windows: list[dict], date_from: date, date_to: date) -> list[dict]` — rows carry exactly the `video_metrics` insert columns (`video_id`, `metric_date` ISO str, `impressions` int, `dwell_time_seconds` float, `circulation` int, `revenue` float). Only windows whose `video_id` is in `video_ids` contribute.
  - `derive.derive_video_metrics_rows(ad_campaign_id, video_ids, date_from, date_to, windows=None)` — same 4-positional-arg signature both call sites use today; new optional `windows`; for any video in `video_ids` with no window in `windows`, synthesizes open windows from `date_from` on all campaign screens (back-compat + bulk convenience).
  - `derive` re-exports `campaign_uplift` and `video_rpi` from `attribution`.

- [ ] **Step 1: Replace the old test file (hook goes red only inside this task)**

```bash
git rm tests/unit/test_demo_derive.py
```

Append to `tests/unit/test_demo_attribution.py` (extend the existing imports):

```python
from app.demo_data.attribution import derive_rows_from_windows, video_rpi
from app.demo_data.constants import DEMO_RPI, DEMO_WINDOW_DAYS
from app.demo_data.derive import derive_video_metrics_rows
from app.tools.metrics_shared import compute_rpi


class TestConstants:
    def test_canonical_values(self):
        assert DEMO_RPI == 0.05
        assert DEMO_WINDOW_DAYS == 30


class TestJoinDerivation:
    def test_one_row_per_video_per_day(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        assert len(rows) == 2 * 7
        dates = {r["metric_date"] for r in rows}
        assert min(dates) == D_FROM.isoformat()
        assert max(dates) == D_TO.isoformat()

    def test_impressions_are_played_slot_inner_visits_only(self):
        """impressions = sum of incoming_inner_count over the video's played
        slots — computed independently here from the schedule + frames. An
        inner+outer computation (the donor's bug) must NOT match."""
        from app.demo_data.attribution import _campaign_seed_config
        from app.demo_data.seed import generate_frames

        screens = screens_for_campaign(CID)
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_FROM)
        frames = generate_frames(_campaign_seed_config(CID, D_FROM, D_FROM))
        ix = {(v["screen_id"], v["timestamp"]): v for v in frames["screen_visits"]}
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_FROM)
        inner = sum(ix[(p.screen_id, p.start)]["incoming_inner_count"] for p in plays)
        both = sum(
            ix[(p.screen_id, p.start)]["incoming_inner_count"]
            + ix[(p.screen_id, p.start)]["incoming_outer_count"]
            for p in plays
        )
        assert rows[0]["impressions"] == int(round(inner))
        assert rows[0]["impressions"] != int(round(both))

    def test_revenue_uses_per_creative_rpi(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        for r in rows:
            assert r["revenue"] == round(r["impressions"] * video_rpi(CID, r["video_id"]), 2)

    def test_video_rpi_band_determinism_and_divergence(self):
        for vid in (101, 102, 999):
            factor = video_rpi(CID, vid)
            assert 0.03 <= factor <= 0.07
            assert factor == video_rpi(CID, vid)
        assert video_rpi(CID, 101) != video_rpi(CID, 102)

    def test_window_rpi_matches_creative_constant(self):
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        total_rev = sum(r["revenue"] for r in rows)
        total_imp = sum(r["impressions"] for r in rows)
        assert abs(compute_rpi(total_rev, total_imp) - video_rpi(CID, 101)) < 0.001

    def test_per_video_schedules_differ(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_FROM)
        by_video = {r["video_id"]: r["impressions"] for r in rows}
        assert by_video[101] != by_video[102]

    def test_later_activation_never_changes_existing_rows(self):
        solo = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
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

    def test_windows_are_load_bearing(self):
        """A window covering only part of the range yields rows ONLY for the
        covered days — metrics accrue where the video was actually live."""
        screens = screens_for_campaign(CID)
        w = [
            {
                "video_id": 101,
                "screen_id": sid,
                "active_from": datetime.combine(D_FROM, datetime.min.time()),
                "active_to": datetime.combine(D_FROM + timedelta(days=2), datetime.min.time()),
            }
            for sid in screens
        ]
        rows = derive_rows_from_windows(CID, [101], w, D_FROM, D_TO)
        days = {r["metric_date"] for r in rows}
        assert days == {(D_FROM + timedelta(days=i)).isoformat() for i in range(3)}

    def test_more_screens_more_impressions(self):
        screens = screens_for_campaign(CID)
        one = derive_rows_from_windows(
            CID, [101], _open_windows([101], screens[:1]), D_FROM, D_FROM
        )
        all_screens = derive_rows_from_windows(
            CID, [101], _open_windows([101], screens), D_FROM, D_FROM
        )
        assert all_screens[0]["impressions"] > one[0]["impressions"]

    def test_dwell_is_synthetic_seconds_scale(self):
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        for r in rows:
            assert 4.0 <= r["dwell_time_seconds"] <= 12.0

    def test_plausible_magnitudes(self):
        """Charts stay sane: per-video daily impressions in the
        hundreds-to-low-thousands, circulation positive."""
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        for r in rows:
            assert 200 <= r["impressions"] <= 8000
            assert r["circulation"] > 0
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/unit/test_demo_attribution.py -v`
Expected: schedule tests PASS; join tests FAIL with `ImportError: cannot import name 'derive_rows_from_windows'`.

- [ ] **Step 3: Append the join to `app/demo_data/attribution.py`**

```python
def _campaign_seed_config(ad_campaign_id: int, date_from: date, date_to: date) -> SeedConfig:
    """One campaign across its real 2-3 screens (the ws05 1:1
    campaign-as-screen proxy is gone)."""
    return SeedConfig(
        screen_ids=screens_for_campaign(ad_campaign_id),
        campaigns=[
            (
                ad_campaign_id,
                f"campaign-{ad_campaign_id}",
                date_from,
                date_to,
                campaign_uplift(ad_campaign_id),
            )
        ],
        date_from=date_from,
        date_to=date_to,
    )


def derive_rows_from_windows(
    ad_campaign_id: int,
    video_ids: list,
    windows: list[dict],
    date_from: date,
    date_to: date,
) -> list[dict]:
    """The ad-play join: windows -> plays -> visits/revenue -> daily rows.

    impressions = summed incoming_inner_count over the video's played slots
    (inner-only — outer is ~100 m passersby, never impressions).
    revenue = impressions x video_rpi(campaign, video) — the demo stand-in
    for the PoS revenue lookup, coupled to the play schedule so each
    creative's RPI stays its ws07 constant.
    Returned dicts carry exactly the video_metrics insert columns."""
    wanted = set(video_ids)
    frames = generate_frames(_campaign_seed_config(ad_campaign_id, date_from, date_to))
    visits_ix = {(v["screen_id"], v["timestamp"]): v for v in frames["screen_visits"]}

    plays = expand_ad_plays(
        ad_campaign_id, [w for w in windows if w["video_id"] in wanted], date_from, date_to
    )

    agg: dict = {}
    for p in plays:
        v = visits_ix.get((p.screen_id, p.start))
        if v is None:
            continue
        a = agg.setdefault((p.video_id, p.start.date()), {"inner": 0.0, "outer_out": 0.0})
        a["inner"] += v["incoming_inner_count"]
        a["outer_out"] += v["outgoing_outer_count"]

    order = {vid: i for i, vid in enumerate(video_ids)}
    rows = []
    for video_id, d in sorted(agg, key=lambda key: (key[1], order.get(key[0], 0))):
        a = agg[(video_id, d)]
        impressions = int(round(a["inner"]))
        rpi = video_rpi(ad_campaign_id, video_id)
        dwell_rng = _seeded_rng("dwell-scalar", ad_campaign_id, video_id, d.isoformat())
        rows.append(
            {
                "video_id": video_id,
                "metric_date": d.isoformat(),
                "impressions": impressions,
                # Synthetic seconds-scale scalar — see module docstring.
                "dwell_time_seconds": float(round(4.0 + dwell_rng.uniform() * 8.0, 1)),
                "circulation": int(round(a["outer_out"])),
                "revenue": round(impressions * rpi, 2),
            }
        )
    return rows
```

- [ ] **Step 4: Rewrite `app/demo_data/derive.py`** (full replacement — `video_fraction` and the old `_campaign_seed_config` die here):

```python
"""Signature-stable facade over the Phase 10 ad-play join.

Kept so both historical call sites (review_tools._insert_derived_metrics,
mock_data seed-time bulk generation) and any older DB keep working: callers
that pass real attribution windows get the honest join; callers that don't
get synthesized always-open windows across the campaign's screens — the
same rows the join produces for a video live all range on every screen.

The per-video-per-day INVENTIONS that used to live here are gone:
video_fraction is replaced by the deterministic play schedule
(attribution.slot_budget + expand_ad_plays), and the 1:1 campaign-as-screen
proxy by attribution.screens_for_campaign. campaign_uplift and video_rpi
moved to attribution.py (re-exported here unchanged).
"""

from datetime import date, datetime

from .attribution import (
    campaign_uplift,  # noqa: F401  (re-export: historical import site)
    derive_rows_from_windows,
    screens_for_campaign,
    video_rpi,  # noqa: F401  (re-export: historical import site)
)


def derive_video_metrics_rows(
    ad_campaign_id: int,
    video_ids: list,
    date_from: date,
    date_to: date,
    windows: list[dict] | None = None,
) -> list[dict]:
    """One video_metrics row per (video, day covered by a window), via the
    ad-play join. Videos with no window in `windows` get synthesized
    always-open windows from date_from on all campaign screens."""
    windows = list(windows or [])
    have = {w["video_id"] for w in windows}
    screens = screens_for_campaign(ad_campaign_id)
    for video_id in video_ids:
        if video_id not in have:
            for screen_id in screens:
                windows.append(
                    {
                        "video_id": video_id,
                        "screen_id": screen_id,
                        "active_from": datetime.combine(date_from, datetime.min.time()),
                        "active_to": None,
                    }
                )
    return derive_rows_from_windows(ad_campaign_id, video_ids, windows, date_from, date_to)
```

- [ ] **Step 5: Update the package docstring** — in `app/demo_data/__init__.py`, replace the line

```
derive.py   - disposable frames -> video_metrics derivation (Phase 10 deletes it)
```

with

```
attribution.py - ad-play join: windows -> plays -> video_metrics rows (Phase 10)
derive.py   - signature-stable facade over attribution.py's join
```

- [ ] **Step 6: Run the full unit suite**

Run: `make test-unit`
Expected: ALL PASS — including `test_review_tools.py` (facade-synthesized windows match what activation will write in Task 5: same screens, full-range coverage) and `test_metrics_tools.py` untouched.

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add app/demo_data/attribution.py app/demo_data/derive.py app/demo_data/__init__.py tests/unit/test_demo_attribution.py
git rm -q --cached tests/unit/test_demo_derive.py 2>/dev/null || true
git commit -m "feat(ws10): ad-play join; derive.py becomes signature-stable facade"
```

---

### Task 5: Dual-write bridge in review_tools

**Files:**
- Modify: `app/tools/review_tools.py`
- Test: `tests/unit/test_review_tools.py` (append a class)

**Interfaces:**
- Consumes: `screens_for_campaign` (Task 3), `video_attribution` table (Task 2), `derive_video_metrics_rows(..., windows=)` (Task 4).
- Produces: `_open_attribution_windows(cursor, video_id, ad_campaign_id, active_from: datetime) -> int`, `_close_attribution_windows(cursor, video_id, active_to: datetime) -> int`, `_load_attribution_windows(cursor, video_ids) -> list[dict]`. Task 6 replicates `_load_attribution_windows`' 4-line query inline (mock_data must not import from app.tools).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_review_tools.py`:

```python
class TestAttributionBridge:
    """Phase 10 dual-write bridge: activation opens video_attribution
    windows, pause/archive close them, and metrics derive through them."""

    def _make_generated_video(self):
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS campaign_id, p.id AS product_id "
                "FROM campaigns c, products p LIMIT 1"
            )
            row = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO campaign_videos
                (campaign_id, product_id, video_filename, status)
                VALUES (?, ?, ?, 'generated')
                """,
                (row["campaign_id"], row["product_id"], "bridge-test-video.mp4"),
            )
            return cursor.lastrowid, row["campaign_id"]

    def _windows(self, video_id):
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT screen_id, active_from, active_to FROM video_attribution "
                "WHERE video_id = ? ORDER BY screen_id",
                (video_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def test_activate_opens_one_window_per_screen(self, fresh_test_db):
        from datetime import date, timedelta

        from app.database.db import get_db_cursor, get_demo_anchor_date
        from app.demo_data.attribution import screens_for_campaign
        from app.demo_data.constants import DEMO_WINDOW_DAYS
        from app.tools.review_tools import activate_video

        video_id, ad_campaign_id = self._make_generated_video()
        assert activate_video(video_id=video_id)["status"] == "success"

        windows = self._windows(video_id)
        assert [w["screen_id"] for w in windows] == sorted(screens_for_campaign(ad_campaign_id))
        assert all(w["active_to"] is None for w in windows)
        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
        expected_from = (anchor - timedelta(days=DEMO_WINDOW_DAYS - 1)).isoformat()
        assert all(w["active_from"].startswith(expected_from) for w in windows)

    def test_pause_and_archive_close_windows(self, fresh_test_db):
        from app.tools.review_tools import activate_video, archive_video, pause_video

        video_id, _ = self._make_generated_video()
        activate_video(video_id=video_id)
        pause_video(video_id=video_id)
        assert all(w["active_to"] is not None for w in self._windows(video_id))

        video_id2, _ = self._make_generated_video_named("bridge-test-video-2.mp4")
        activate_video(video_id=video_id2)
        archive_video(video_id=video_id2)
        assert all(w["active_to"] is not None for w in self._windows(video_id2))

    def _make_generated_video_named(self, filename):
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS campaign_id, p.id AS product_id "
                "FROM campaigns c, products p LIMIT 1"
            )
            row = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO campaign_videos
                (campaign_id, product_id, video_filename, status)
                VALUES (?, ?, ?, 'generated')
                """,
                (row["campaign_id"], row["product_id"], filename),
            )
            return cursor.lastrowid, row["campaign_id"]

    def test_close_on_miss_warns_but_does_not_fail(self, fresh_test_db, caplog):
        """An activated video whose windows were externally closed: pausing
        must still succeed, with a warning — never the donor's silent no-op,
        never an exception."""
        import logging

        from app.database.db import get_db_cursor
        from app.tools.review_tools import activate_video, pause_video

        video_id, _ = self._make_generated_video()
        activate_video(video_id=video_id)
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE video_attribution SET active_to = active_from WHERE video_id = ?",
                (video_id,),
            )
        with caplog.at_level(logging.WARNING):
            assert pause_video(video_id=video_id)["status"] == "success"
        assert any("no open attribution window" in r.message for r in caplog.records)

    def test_activation_metrics_derive_through_db_windows(self, fresh_test_db):
        """The rows written at activation equal the join over the windows the
        bridge just opened — the windows are load-bearing, not decorative."""
        from datetime import date, timedelta

        from app.database.db import get_db_cursor, get_demo_anchor_date
        from app.demo_data.constants import DEMO_WINDOW_DAYS
        from app.demo_data.derive import derive_video_metrics_rows
        from app.tools.review_tools import _load_attribution_windows, activate_video

        video_id, ad_campaign_id = self._make_generated_video()
        activate_video(video_id=video_id)

        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            windows = _load_attribution_windows(cursor, [video_id])
            cursor.execute(
                "SELECT metric_date, impressions, dwell_time_seconds, circulation, revenue "
                "FROM video_metrics WHERE video_id = ? ORDER BY metric_date",
                (video_id,),
            )
            stored = [tuple(r) for r in cursor.fetchall()]

        derived = derive_video_metrics_rows(
            ad_campaign_id,
            [video_id],
            anchor - timedelta(days=DEMO_WINDOW_DAYS - 1),
            anchor,
            windows=windows,
        )
        expected = [
            (
                r["metric_date"],
                r["impressions"],
                r["dwell_time_seconds"],
                r["circulation"],
                r["revenue"],
            )
            for r in derived
        ]
        assert stored == expected
        assert len(stored) == DEMO_WINDOW_DAYS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_review_tools.py::TestAttributionBridge -v`
Expected: FAIL — `ImportError: cannot import name '_load_attribution_windows'` (and no windows written).

- [ ] **Step 3: Implement the bridge**

In `app/tools/review_tools.py`:

Add to the imports (top of file):

```python
import logging

from ..demo_data.attribution import screens_for_campaign
```

Add below the import block:

```python
logger = logging.getLogger(__name__)
```

Add these three helpers directly above `_insert_derived_metrics`:

```python
def _load_attribution_windows(cursor, video_ids) -> list[dict]:
    """Read this video set's attribution windows in join-ready dict shape."""
    placeholders = ",".join("?" for _ in video_ids)
    cursor.execute(
        f"SELECT video_id, screen_id, active_from, active_to FROM video_attribution "
        f"WHERE video_id IN ({placeholders})",
        list(video_ids),
    )
    windows = []
    for row in cursor.fetchall():
        windows.append(
            {
                "video_id": row["video_id"],
                "screen_id": row["screen_id"],
                "active_from": datetime.fromisoformat(row["active_from"]),
                "active_to": (
                    datetime.fromisoformat(row["active_to"]) if row["active_to"] else None
                ),
            }
        )
    return windows


def _open_attribution_windows(cursor, video_id, ad_campaign_id, active_from) -> int:
    """Open one window per campaign screen (skip screens already open)."""
    opened = 0
    for screen_id in screens_for_campaign(ad_campaign_id):
        cursor.execute(
            "SELECT 1 FROM video_attribution "
            "WHERE video_id = ? AND screen_id = ? AND active_to IS NULL",
            (video_id, screen_id),
        )
        if cursor.fetchone():
            continue
        cursor.execute(
            "INSERT INTO video_attribution "
            "(video_id, ad_campaign_id, screen_id, active_from, active_to) "
            "VALUES (?, ?, ?, ?, NULL)",
            (video_id, ad_campaign_id, screen_id, active_from.isoformat()),
        )
        opened += 1
    return opened


def _close_attribution_windows(cursor, video_id, active_to, expect_open: bool) -> int:
    """Close all open windows. Unlike the donor bridge's silent no-op, a miss
    where windows were expected logs a warning."""
    cursor.execute(
        "UPDATE video_attribution SET active_to = ? "
        "WHERE video_id = ? AND active_to IS NULL",
        (active_to.isoformat(), video_id),
    )
    closed = cursor.rowcount
    if closed == 0 and expect_open:
        logger.warning("no open attribution window to close for video %s", video_id)
    return closed
```

Rewrite `_insert_derived_metrics` to route through DB windows (same signature, same insert loop):

```python
def _insert_derived_metrics(cursor, ad_campaign_id, video_ids, date_from, date_to) -> int:
    """Insert join-derived deterministic rows; INSERT OR IGNORE keeps
    overlapping regeneration idempotent (UNIQUE(video_id, metric_date)).
    Videos with no stored windows (pre-bridge rows) fall back to the
    facade's synthesized always-open windows."""
    windows = _load_attribution_windows(cursor, video_ids)
    inserted = 0
    for row in derive_video_metrics_rows(
        ad_campaign_id, video_ids, date_from, date_to, windows=windows
    ):
        cursor.execute('''
            INSERT OR IGNORE INTO video_metrics
            (video_id, metric_date, impressions, dwell_time_seconds, circulation, revenue)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            row["video_id"],
            row["metric_date"],
            row["impressions"],
            row["dwell_time_seconds"],
            row["circulation"],
            row["revenue"]
        ))
        inserted += cursor.rowcount if cursor.rowcount > 0 else 0
    return inserted
```

In `activate_video`, between the `UPDATE campaign_videos ... status = 'activated'` execute and the `# Deterministic metrics ...` comment, the anchor read moves up and the bridge opens windows first. Replace the block

```python
        # Deterministic metrics on the single anchor window [anchor-29, anchor]
        anchor = date.fromisoformat(get_demo_anchor_date(cursor))
        metrics_generated = _insert_derived_metrics(
```

with

```python
        # Open attribution windows across the campaign's screens for the
        # whole demo history window (the 30-day backfill fiction), THEN
        # derive metrics through them — the join only accrues where a
        # window covers.
        anchor = date.fromisoformat(get_demo_anchor_date(cursor))
        window_start = anchor - timedelta(days=DEMO_WINDOW_DAYS - 1)
        _open_attribution_windows(
            cursor,
            video_id,
            video["campaign_id"],
            datetime.combine(window_start, datetime.min.time()),
        )
        metrics_generated = _insert_derived_metrics(
```

(and the existing `anchor - timedelta(days=DEMO_WINDOW_DAYS - 1)` positional argument below can become `window_start`).

In `pause_video`, after the `UPDATE campaign_videos SET status = 'paused'` execute, add:

```python
        _close_attribution_windows(cursor, video_id, datetime.now(), expect_open=True)
```

In `archive_video`, after the `UPDATE campaign_videos SET status = 'archived'` execute, add:

```python
        # Only an activated video is expected to have open windows; archiving
        # a never-activated or paused video closes nothing, silently.
        _close_attribution_windows(
            cursor, video_id, datetime.now(), expect_open=(video["status"] == "activated")
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/unit/test_review_tools.py -v && make test-unit`
Expected: all PASS — including the pre-existing activation-idempotency and generate_additional_metrics tests (DB windows cover the full range on all campaign screens, which is exactly what the facade synthesizes, so historical expectations hold).

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add app/tools/review_tools.py tests/unit/test_review_tools.py
git commit -m "feat(ws10): dual-write attribution bridge; metrics derive through stored windows"
```

---

### Task 6: Seed-time bulk path opens windows

**Files:**
- Modify: `app/database/mock_data.py`
- Test: `tests/unit/test_mock_data_attribution.py`

**Interfaces:**
- Consumes: `screens_for_campaign` (Task 3), `derive_video_metrics_rows(..., windows=)` (Task 4), `video_attribution` table (Task 2).
- Produces: after `populate_mock_data()`, every activated video has one open window per campaign screen with `active_from = anchor - 29d` (midnight ISO), and its metrics equal the join over those windows.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_mock_data_attribution.py`:

```python
"""Seed-time bulk path: pre-activated demo videos get attribution windows
(no activation moment exists on this path — the windows ARE the fiction)."""

from datetime import date, timedelta

from app.database.db import get_db_cursor, get_demo_anchor_date
from app.demo_data.attribution import screens_for_campaign
from app.demo_data.constants import DEMO_WINDOW_DAYS


class TestBulkSeedWindows:
    def test_every_activated_video_has_open_windows_per_screen(self, fresh_test_db):
        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            expected_from = (anchor - timedelta(days=DEMO_WINDOW_DAYS - 1)).isoformat()
            cursor.execute(
                "SELECT id, campaign_id FROM campaign_videos WHERE status = 'activated'"
            )
            activated = [(r["id"], r["campaign_id"]) for r in cursor.fetchall()]
            assert activated, "demo seed data provides activated videos"

            for video_id, ad_campaign_id in activated:
                cursor.execute(
                    "SELECT screen_id, active_from, active_to FROM video_attribution "
                    "WHERE video_id = ? ORDER BY screen_id",
                    (video_id,),
                )
                windows = cursor.fetchall()
                assert [w["screen_id"] for w in windows] == sorted(
                    screens_for_campaign(ad_campaign_id)
                )
                assert all(w["active_to"] is None for w in windows)
                assert all(w["active_from"].startswith(expected_from) for w in windows)

    def test_bulk_metrics_match_join_over_stored_windows(self, fresh_test_db):
        from app.demo_data.derive import derive_video_metrics_rows
        from app.tools.review_tools import _load_attribution_windows

        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            cursor.execute(
                "SELECT id, campaign_id FROM campaign_videos "
                "WHERE status = 'activated' LIMIT 1"
            )
            row = cursor.fetchone()
            video_id, ad_campaign_id = row["id"], row["campaign_id"]
            windows = _load_attribution_windows(cursor, [video_id])
            cursor.execute(
                "SELECT metric_date, impressions, revenue FROM video_metrics "
                "WHERE video_id = ? ORDER BY metric_date",
                (video_id,),
            )
            stored = [tuple(r) for r in cursor.fetchall()]

        derived = derive_video_metrics_rows(
            ad_campaign_id,
            [video_id],
            anchor - timedelta(days=DEMO_WINDOW_DAYS - 1),
            anchor,
            windows=windows,
        )
        assert stored == [(r["metric_date"], r["impressions"], r["revenue"]) for r in derived]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mock_data_attribution.py -v`
Expected: FAIL — no rows in `video_attribution` on the bulk path yet.

- [ ] **Step 3: Implement in `mock_data.py`**

Add to the imports:

```python
from ..demo_data.attribution import screens_for_campaign
```

(`datetime` is already imported or add `from datetime import datetime` alongside the existing `date`/`timedelta` import.)

In the Step-4 metrics block, after `campaign_video_ids = [row[0] for row in cursor.fetchall()]` / the `if not campaign_video_ids: continue` guard and BEFORE the `DELETE FROM video_metrics` loop, insert:

```python
        # Phase 10: pre-activated demo videos get attribution windows (there
        # is no activation moment on this path — the open window from
        # window_start IS the "has been live for 30 days" fiction).
        active_from_iso = datetime.combine(window_start, datetime.min.time()).isoformat()
        for video_id in campaign_video_ids:
            for screen_id in screens_for_campaign(campaign_id):
                cursor.execute('''
                    SELECT 1 FROM video_attribution
                    WHERE video_id = ? AND screen_id = ? AND active_to IS NULL
                ''', (video_id, screen_id))
                if cursor.fetchone():
                    continue
                cursor.execute('''
                    INSERT INTO video_attribution
                    (video_id, ad_campaign_id, screen_id, active_from, active_to)
                    VALUES (?, ?, ?, ?, NULL)
                ''', (video_id, campaign_id, screen_id, active_from_iso))
```

Then make the derive loop windows-aware — replace

```python
        # Generate deterministic metrics
        for row in derive_video_metrics_rows(
            campaign_id, campaign_video_ids, window_start, anchor
        ):
```

with

```python
        # Generate deterministic metrics through the stored windows
        # (4-line inline window load — mock_data must not import app.tools)
        placeholders = ",".join("?" for _ in campaign_video_ids)
        cursor.execute(
            f"SELECT video_id, screen_id, active_from, active_to FROM video_attribution "
            f"WHERE video_id IN ({placeholders})", campaign_video_ids)
        windows = [
            {
                "video_id": r[0],
                "screen_id": r[1],
                "active_from": datetime.fromisoformat(r[2]),
                "active_to": datetime.fromisoformat(r[3]) if r[3] else None,
            }
            for r in cursor.fetchall()
        ]
        for row in derive_video_metrics_rows(
            campaign_id, campaign_video_ids, window_start, anchor, windows=windows
        ):
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_mock_data_attribution.py -v && make test-unit && make test-e2e`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add app/database/mock_data.py tests/unit/test_mock_data_attribution.py
git commit -m "feat(ws10): bulk seed path opens attribution windows and derives through them"
```

---

### Task 7: Documentation and demo-scenario scene

**Files:**
- Modify: `docs/METRICS.md`, `app/demo_data/BLUEZOO_MAPPING.md`, `docs/demo-scenarios/fashion.md`, `.docs/version2-plan/demo_guide.md`

No code; the deliverable is docs consistent with the new derivation. The implementer reads each file first and anchors these edits to the existing prose:

- [ ] **Step 1: `docs/METRICS.md`** — update the derivation notes (glossary meanings stay identical):
  - **impressions**: replace the "video_fraction × daily summed incoming_inner_count" derivation description with: "Sum of `incoming_inner_count` over the 15-min slots the creative actually played (its deterministic `AdPlayRecord` schedule within its `video_attribution` windows, across the campaign's 2–3 screens). Inner-only, as before. (Phase 10: derived through the ad-play join, no longer a per-video daily fraction.)"
  - **circulation**: replace the "outgoing_outer_count × video_fraction" description with: "Sum of `outgoing_outer_count` over the creative's played slots — still the synthetic demo convention (the term appears nowhere in BlueZoo's docs); real semantics deferred to Phase 11."
  - **RPI/revenue**: confirm the per-creative band [0.03, 0.07] text still reads correctly (it should — the keying and formula are unchanged); mention revenue is now attributed per play window (`play visits × video_rpi`), summing to the same daily `impressions × rpi`.
  - **dwell**: unchanged (still synthetic, still deferred) — verify the existing text needs no edit.
- [ ] **Step 2: `app/demo_data/BLUEZOO_MAPPING.md`** — two fixes: (a) the stale "flat 0.05" RPI provenance line → per-creative band [0.03, 0.07] = DEMO_RPI × seeded [0.6, 1.4] (ws07); (b) the `video_attribution` frame's "reserved for Phase 10" note → now consumed: the DB `video_attribution` table carries the live windows, `attribution.py` performs the join; seed.py's frame remains the shape reference.
- [ ] **Step 3: `docs/demo-scenarios/fashion.md`** — append scene **F6: Attribution windows (Phase 10)** in the file's existing Act/Scene format:
  - **F6.1** — Query: "Show me the pending videos for campaign 1, then activate the first one." Expected tool calls: `list_pending_videos` (or `get_video_review_table`) then `activate_video`. Checks: response reports metrics generated (30 days); **DB assertion** (verifier runs via Bash against the local `campaigns.db`): `SELECT screen_id, active_to FROM video_attribution WHERE video_id = <id>` returns 2–3 rows, every `screen_id != campaign_id`, every `active_to` NULL.
  - **F6.2** — Query: "Pause that video." Expected tool call: `pause_video`. Checks: success response; DB assertion: the same rows now all have `active_to` NOT NULL.
- [ ] **Step 4: `.docs/version2-plan/demo_guide.md`** — refresh for changed metric values (owner note (d)): re-walk the B-journey narrative; keep B4/B5's invariant framing (band [0.03, 0.07], revenue ≈ impressions × per-creative RPI — both still hold exactly); replace any concrete example numbers with fresh ones observed from a `make reset-db && make dev`-seeded DB (capture via `sqlite3 campaigns.db "SELECT metric_date, impressions, revenue FROM video_metrics LIMIT 5"`); add a short "What changed in Phase 10" note (metrics now derive from attribution windows + ad-play schedules across 2–3 screens per campaign; absolute values shifted, invariants didn't). The main-checkout copy is synced at finish per the standing rule.
- [ ] **Step 5: Commit**

```bash
git add docs/METRICS.md app/demo_data/BLUEZOO_MAPPING.md docs/demo-scenarios/fashion.md .docs/version2-plan/demo_guide.md
git commit -m "docs(ws10): METRICS/BLUEZOO_MAPPING for ad-play join; F6 scenario; demo guide refresh"
```

---

### Task 8: Full-suite gate and verification handoff

- [ ] **Step 1: Full local gate**

Run: `make test-unit && make test-e2e && make lint`
Expected: all green. `tests/unit/test_metrics_tools.py` must be untouched by this branch (`git diff version_2 -- tests/unit/test_metrics_tools.py` is empty) — that is the "consumers insulated" proof.

- [ ] **Step 2: Fresh-DB smoke**

```bash
make reset-db
.venv/bin/python -c "
from app.database.db import init_database
from app.database.mock_data import populate_mock_data
init_database(); print(populate_mock_data())"
sqlite3 campaigns.db "SELECT COUNT(*) FROM video_attribution; SELECT COUNT(*) FROM video_metrics;"
```

Expected: both counts > 0; populate reports metrics_created > 0.

- [ ] **Step 3: Commit any stragglers, then hand off**

Verification proceeds per `verifying-with-demo-scenarios` (NOT part of this plan's task loop): STATUS → `verify in progress`, then `demo-scenario-verifier` runs **F3, F4, F6** from `docs/demo-scenarios/fashion.md` sequentially against this worktree's `make dev`. After that: `requesting-code-review` on the whole branch, then `finishing-a-development-branch` (PR into `version_2`, owner confirmation, self-merge; sync `demo_guide.md` to the main checkout).

---

## Self-Review Notes

- **Spec coverage:** working-doc components 1–8 map to Tasks 1 (DTOs), 2 (table), 3 (screens/schedule), 4 (join + facade + dwell/circulation policy), 5 (bridge + close-on-miss warning), 6 (bulk windows), 7 (docs + F6 + demo_guide), 8 (gates). Per-creative RPI, absoluteness, inner-only, 15-min alignment all pinned by tests in Tasks 3–4.
- **Type consistency:** windows travel as `list[dict]` with keys `video_id`/`screen_id`/`active_from: datetime`/`active_to: datetime|None` everywhere (`_load_attribution_windows`, mock_data inline load, `expand_ad_plays`, `derive_rows_from_windows`, facade synthesis). Plays are `AdPlayRecord` models. Row dicts carry the exact 6 video_metrics insert columns.
- **Known-safe back-compat:** activation writes windows covering the full [anchor−29, anchor] range on all campaign screens — identical in effect to the facade's synthesized windows — so the pre-existing idempotency and generate_additional_metrics tests pass without edits.
- **Magnitude sanity:** impressions ≈ (2–3 screens) × (10–22 slots) × (~42 × uplift inner/slot) ≈ 600–3700/day — inside the pinned [200, 8000] band.
