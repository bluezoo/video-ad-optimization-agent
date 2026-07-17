# Deterministic Demo Data (donor generator port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace both drifted random-metric generators (three call sites) with one deterministic, BlueZoo-shaped generator ported from the donor repo, feeding the existing `video_metrics` table through a thin disposable derivation layer.

**Architecture:** New import-light `app/demo_data/` package: `seed.py` (ported generator, sha256-seeded numpy RNG, frames as lists of dicts), `constants.py` (the single `DEMO_RPI`), `derive.py` (disposable frames→`video_metrics` layer). A tiny `demo_meta` table stores the demo anchor date; every generation call fills the backward window `[anchor − 29, anchor]`, so seed-time and activation-time data are indistinguishable and regeneration is idempotent (`INSERT OR IGNORE` on `UNIQUE(video_id, metric_date)`).

**Tech Stack:** Python 3.12, numpy (new dependency — no pandas), SQLite, pytest.

## Global Constraints

- Donor code was read at `ad-campaign-agent` @ `b6e3302` via `git show` only — the full ported code is IN this plan; implementers must NOT touch `/Users/lavi/gwork/ad-campaign-agent` at all (dirty working tree, strictly read-only).
- `DEMO_RPI = 0.05`, **flat** (owner decision): `revenue = round(impressions * DEMO_RPI, 2)`, no per-video revenue variance. Exactly ONE revenue/RPI constant on the demo-data path.
- Impressions = **inner-only** (`incoming_inner_count`), never inner+outer.
- Dwell-bin names are **HHMM-encoded** (`distribution_bin_0100_to_0105`; boundary bin `distribution_bin_0058_to_0100`); 106 bins total.
- Every frame column uses `ad_campaign_id`, never bare `campaign_id`; `minimum_/maximum_visitors_*`, not `min_/max_visitors_*`; vocabulary is `screen`, not `store`.
- `dwell_time_seconds` and `circulation` are provenance-flagged synthetic (METRICS.md governs); dwell is NOT derived from the bin histogram (that aggregation rule is Phase 11's to validate).
- `app/demo_data/seed.py` imports stdlib + numpy ONLY — no app modules, no DB (Phase 11a relocates it).
- All dates are UTC day buckets (`datetime.now(timezone.utc).date()`).
- Tool-invisible: no tool signatures, agent instructions, or response message shapes change.
- Both old `_generate_mock_video_metrics` implementations are deleted; `grep -rn "_generate_mock_video_metrics" app/ tests/` must return zero hits at the end.
- No AI-attribution trailers in commit messages.
- `README.md` and `DEMO_GUIDE.md` untouched.

## File Structure

- Create: `app/demo_data/__init__.py`, `app/demo_data/seed.py`, `app/demo_data/constants.py`, `app/demo_data/derive.py`, `app/demo_data/BLUEZOO_MAPPING.md`
- Modify: `app/requirements.txt` (add numpy), `app/database/db.py` (demo_meta table + anchor helpers), `app/database/mock_data.py` (call site 1, delete old generator), `app/tools/review_tools.py` (call sites 2+3, delete old generator), `SETUP_INSTRUCTIONS.md` (numpy note)
- Test: `tests/unit/test_demo_seed.py`, `tests/unit/test_demo_derive.py`, `tests/unit/test_demo_meta.py`, plus edits to `tests/unit/test_review_tools.py`

---

### Task 1: Ported generator (`app/demo_data/seed.py`) + numpy dependency

**Files:**
- Create: `app/demo_data/__init__.py`, `app/demo_data/seed.py`
- Modify: `app/requirements.txt`
- Test: `tests/unit/test_demo_seed.py`

**Interfaces:**
- Produces: `SeedConfig(screen_ids: list[int], campaigns: list[tuple[int, str, date, date, float]], date_from: date, date_to: date, videos_per_campaign: int = 2)`; `generate_frames(cfg: SeedConfig) -> dict[str, list[dict]]` with keys `screen_visits`, `screen_dwell`, `campaign_uv_daily`, `campaign_flow_transition`, `video_attribution`; `DWELL_BIN_COLUMNS: list[str]` (106 names); `_seeded_rng(*keys) -> np.random.Generator` (Task 2 reuses it).

- [ ] **Step 1: Add numpy to requirements and install it in the worktree venv**

In `app/requirements.txt`, under the `# Feature Dependencies` section, after the `pydantic>=2.11.7` line, add:

```
# Deterministic demo-data generation (app/demo_data/seed.py)
numpy>=1.26.0
```

Run: `.venv/bin/pip install "numpy>=1.26.0"`
Expected: numpy installs into the worktree venv (the PostToolUse test hook needs it before any app/ edit lands).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_demo_seed.py` with exactly:

```python
"""Tests for the deterministic demo-data seed generator.

Ported from the donor repo's test_seed.py (ad-campaign-agent @ b6e3302),
adapted: no pandas (frames are lists of dicts), screen vocabulary,
ad_campaign_id columns, HHMM bin names, plus a cross-process determinism
check the phase doc's validation requires.
"""

import subprocess
import sys
from datetime import date

from app.demo_data.seed import (
    DWELL_BIN_COLUMNS,
    SeedConfig,
    generate_frames,
)


def _config() -> SeedConfig:
    return SeedConfig(
        screen_ids=[1, 2],
        campaigns=[
            (42, "Spring Promo", date(2026, 3, 1), date(2026, 3, 7), 1.0),
            (43, "Mother's Day", date(2026, 5, 1), date(2026, 5, 7), 1.4),
        ],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 5, 10),
    )


