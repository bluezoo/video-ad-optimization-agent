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

from datetime import date, timedelta

from ..models.attribution import AdPlayRecord
from .constants import DEMO_RPI
from .seed import _seeded_rng, _slot_starts

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
