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