class TestSeedShape:
    def test_returns_all_five_frames(self):
        frames = generate_frames(_config())
        assert set(frames.keys()) == {
            "screen_visits",
            "screen_dwell",
            "campaign_uv_daily",
            "campaign_flow_transition",
            "video_attribution",
        }

    def test_screen_visits_has_corrected_columns(self):
        frames = generate_frames(_config())
        row = frames["screen_visits"][0]
        assert "incoming_inner_count" in row
        assert "outgoing_outer_count" in row
        assert "ad_campaign_id" in row
        assert "minimum_visitors_inner" in row
        assert "maximum_visitors_outer" in row
        # The donor names this port corrects must be gone
        assert "campaign_id" not in row
        assert "store_id" not in row
        assert "min_visitors_inner" not in row

    def test_dwell_bins_are_hhmm_encoded(self):
        assert len(DWELL_BIN_COLUMNS) == 106
        # Sub-hour names are identical in both encodings
        assert DWELL_BIN_COLUMNS[0] == "distribution_bin_0000_to_0001"
        # The boundary bin: 58 min -> 60 min is _0058_to_0100, never _0058_to_0060
        assert DWELL_BIN_COLUMNS[44] == "distribution_bin_0058_to_0100"
        assert "distribution_bin_0058_to_0060" not in DWELL_BIN_COLUMNS
        # First bin above the hour: HHMM, not minutes
        assert DWELL_BIN_COLUMNS[45] == "distribution_bin_0100_to_0105"
        assert "distribution_bin_0060_to_0065" not in DWELL_BIN_COLUMNS
        # Last regular bin and the open-ended bin
        assert DWELL_BIN_COLUMNS[104] == "distribution_bin_2300_to_2400"
        assert DWELL_BIN_COLUMNS[105] == "distribution_bin_2400_to_beyond"

    def test_screen_dwell_has_106_bins_summing_to_one(self):
        frames = generate_frames(_config())
        d = frames["screen_dwell"]
        assert d, "dwell frame must not be empty"
        row = d[0]
        bins = [k for k in row if k.startswith("distribution_bin_")]
        assert len(bins) == 106
        for r in d[:50]:
            assert abs(sum(r[c] for c in DWELL_BIN_COLUMNS) - 1.0) < 1e-6

    def test_cuv_freq_columns_are_floats(self):
        frames = generate_frames(_config())
        row = frames["campaign_uv_daily"][0]
        for i in range(1, 11):
            assert isinstance(row[f"cuv_freq_{i}"], float)


class TestDeterminism:
    def test_same_config_produces_identical_data(self):
        f1 = generate_frames(_config())
        f2 = generate_frames(_config())
        assert f1 == f2

    def test_cross_process_determinism(self):
        """Same key in two separate processes -> byte-identical output
        (proves sha256 seeding survived the port; no PYTHONHASHSEED dependence)."""
        script = (
            "import hashlib, json;"
            "from datetime import date;"
            "from app.demo_data.seed import SeedConfig, generate_frames;"
            "cfg = SeedConfig(screen_ids=[1], campaigns=[(7, 'x', date(2026, 5, 1),"
            " date(2026, 5, 3), 1.1)], date_from=date(2026, 5, 1), date_to=date(2026, 5, 3));"
            "frames = generate_frames(cfg);"
            "print(hashlib.sha256(repr(frames).encode()).hexdigest())"
        )
        runs = [
            subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, check=True
            ).stdout.strip()
            for _ in range(2)
        ]
        assert runs[0] == runs[1]
        assert len(runs[0]) == 64

    def test_different_keys_differ(self):
        cfg_a = SeedConfig(
            screen_ids=[1],
            campaigns=[(42, "x", date(2026, 5, 1), date(2026, 5, 3), 1.0)],
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 3),
        )
        cfg_b = SeedConfig(
            screen_ids=[1],
            campaigns=[(43, "x", date(2026, 5, 1), date(2026, 5, 3), 1.0)],
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 3),
        )
        va = generate_frames(cfg_a)["screen_visits"]
        vb = generate_frames(cfg_b)["screen_visits"]
        assert [r["incoming_inner_count"] for r in va] != [
            r["incoming_inner_count"] for r in vb
        ]

    def test_campaign_uplift_increases_impressions(self):
        def cfg(uplift):
            return SeedConfig(
                screen_ids=[1],
                campaigns=[(42, "x", date(2026, 5, 1), date(2026, 5, 3), uplift)],
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 3),
            )

        low = generate_frames(cfg(0.7))["screen_visits"]
        high = generate_frames(cfg(1.4))["screen_visits"]
        assert sum(r["incoming_inner_count"] for r in high) > sum(
            r["incoming_inner_count"] for r in low
        )


class TestRealism:
    def test_weekend_lift_is_visible(self):
        cfg = SeedConfig(
            screen_ids=[1],
            campaigns=[(42, "x", date(2026, 5, 1), date(2026, 5, 14), 1.0)],
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 14),
        )
        visits = generate_frames(cfg)["screen_visits"]
        weekend = [
            r["incoming_inner_count"] for r in visits if r["timestamp"].weekday() >= 5
        ]
        weekday = [
            r["incoming_inner_count"] for r in visits if r["timestamp"].weekday() < 5
        ]
        assert sum(weekend) / len(weekend) > sum(weekday) / len(weekday)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_demo_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.demo_data'`

- [ ] **Step 4: Create the package and the ported generator**

Create `app/demo_data/__init__.py`:

```python
"""Deterministic, BlueZoo-shaped demo data (ported from the donor repo).

seed.py     - the generator (import-light; Phase 11a relocates it)
constants.py- the single canonical demo revenue constant
derive.py   - disposable frames -> video_metrics derivation (Phase 10 deletes it)
See BLUEZOO_MAPPING.md for every deliberate divergence from BlueZoo's schema.
"""
```

Create `app/demo_data/seed.py` with exactly:

