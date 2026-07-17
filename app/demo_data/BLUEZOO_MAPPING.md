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