```python
"""Deterministic, BlueZoo-shaped demo-data generator.

Ported from the donor repo `ad-campaign-agent` @ b6e3302
(`services/audience_provider/seed.py`, branch feat/plan3-slice1-bq-mvp) with
the corrections mandated by the BlueZoo mapping verification
(.docs/version2-plan/working-docs/replan-data-track/bluezoo-mapping-verification.md):
HHMM dwell-bin names, `ad_campaign_id` (never bare `campaign_id`),
`minimum_/maximum_visitors_*`, FLOAT64 cuv_freq_*, screen vocabulary, and
frames as lists of dicts (no pandas). Every divergence is enumerated in
app/demo_data/BLUEZOO_MAPPING.md.

Hash-based on (ad_campaign_id, screen_id, date): re-running with the same
config produces byte-identical frames, in any process (sha256-derived seeds,
no PYTHONHASHSEED dependence).

Dates and timestamps are UTC day buckets by convention (Q18 tracks BlueZoo's
own daily-bucket timezone).

Deliberately import-light: stdlib + numpy only, no app modules, no DB —
Phase 11a moves this file behind the AudienceProvider seam as-is.
"""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np


def _hhmm(minutes: int) -> str:
    """Encode a dwell-boundary minute count as BlueZoo's HHMM name token."""
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def _bin_columns() -> list[str]:
    """The 106 BlueZoo dwell-histogram bin names, HHMM-encoded.

    Grain layout (verified against the live docs): 30x1min + 15x2min +
    24x5min + 20x15min + 16x60min + 1 open-ended. The donor emitted these in
    minutes encoding (61 of 106 wrong, e.g. `_0060_to_0065`); BlueZoo's real
    names are HHMM (`_0100_to_0105`; boundary bin `_0058_to_0100`).
    """
    edges: list[tuple[int, int]] = []
    for i in range(30):
        edges.append((i, i + 1))
    for i in range(30, 60, 2):
        edges.append((i, i + 2))
    for i in range(60, 180, 5):
        edges.append((i, i + 5))
    for i in range(180, 480, 15):
        edges.append((i, i + 15))
    for i in range(480, 1440, 60):
        edges.append((i, i + 60))
    cols = [f"distribution_bin_{_hhmm(lo)}_to_{_hhmm(hi)}" for lo, hi in edges]
    cols.append("distribution_bin_2400_to_beyond")
    assert len(cols) == 106
    return cols


DWELL_BIN_COLUMNS = _bin_columns()


@dataclass
class SeedConfig:
    """Configuration for demo data generation.

    campaigns: list of (ad_campaign_id, name, start, end, uplift_factor).
    """

    screen_ids: list[int]
    campaigns: list[tuple[int, str, date, date, float]]
    date_from: date
    date_to: date
    # Two video attributions per campaign (variation A + B)
    videos_per_campaign: int = 2


def _seeded_rng(*keys) -> np.random.Generator:
    """Deterministic per-(key) RNG. Uses sha256 to derive a 64-bit seed."""
    h = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "big"))


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _slot_starts(d: date) -> list[datetime]:
    """15-min slots from 09:00 to 21:00 — 48 slots/day (12h x 4)."""
    base = datetime.combine(d, datetime.min.time()).replace(hour=9)
    return [base + timedelta(minutes=15 * i) for i in range(48)]


def _campaign_for_date(cfg: SeedConfig, d: date) -> "tuple[int, float] | None":
    """Return (ad_campaign_id, uplift) for the campaign covering date d, or None."""
    for cid, _name, start, end, uplift in cfg.campaigns:
        if start <= d <= end:
            return cid, uplift
    return None


def _dwell_distribution(rng: np.random.Generator) -> np.ndarray:
    """106-bin dwell histogram. Bimodal: most visitors <2m, smaller bump at 2-10m."""
    weights = np.zeros(106)
    # Bins 0-29 are 1-min bins covering 0-30m
    weights[:30] = rng.dirichlet(np.array([5.0] * 30)) * 0.65
    # Bins 30-44 are 2-min covering 30-60m
    weights[30:45] = rng.dirichlet(np.array([1.0] * 15)) * 0.20
    # Bins 45-68 are 5-min covering 1-3h
    weights[45:69] = rng.dirichlet(np.array([1.0] * 24)) * 0.10
    # Bins 69-88 are 15-min covering 3-8h
    weights[69:89] = rng.dirichlet(np.array([1.0] * 20)) * 0.04
    # Bins 89-104 are 1-h covering 8-24h, plus the 2400_to_beyond
    weights[89:105] = rng.dirichlet(np.array([1.0] * 16)) * 0.009
    weights[105] = 0.001
    return weights / weights.sum()


def _generate_visits(cfg: SeedConfig) -> list[dict]:
    rows = []
    for d in _date_range(cfg.date_from, cfg.date_to):
        match = _campaign_for_date(cfg, d)
        cid, uplift = match if match else (None, 1.0)
        weekend = d.weekday() >= 5
        weekend_mult = 1.25 if weekend else 1.0
        for screen_id in cfg.screen_ids:
            rng = _seeded_rng(cid, screen_id, d.isoformat())
            for slot_idx, ts in enumerate(_slot_starts(d)):
                # Lunch peak (slots 12-16 = 12:00-13:00) and after-school
                hour_factor = 1.0
                if 12 <= slot_idx <= 16:
                    hour_factor = 1.35
                elif 28 <= slot_idx <= 32:
                    hour_factor = 1.15
                base_outer = 200 * uplift * weekend_mult * hour_factor
                base_inner = 40 * uplift * weekend_mult * hour_factor
                rows.append(
                    {
                        "timestamp": ts,
                        "screen_id": screen_id,
                        "ad_campaign_id": cid,
                        "incoming_inner_count": float(
                            round(base_inner * rng.uniform(0.85, 1.15), 2)
                        ),
                        "outgoing_inner_count": float(
                            round(base_inner * rng.uniform(0.80, 1.10), 2)
                        ),
                        "incoming_outer_count": float(
                            round(base_outer * rng.uniform(0.90, 1.10), 2)
                        ),
                        "outgoing_outer_count": float(
                            round(base_outer * rng.uniform(0.85, 1.05), 2)
                        ),
                        "minimum_visitors_inner": float(round(base_inner * 0.05, 2)),
                        "maximum_visitors_inner": float(round(base_inner * 0.40, 2)),
                        "average_visitors_inner": float(round(base_inner * 0.20, 2)),
                        "minimum_visitors_outer": float(round(base_outer * 0.10, 2)),
                        "maximum_visitors_outer": float(round(base_outer * 0.50, 2)),
                        "average_visitors_outer": float(round(base_outer * 0.25, 2)),
                        "valid": True,
                    }
                )
    return rows


def _generate_dwell(cfg: SeedConfig, visits: list[dict]) -> list[dict]:
    """One row per (timestamp, screen, campaign) matching visits.

    total_visits is inner-only (visits that ended in the slot) — the donor
    summed inner+outer; corrected per the mapping verification.
    """
    rows = []
    for v in visits:
        rng = _seeded_rng(
            "dwell", v["ad_campaign_id"], v["screen_id"], v["timestamp"].isoformat()
        )
        weights = _dwell_distribution(rng)
        d_row: dict = {
            "timestamp": v["timestamp"],
            "screen_id": v["screen_id"],
            "ad_campaign_id": v["ad_campaign_id"],
            "total_visits": v["incoming_inner_count"],
            "valid": True,
        }
        for col, w in zip(DWELL_BIN_COLUMNS, weights):
            d_row[col] = float(w)
        rows.append(d_row)
    return rows


def _generate_uv_daily(cfg: SeedConfig) -> list[dict]:
    rows = []
    for cid, _name, start, end, uplift in cfg.campaigns:
        for d in _date_range(start, end):
            if d < cfg.date_from or d > cfg.date_to:
                continue
            rng = _seeded_rng("uv", cid, d.isoformat())
            total = int(round(800 * uplift * len(cfg.screen_ids) * rng.uniform(0.9, 1.1)))
            row: dict = {"date": d, "ad_campaign_id": cid, "unique_visitors_count": total}
            # Heavy long tail: ~75% in freq_1, decreasing.
            # FLOAT64 per BlueZoo (extrapolated from sampled MACs), not INT64.
            shares = np.array([0.75, 0.12, 0.06, 0.03, 0.015, 0.01, 0.008, 0.005, 0.001, 0.001])
            shares = shares / shares.sum()
            for i, s in enumerate(shares, start=1):
                row[f"cuv_freq_{i}"] = float(round(total * s, 2))
            rows.append(row)
    return rows


def _generate_flow(cfg: SeedConfig) -> list[dict]:
    rows = []
    for cid, _name, start, end, uplift in cfg.campaigns:
        for d in _date_range(start, end):
            if d < cfg.date_from or d > cfg.date_to:
                continue
            for src in cfg.screen_ids:
                for dst in cfg.screen_ids:
                    if src == dst:
                        continue
                    rng = _seeded_rng("flow", cid, d.isoformat(), src, dst)
                    rows.append(
                        {
                            "date": d,
                            "ad_campaign_id": cid,
                            "source_screen_id": src,
                            "dest_screen_id": dst,
                            "transition_count": int(round(40 * uplift * rng.uniform(0.7, 1.3))),
                            # Per-pair journey duration is a donor invention
                            # (BlueZoo keys journey duration by
                            # number_of_groups_visited) — see BLUEZOO_MAPPING.md.
                            "average_journey_duration_seconds": float(
                                round(900 * rng.uniform(0.8, 1.2), 1)
                            ),
                        }
                    )
    return rows


def _generate_attribution(cfg: SeedConfig) -> list[dict]:
    rows = []
    for cid, _name, start, end, _u in cfg.campaigns:
        for screen_id in cfg.screen_ids:
            for v_idx in range(cfg.videos_per_campaign):
                video_id = f"vid_c{cid}_s{screen_id}_{v_idx}"
                rows.append(
                    {
                        "video_id": video_id,
                        "ad_campaign_id": cid,
                        "screen_id": screen_id,
                        "active_from": datetime.combine(start, datetime.min.time()),
                        "active_to": datetime.combine(end, datetime.min.time()),
                    }
                )
    return rows


def generate_frames(cfg: SeedConfig) -> dict[str, list[dict]]:
    """Build the five frames matching the BlueZoo-shaped demo schema."""
    visits = _generate_visits(cfg)
    return {
        "screen_visits": visits,
        "screen_dwell": _generate_dwell(cfg, visits),
        "campaign_uv_daily": _generate_uv_daily(cfg),
        "campaign_flow_transition": _generate_flow(cfg),
        "video_attribution": _generate_attribution(cfg),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_demo_seed.py -v`
Expected: all PASS (the cross-process test spawns `sys.executable` — it needs to run from the repo root so `app` is importable; pytest's rootdir already is).

- [ ] **Step 6: Lint and run the full unit suite**

Run: `make lint && make test-unit`
Expected: clean, all pass.

- [ ] **Step 7: Commit**

```bash
git add app/demo_data/__init__.py app/demo_data/seed.py app/requirements.txt tests/unit/test_demo_seed.py
git commit -m "Port deterministic BlueZoo-shaped seed generator from donor (b6e3302)"
```

---

### Task 2: Constants + derivation layer (`constants.py`, `derive.py`)

**Files:**
- Create: `app/demo_data/constants.py`, `app/demo_data/derive.py`
- Test: `tests/unit/test_demo_derive.py`

**Interfaces:**
- Consumes: `SeedConfig`, `generate_frames`, `_seeded_rng` from Task 1.
- Produces: `DEMO_RPI: float = 0.05`, `DEMO_WINDOW_DAYS: int = 30` (constants.py); `derive_video_metrics_rows(ad_campaign_id: int, video_ids: list, date_from: date, date_to: date) -> list[dict]` and `video_fraction(ad_campaign_id: int, video_id) -> float` (derive.py). Row dicts carry exactly the `video_metrics` insert columns: `video_id, metric_date (ISO str), impressions (int), dwell_time_seconds (float), circulation (int), revenue (float)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_demo_derive.py` with exactly:

```python
"""Tests for the disposable frames -> video_metrics derivation layer."""

from datetime import date

from app.demo_data.constants import DEMO_RPI, DEMO_WINDOW_DAYS
from app.demo_data.derive import derive_video_metrics_rows, video_fraction
from app.demo_data.seed import SeedConfig, generate_frames
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_demo_derive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.demo_data.constants'`

- [ ] **Step 3: Write the implementation**

Create `app/demo_data/constants.py` with exactly:

```python
"""The canonical demo-data constants.

DEMO_RPI is THE single revenue-per-impression constant on the demo-data path
(phase-doc step 4). The donor duplicated 0.05 in two places
(REVENUE_PER_IMPRESSION and an inline SQL literal); here it exists once.
Flat by owner decision (ws05 working doc): demo revenue is exactly
impressions x DEMO_RPI, so demo RPI is identical across creatives until
Phase 7 revisits.
"""

# Dollars of attributed revenue per impression (donor's effective constant).
DEMO_RPI = 0.05

# Every generation call fills the backward window [anchor - 29, anchor].
DEMO_WINDOW_DAYS = 30
```

Create `app/demo_data/derive.py` with exactly:

```python
"""Disposable derivation layer: BlueZoo-shaped frames -> video_metrics rows.

Phase 10 replaces this file with the real ad-play join — every
per-video-per-day assumption lives HERE, never in seed.py.

Provenance flags (see docs/METRICS.md and BLUEZOO_MAPPING.md):
- dwell_time_seconds: synthetic scalar. METRICS.md defers the dwell
  histogram -> scalar aggregation rule to Phase 11 ("must be validated
  against a real BlueZoo response before it is written down as fact"), so
  this value is deliberately NOT derived from the dwell bins.
- circulation: synthetic demo convention derived from outgoing_outer_count;
  "circulation" appears nowhere in BlueZoo's docs.
"""

from datetime import date

from .constants import DEMO_RPI
from .seed import SeedConfig, _seeded_rng, generate_frames


def _campaign_seed_config(ad_campaign_id: int, date_from: date, date_to: date) -> SeedConfig:
    """One campaign on one screen. The screen IS the campaign (1:1 proxy:
    a campaign is a single product at a single store today; Phase 10's
    Screen entity replaces this without changing the key mechanism)."""
    return SeedConfig(
        screen_ids=[ad_campaign_id],
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


def campaign_uplift(ad_campaign_id: int) -> float:
    """Deterministic per-campaign performance uplift in [0.7, 1.4].

    Replaces the old hard-coded campaign_multipliers dict: any campaign id —
    including ones created after seed time — gets a plausible, stable value
    (Phase 15's onboarding relies on this)."""
    rng = _seeded_rng("uplift", ad_campaign_id)
    return float(round(0.7 + rng.uniform() * 0.7, 2))


def video_fraction(ad_campaign_id: int, video_id) -> float:
    """Deterministic absolute fraction of the screen's daily audience this
    video captures, in [0.25, 0.6].

    Absolute, not normalized across the campaign's videos: activating
    another video later must never change existing videos' rows."""
    rng = _seeded_rng("share", ad_campaign_id, video_id)
    return float(round(0.25 + rng.uniform() * 0.35, 4))


def derive_video_metrics_rows(
    ad_campaign_id: int, video_ids: list, date_from: date, date_to: date
) -> list[dict]:
    """One video_metrics row per (video, day), derived from the day's
    BlueZoo-shaped 15-minute visit frames.

    impressions = video_fraction x the day's summed incoming_inner_count
    (inner-only — outer is ~100 m passersby, never impressions).
    revenue = impressions x DEMO_RPI (flat, owner decision).
    Returned dicts carry exactly the video_metrics insert columns."""
    frames = generate_frames(_campaign_seed_config(ad_campaign_id, date_from, date_to))

    by_day: dict = {}
    for v in frames["screen_visits"]:
        d = v["timestamp"].date()
        agg = by_day.setdefault(d, {"inner": 0.0, "outer_out": 0.0})
        agg["inner"] += v["incoming_inner_count"]
        agg["outer_out"] += v["outgoing_outer_count"]

    rows = []
    for d in sorted(by_day):
        for video_id in video_ids:
            fraction = video_fraction(ad_campaign_id, video_id)
            impressions = int(round(by_day[d]["inner"] * fraction))
            dwell_rng = _seeded_rng("dwell-scalar", ad_campaign_id, video_id, d.isoformat())
            rows.append(
                {
                    "video_id": video_id,
                    "metric_date": d.isoformat(),
                    "impressions": impressions,
                    # Synthetic seconds-scale scalar — see module docstring.
                    "dwell_time_seconds": float(round(4.0 + dwell_rng.uniform() * 8.0, 1)),
                    "circulation": int(round(by_day[d]["outer_out"] * fraction)),
                    "revenue": round(impressions * DEMO_RPI, 2),
                }
            )
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_demo_derive.py tests/unit/test_demo_seed.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, full unit suite, commit**

Run: `make lint && make test-unit`

```bash
git add app/demo_data/constants.py app/demo_data/derive.py tests/unit/test_demo_derive.py
git commit -m "Add demo constants and disposable video_metrics derivation layer"
```

---

### Task 3: `demo_meta` table + anchor-date helpers

**Files:**
- Modify: `app/database/db.py`
- Test: `tests/unit/test_demo_meta.py`

**Interfaces:**
- Produces: `get_demo_anchor_date(cursor) -> str` (ISO date; creates today's UTC date on first call) and `set_demo_anchor_date(cursor, iso_date: str) -> None` in `app/database/db.py`; `demo_meta` table created by `init_database()`, dropped by `reset_database()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_demo_meta.py` with exactly:

```python
"""Tests for the demo_meta table and demo anchor-date helpers."""

from datetime import datetime, timezone

from app.database.db import (
    get_db_cursor,
    get_demo_anchor_date,
    set_demo_anchor_date,
)


class TestDemoAnchor:
    def test_first_read_seeds_todays_utc_date(self, fresh_test_db):
        with get_db_cursor() as cursor:
            anchor = get_demo_anchor_date(cursor)
        assert anchor == datetime.now(timezone.utc).date().isoformat()

    def test_anchor_is_stable_across_reads(self, fresh_test_db):
        with get_db_cursor() as cursor:
            first = get_demo_anchor_date(cursor)
        with get_db_cursor() as cursor:
            second = get_demo_anchor_date(cursor)
        assert first == second

    def test_set_overwrites(self, fresh_test_db):
        with get_db_cursor() as cursor:
            set_demo_anchor_date(cursor, "2026-01-15")
        with get_db_cursor() as cursor:
            assert get_demo_anchor_date(cursor) == "2026-01-15"
        with get_db_cursor() as cursor:
            set_demo_anchor_date(cursor, "2026-02-01")
        with get_db_cursor() as cursor:
            assert get_demo_anchor_date(cursor) == "2026-02-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_demo_meta.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_demo_anchor_date'`

- [ ] **Step 3: Implement**

In `app/database/db.py`:

(a) Change the datetime import — the file currently has no datetime import; add after `import sqlite3`:

```python
from datetime import datetime, timezone
```

(b) In `init_database()`, directly after the `video_metrics` CREATE TABLE block (the `''')` at db.py:153, before the `# Legacy tables for backward compatibility` comment), add:

```python
    # Key-value store for demo-mode state (e.g. the demo anchor date that
    # fixes the deterministic generation window — see app/demo_data/).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS demo_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
```

(c) In `reset_database()`, add to the "Drop new tables" group:

```python
    cursor.execute('DROP TABLE IF EXISTS demo_meta')
```

(d) At module bottom (after `reset_database()`), add:

```python
DEMO_ANCHOR_KEY = "demo_anchor_date"


def get_demo_anchor_date(cursor) -> str:
    """The demo anchor date (ISO), created as today's UTC date on first read.

    All deterministic demo generation windows are anchored here (UTC day
    buckets by convention), so seed-time and activation-time data share one
    windowing rule."""
    cursor.execute("SELECT value FROM demo_meta WHERE key = ?", (DEMO_ANCHOR_KEY,))
    row = cursor.fetchone()
    if row:
        return row["value"]
    today = datetime.now(timezone.utc).date().isoformat()
    cursor.execute(
        "INSERT OR IGNORE INTO demo_meta (key, value) VALUES (?, ?)",
        (DEMO_ANCHOR_KEY, today),
    )
    return today


def set_demo_anchor_date(cursor, iso_date: str) -> None:
    """Overwrite the demo anchor date (ISO string)."""
    cursor.execute(
        """
        INSERT INTO demo_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (DEMO_ANCHOR_KEY, iso_date),
    )
```

Note: `get_connection()` sets `row_factory = sqlite3.Row`, so `row["value"]` works for every caller that goes through this module's helpers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_demo_meta.py -v`
Expected: PASS. (The `fresh_test_db` fixture calls `init_database()` + `populate_mock_data()` against a temp DB — see tests/conftest.py:166-169.)

- [ ] **Step 5: Lint, full unit suite, commit**

Run: `make lint && make test-unit`

```bash
git add app/database/db.py tests/unit/test_demo_meta.py
git commit -m "Add demo_meta table and demo anchor-date helpers"
```

---

### Task 4: Call site 1 — `populate_mock_data()` uses the ported path; delete old generator

**Files:**
- Modify: `app/database/mock_data.py`
- Test: extend `tests/unit/test_demo_meta.py` (windowing assertions live with the anchor tests)

**Interfaces:**
- Consumes: `derive_video_metrics_rows` (Task 2), `DEMO_WINDOW_DAYS` (Task 2), `get_demo_anchor_date` (Task 3).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_demo_meta.py`:

```python
class TestSeededWindow:
    def test_seeded_metrics_fill_the_anchor_window(self, fresh_test_db):
        """populate_mock_data() must fill exactly [anchor-29, anchor] for
        every seeded activated video — the single windowing rule."""
        from datetime import date, timedelta

        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            cursor.execute(
                """
                SELECT video_id, MIN(metric_date) AS lo, MAX(metric_date) AS hi,
                       COUNT(*) AS n
                FROM video_metrics GROUP BY video_id
                """
            )
            groups = cursor.fetchall()
        assert groups, "seeded demo DB must contain metrics"
        for g in groups:
            assert g["lo"] == (anchor - timedelta(days=29)).isoformat()
            assert g["hi"] == anchor.isoformat()
            assert g["n"] == 30

    def test_reseeding_is_deterministic(self, fresh_test_db):
        """Wipe metrics and repopulate: byte-identical rows come back."""
        from app.database.mock_data import populate_mock_data

        def snapshot():
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT video_id, metric_date, impressions, dwell_time_seconds,
                           circulation, revenue
                    FROM video_metrics ORDER BY video_id, metric_date
                    """
                )
                return [tuple(r) for r in cursor.fetchall()]

        first = snapshot()
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM video_metrics")
        populate_mock_data()
        assert snapshot() == first
```

Run: `.venv/bin/pytest tests/unit/test_demo_meta.py -v`
Expected: the two new tests FAIL (current generator anchors on `datetime.now()` per-call and is random on reseed).

- [ ] **Step 2: Swap the call site**

In `app/database/mock_data.py`:

(a) Replace the imports block lines `import random` and `from datetime import datetime, timedelta` handling: the old generator is this file's only `random` user — after deletion, remove `import random` if (and only if) `grep -n "random\." app/database/mock_data.py` shows no other use. Add imports:

```python
from datetime import date, datetime, timedelta

from ..demo_data.constants import DEMO_WINDOW_DAYS
from ..demo_data.derive import derive_video_metrics_rows
from .db import get_connection, get_demo_anchor_date
```

(replacing the existing `from .db import get_connection`).

(b) Delete the entire `_generate_mock_video_metrics()` function (mock_data.py:168-235, from its `def` line through its `return metrics`).

(c) In `populate_mock_data()`, the campaign/video loop currently generates metrics per video right after inserting each video (the block at :381-396 beginning `# Step 4: Generate metrics for each activated video`). Restructure: inside the per-campaign loop, collect the fetched `video_id`s into a `campaign_video_ids` list where `videos_created += 1` happens; delete the old per-video metrics block; after the per-campaign video loop completes (still inside the campaign loop), generate once per campaign:

```python
            # Step 4: Deterministic metrics for this campaign's activated
            # videos, on the single anchor window [anchor-29, anchor]
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            window_start = anchor - timedelta(days=DEMO_WINDOW_DAYS - 1)
            for row in derive_video_metrics_rows(
                campaign_id, campaign_video_ids, window_start, anchor
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
                metrics_created += 1
```

Match the surrounding function's actual variable names (`campaign_id`, `cursor`, `metrics_created` all exist in the current code) — read the function before editing; the block above is drop-in but the `campaign_video_ids = []` initialization must be added at the top of the per-campaign loop.

- [ ] **Step 3: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_demo_meta.py tests/unit/test_demo_derive.py -v`
Expected: PASS.

- [ ] **Step 4: Full unit suite (conftest repopulates the shared test DB — this proves nothing else broke)**

Run: `make lint && make test-unit && make test-e2e`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/database/mock_data.py tests/unit/test_demo_meta.py
git commit -m "Seed demo metrics via deterministic derivation on the anchor window"
```

---

### Task 5: Call sites 2+3 — `activate_video()` and `generate_additional_metrics()`; delete second old generator

**Files:**
- Modify: `app/tools/review_tools.py`
- Test: extend `tests/unit/test_review_tools.py`

**Interfaces:**
- Consumes: `derive_video_metrics_rows`, `DEMO_WINDOW_DAYS` (Task 2), `get_demo_anchor_date`, `set_demo_anchor_date` (Task 3).
- Behavior contract: `activate_video` fills `[anchor-29, anchor]` for the new video; `generate_additional_metrics(video_id, days=N)` advances the global anchor by N days and fills `(old_anchor, new_anchor]` for EVERY activated video (the demo universe moves forward atomically). Response message shapes unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_review_tools.py` (module already imports `date`/`timedelta` helpers and has `_insert`-style fixtures; add plain imports inside the tests where shown):

```python
class TestDeterministicActivation:
    async def test_activation_fills_anchor_window(self, fresh_test_db):
        """A newly-activated video's rows land on [anchor-29, anchor] —
        the same window seeding used (no seed/activation discontinuity)."""
        from datetime import date, timedelta

        from app.database.db import get_db_cursor, get_demo_anchor_date
        from app.tools.review_tools import activate_video, list_pending_videos

        pending = await list_pending_videos()
        video_id = pending["videos"][0]["id"]
        result = await activate_video(video_id=video_id)
        assert result["status"] == "success"

        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            cursor.execute(
                "SELECT MIN(metric_date) AS lo, MAX(metric_date) AS hi, COUNT(*) AS n "
                "FROM video_metrics WHERE video_id = ?",
                (video_id,),
            )
            row = cursor.fetchone()
        assert row["lo"] == (anchor - timedelta(days=29)).isoformat()
        assert row["hi"] == anchor.isoformat()
        assert row["n"] == 30

    async def test_activation_is_deterministic(self, fresh_test_db):
        """Activating, wiping the rows, and re-deriving yields identical rows."""
        from app.database.db import get_db_cursor
        from app.tools.review_tools import activate_video, list_pending_videos

        pending = await list_pending_videos()
        video_id = pending["videos"][0]["id"]
        await activate_video(video_id=video_id)

        def rows():
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT metric_date, impressions, dwell_time_seconds, circulation, revenue "
                    "FROM video_metrics WHERE video_id = ? ORDER BY metric_date",
                    (video_id,),
                )
                return [tuple(r) for r in cursor.fetchall()]

        first = rows()
        assert len(first) == 30
        # Re-run just the metrics generation path (activate_video refuses an
        # already-activated video, so exercise idempotent regeneration directly)
        from datetime import date, timedelta

        from app.database.db import get_demo_anchor_date
        from app.demo_data.constants import DEMO_WINDOW_DAYS
        from app.demo_data.derive import derive_video_metrics_rows

        with get_db_cursor() as cursor:
            anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            cursor.execute(
                "SELECT campaign_id FROM campaign_videos WHERE id = ?", (video_id,)
            )
            campaign_id = cursor.fetchone()["campaign_id"]
            for row in derive_video_metrics_rows(
                campaign_id,
                [video_id],
                anchor - timedelta(days=DEMO_WINDOW_DAYS - 1),
                anchor,
            ):
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO video_metrics
                    (video_id, metric_date, impressions, dwell_time_seconds, circulation, revenue)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["video_id"],
                        row["metric_date"],
                        row["impressions"],
                        row["dwell_time_seconds"],
                        row["circulation"],
                        row["revenue"],
                    ),
                )
        assert rows() == first  # INSERT OR IGNORE + determinism = idempotent


class TestGenerateAdditionalMetricsDeterministic:
    async def test_advances_anchor_and_extends_all_activated_videos(self, fresh_test_db):
        """The third call site: advancing the demo universe by N days moves
        the anchor and extends every activated video, atomically."""
        from datetime import date, timedelta

        from app.database.db import get_db_cursor, get_demo_anchor_date
        from app.tools.review_tools import generate_additional_metrics

        with get_db_cursor() as cursor:
            old_anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            cursor.execute(
                "SELECT id FROM campaign_videos WHERE status = 'activated' LIMIT 2"
            )
            activated = [r["id"] for r in cursor.fetchall()]
        assert len(activated) >= 2, "demo seed data provides activated videos"

        result = await generate_additional_metrics(video_id=activated[0], days=5)
        assert result["status"] == "success"

        with get_db_cursor() as cursor:
            new_anchor = date.fromisoformat(get_demo_anchor_date(cursor))
            assert new_anchor == old_anchor + timedelta(days=5)
            for vid in activated:
                cursor.execute(
                    "SELECT MAX(metric_date) AS hi FROM video_metrics WHERE video_id = ?",
                    (vid,),
                )
                assert cursor.fetchone()["hi"] == new_anchor.isoformat()
```

Run: `.venv/bin/pytest tests/unit/test_review_tools.py -k "Deterministic" -v`
Expected: FAIL (current code uses the old random generator and no anchor).

Defensive note: the tests above assume `list_pending_videos()` returns its list under a `"videos"` key — verify against the actual return in `app/tools/review_tools.py` before running, and adapt the key if it differs (do not change the tool).

- [ ] **Step 2: Swap both call sites and delete the old generator**

In `app/tools/review_tools.py`:

(a) Imports: add

```python
from ..database.db import get_db_cursor, get_demo_anchor_date, set_demo_anchor_date
from ..demo_data.constants import DEMO_WINDOW_DAYS
from ..demo_data.derive import derive_video_metrics_rows
```

(the first line replaces the existing `from ..database.db import get_db_cursor`). Remove `import random` if the old generator was this module's only user (verify: `grep -n "random\." app/tools/review_tools.py` — the mock thumbnail/video helpers around :482/:503 may also use it; only remove if genuinely unused).

(b) Add a module-level helper (near the other private helpers, above `activate_video`):

```python
def _insert_derived_metrics(cursor, ad_campaign_id, video_ids, date_from, date_to) -> int:
    """Insert derived deterministic rows; INSERT OR IGNORE keeps overlapping
    regeneration idempotent (UNIQUE(video_id, metric_date))."""
    inserted = 0
    for row in derive_video_metrics_rows(ad_campaign_id, video_ids, date_from, date_to):
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

(c) In `activate_video()`: the initial `SELECT status FROM campaign_videos WHERE id = ?` must also fetch `campaign_id` (`SELECT status, campaign_id FROM ...`). Replace the old generation block (:168-174, `# Generate mock metrics for this video ... _generate_mock_video_metrics(...)`) with:

```python
        # Deterministic metrics on the single anchor window [anchor-29, anchor]
        anchor = date.fromisoformat(get_demo_anchor_date(cursor))
        metrics_generated = _insert_derived_metrics(
            cursor,
            video["campaign_id"],
            [video_id],
            anchor - timedelta(days=DEMO_WINDOW_DAYS - 1),
            anchor,
        )
```

(d) In `generate_additional_metrics()`: keep the existence/activation checks; replace everything from the `# Get the last metric date` query through the `_generate_mock_video_metrics(...)` call with:

```python
        # Advance the demo universe: move the anchor forward by `days` and
        # fill the new dates for EVERY activated video, so no video lags the
        # anchor (single windowing rule, no per-video drift).
        old_anchor = date.fromisoformat(get_demo_anchor_date(cursor))
        new_anchor = old_anchor + timedelta(days=days)
        set_demo_anchor_date(cursor, new_anchor.isoformat())

        cursor.execute('''
            SELECT id, campaign_id FROM campaign_videos WHERE status = 'activated'
        ''')
        by_campaign: dict = {}
        for row in cursor.fetchall():
            by_campaign.setdefault(row["campaign_id"], []).append(row["id"])

        for cid, vids in by_campaign.items():
            _insert_derived_metrics(
                cursor, cid, vids, old_anchor + timedelta(days=1), new_anchor
            )

        # The response contract's count is for the requested video
        cursor.execute(
            "SELECT COUNT(*) AS n FROM video_metrics WHERE video_id = ? AND metric_date > ?",
            (video_id, old_anchor.isoformat()),
        )
        metrics_created = cursor.fetchone()["n"]
```

Keep the function's existing success-return shape (`status`, `message`, counts) exactly as-is, feeding it the new `metrics_created`.

(e) Delete the entire second `_generate_mock_video_metrics()` (review_tools.py:455-514).

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/unit/test_review_tools.py tests/unit/test_demo_meta.py -v`
Expected: all PASS, including the pre-existing `TestActivateVideo`/`TestGenerateAdditionalMetrics` classes (they assert only status/structure).

- [ ] **Step 4: Exit-criteria grep + full suite**

Run: `grep -rn "_generate_mock_video_metrics" app/ tests/`
Expected: no output (exit 1).

Run: `make lint && make test-unit && make test-e2e`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/tools/review_tools.py tests/unit/test_review_tools.py
git commit -m "Activate and extend metrics via deterministic derivation; delete old generators"
```

---

### Task 6: Mapping doc, docs updates, final verification sweep

**Files:**
- Create: `app/demo_data/BLUEZOO_MAPPING.md`
- Modify: `SETUP_INSTRUCTIONS.md`
- Test: none new — this task runs the full-suite + grep verification battery

- [ ] **Step 1: Write the mapping table**

Create `app/demo_data/BLUEZOO_MAPPING.md` with exactly:

```markdown
# BlueZoo mapping — demo-data mimic divergences

Naming policy (from the BlueZoo mapping verification,
`.docs/version2-plan/working-docs/replan-data-track/bluezoo-mapping-verification.md`):
**BlueZoo-literal column names inside deliberately renamed tables/frames**,
with every divergence enumerated here. Dates are **UTC day buckets** by
convention (BlueZoo's own daily-bucket timezone is open ask Q18).

## Provenance

Ported from `ad-campaign-agent` @ `b6e3302358d61892e388d7ff744b2aff0e04b399`
(branch `feat/plan3-slice1-bq-mvp`), read exclusively via `git show`:
- `seed.py` ← `services/audience_provider/seed.py` @ b6e3302
- constants ← `services/audience_provider/providers/mock_bigquery.py` @ b6e3302
  (`REVENUE_PER_IMPRESSION = 0.05`, deduplicated here into
  `constants.DEMO_RPI` — the donor repeated the literal in its
  `top_videos_by_revenue` SQL)

## Frame (table) renames — deliberate

| This repo (frame) | Donor | BlueZoo table |
|---|---|---|
| `screen_visits` | `store_visits` | `sensor_visits` (+ occupancy fields the donor merged in from `sensor_visitors` — the live adapter reads TWO tables) |
| `screen_dwell` | `store_dwell` | `sensor_dwell` |
| `campaign_uv_daily` | `campaign_uv_daily` | `group_uv_daily` (BlueZoo keys by `group_id`, no campaign column — the donor spec's claim otherwise was wrong) |
| `campaign_flow_transition` | `campaign_flow_transition` | `group_flow_transition` |
| `video_attribution` | `video_attribution` | (no BlueZoo equivalent — app-side concept, Phase 10 owns it) |

## Column divergences

| Here | Donor | BlueZoo | Why |
|---|---|---|---|
| `ad_campaign_id` | `campaign_id` | n/a (their `campaign_id` = unrelated flow-campaign concept) | METRICS.md do-not-conflate rule |
| `screen_id` | `store_id` | sensor/group ids | this repo's Phase 10 vocabulary |
| `minimum_/maximum_visitors_*` | `min_/max_visitors_*` | `minimum_/maximum_visitors_*` | BlueZoo-literal |
| `cuv_freq_1..10` FLOAT | INT | FLOAT64 | BlueZoo extrapolates from sampled MACs |
| dwell bin names HHMM (`distribution_bin_0100_to_0105`, boundary `_0058_to_0100`) | minutes encoding (61/106 wrong) | HHMM | verified against live docs |
| `total_visits` = inner-only (visits that ended in the slot) | inner+outer | inner-only | verified semantics |

## Provenance-flagged synthetic values (demo conventions, NOT BlueZoo mappings)

- `video_metrics.impressions` = `video_fraction × Σ incoming_inner_count`
  (inner-only IS the confirmed impressions mapping; the per-video fraction is
  the synthetic part — Phase 10's ad-play join replaces it).
- `video_metrics.revenue` = `impressions × DEMO_RPI` (0.05, flat — owner
  decision, ws05).
- `video_metrics.dwell_time_seconds`: synthetic 4–12 s scalar. The dwell
  histogram → scalar aggregation rule is deferred to Phase 11 per
  `docs/METRICS.md` — deliberately NOT derived from the bins.
- `video_metrics.circulation` = `video_fraction × Σ outgoing_outer_count`:
  "circulation" appears nowhere in BlueZoo's docs (Q5); demo convention only.
- `average_journey_duration_seconds` (flow frame): donor invention — BlueZoo
  keys journey duration by `number_of_groups_visited`, not per store pair.
```

- [ ] **Step 2: SETUP_INSTRUCTIONS note**

In `SETUP_INSTRUCTIONS.md`, in whatever section covers dependencies/installation, add one line noting numpy is now a direct dependency (demo-data generation) and existing environments need `make install` (or `pip install "numpy>=1.26.0"`) after pulling.

- [ ] **Step 3: Full verification battery**

Run each; expected results as stated:

```bash
grep -rn "_generate_mock_video_metrics" app/ tests/          # no output
grep -rn "0\.05" app/ --include="*.py" | grep -v demo_data   # no demo-RPI hits outside app/demo_data/ (unrelated 0.05s, if any, must be inspected and justified in the report)
grep -rnE "uniform\(0\.02, 0\.08\)|uniform\(0\.08, 0\.15\)" app/   # no output (old RPI ranges gone)
make lint && make test-unit && make test-e2e                 # all pass
make test                                                    # all pass (integration too)
```

- [ ] **Step 4: Commit**

```bash
git add app/demo_data/BLUEZOO_MAPPING.md SETUP_INSTRUCTIONS.md
git commit -m "Add BlueZoo mapping table and numpy setup note"
```

---

## Verification & finish (controller, after all tasks)

1. Full `make test` in the worktree venv.
2. `verifying-with-demo-scenarios`: STATUS → `verify in progress` (main checkout); run fashion F2 (both scenes) as chart regression over the new data; write and run new Scenario F3 (activate → top ads + chart → numbers consistent: displayed RPI == compute_rpi of displayed totals == 0.05); one verifier at a time on :8501.
3. Final whole-branch review (`scripts/review-package 1008c79 HEAD`), focus: five port corrections applied; donor repo untouched (`git -C /Users/lavi/gwork/ad-campaign-agent status` unchanged); exactly one RPI constant; both generators deleted; tool contracts unchanged.
4. `finishing-a-development-branch`: PR into `version_2`, owner confirms self-merge.
