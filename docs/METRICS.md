# Metrics Glossary

**This is the single source of truth for what every metric in this app means.** Read it before touching any metric-related code. Phase 4 (`.docs/version2-plan/04-centralize-rpi-metrics.md`) turns the RPI rule below into the one shared implementation (`compute_rpi()`); until then, no code file is authoritative — this document is.

Definitions are aligned to BlueZoo's own vocabulary wherever BlueZoo defines the term (quotes below were verified against the live BlueZoo Data Warehouse API docs at `api.bluezoo.io`, fetched 2026-07-16). Where a mapping is *not* confirmed, this document says so explicitly rather than guessing.

## Impressions

**One inner-zone visit event, attributed to a specific screen (sensor) and time window.**

This adopts BlueZoo's definition verbatim — BlueZoo's `sensor_visits` table is captioned: "Sensor Visits measure the number of devices seen within the inner detection range of a sensor, **also known as impressions**." An impression is an *event count* (a device entered the inner detection zone), not an occupancy snapshot and not a deduplicated person count — see the appendix for the neighboring concepts it must not be conflated with.

In this app: the `video_metrics.impressions` column (one integer per activated video per day).
Derivation (demo mode): sum of `incoming_inner_count` over the 15-min slots the
creative actually played (its deterministic `AdPlayRecord` schedule within its
`video_attribution` windows, across the campaign's 2–3 screens). Inner-only, as
before. (Phase 10: derived through the ad-play join, no longer a per-video
daily fraction.)

## Revenue

**The point-of-sale revenue for the advertised product, at the store showing the ad, over the same time window as the impressions it is paired with.**

Revenue is **not a BlueZoo metric** — BlueZoo sensors measure audience attention, not sales. Revenue enters the system from a separate source (point-of-sale data or an attribution model; see `.docs/version2-plan/12-live-pos-adapter.md`). RPI is only meaningful once both sides — BlueZoo impressions and PoS revenue — are joined over the same product, store, and window.

In this app: the `video_metrics.revenue` column (mock-generated in demo mode).

## Revenue per Impression (RPI)

**RPI = total revenue ÷ total impressions, computed over a given window.**

This is the app's primary KPI, and it is BlueZoo's own coined, marketed metric. The client's operational framing (from the project README): retailers normalize each store's point-of-sale revenue for the advertised product by the number of impressions delivered for that store's ad during a day.

**The one non-negotiable computation rule: RPI over any multi-period window is the *ratio of sums, never the sum (or average) of per-period ratios*.** A weekly RPI is sum(revenue over the week) ÷ sum(impressions over the week) — it is *not* the sum or mean of seven daily RPI values. Summing ratios produces a number with no meaning (this exact bug existed in the weekly bar chart and is fixed by Phase 4's centralization). Any code that aggregates RPI across days, videos, campaigns, or stores must recompute from the summed numerator and denominator.

Derived convenience form: revenue per 1,000 impressions (`RPI × 1000`, a CPM-style figure) — same rule applies.

Zero-impressions convention: the shared implementation (`compute_rpi()` in `app/tools/metrics_shared.py`, added by Phase 4) returns `0.0` when total impressions are zero — "no impressions yet" is reported as zero RPI, not an error or null. A caller that needs to distinguish "no data" from "genuinely zero RPI" must check the impressions count, not the ratio.

Derivation (demo mode): each creative has a deterministic per-(campaign,
video) RPI in the band [0.03, 0.07] (Phase 7); this keying and formula are
unchanged by Phase 10. What changed is *how the paired revenue number is
attributed* — revenue is now computed per play window (`play visits ×
video_rpi`) at the ad-play join, rather than as a single per-video daily
scalar, and those per-window amounts sum to the same daily `impressions ×
rpi` total as before.

## Circulation

**App-local synthetic metric; BlueZoo mapping unresolved.**

The `video_metrics.circulation` column exists in this app's schema and is populated by the demo-mode mock generator, but it has **no confirmed BlueZoo counterpart**. Candidate interpretation (unconfirmed): broader foot-traffic / opportunity-to-see near a screen — possibly BlueZoo `sensor_visitors` occupancy or an outer-zone visit count — as distinct from impressions (inner-zone attention). That is a plausible retail-signage-industry pattern (circulation = OTS, impressions = actual attention) but it has **not been confirmed against BlueZoo's docs or the client's own usage**. Do not build anything on the candidate mapping; see open question 5 ("`circulation` metric definition (Phase 3 glossary — does not block Phase 3 itself)") in `.docs/version2-plan/99-open-questions.md`.

Derivation (demo mode): sum of `outgoing_outer_count` over the creative's
played slots — still the synthetic demo convention (the term appears nowhere
in BlueZoo's docs); real semantics deferred to Phase 11.

## Dwell time

**App-local scalar average; BlueZoo alignment requires an aggregation rule, unresolved until Phase 11.**

This app's `video_metrics.dwell_time_seconds` column stores **one scalar average per video per day**. BlueZoo's `sensor_dwell` is *not* that: it is "a distribution of visit durations per 15-minute slots" — i.e., visit-duration *bins*, not a single number. Mapping the distribution onto our scalar requires a defined, documented aggregation rule (e.g., a weighted mean across bins) that must be validated against a real BlueZoo response before it is written down as fact — that validation belongs to Phase 11 (`.docs/version2-plan/11-live-bluezoo-adapter.md`). Until then, treat our column as demo-mode synthetic data with intentionally unresolved provenance.

**Update (live schema scan, 2026-07-25): the aggregation rule is "don't aggregate — read BlueZoo's own scalar."** An authenticated `desc_table` against a live account found that `sensor_dwell` also ships **`distribution_average_duration`** and **`distribution_median_duration`**, neither of which appears in BlueZoo's published documentation. So the live mapping onto our scalar is a direct read, not a bin-midpoint weighted mean. Two caveats keep this paragraph short of settling the entry: the account scanned has zero rows, so the columns' **units and scale are unverified** (as is the bin values' 0–1-vs-0–100 scale), and demo-mode data stays synthetic regardless. Phase 11 still owns writing the rule down as fact once real rows exist. Record: `.docs/version2-plan/working-docs/bluezoo-live-verification/findings.md`.

**Resolved (real-data verification, 2026-07-27).** The caveats above are now closed, against a tenant with 5.1M real rows (MO_92; `findings.md` Part 5.2). The rule for live mode:

- **`distribution_average_duration` and `distribution_median_duration` are integer SECONDS** — observed 260 s, 402 s, 160 s. That is a **direct 1:1 mapping onto `dwell_time_seconds`.** Read the scalar; do not derive one from the histogram.
- **The 106 bins are 0–100 percentages, not 0–1 shares** — one sampled slot's first three bins alone sum to 62.9. Anything that does consume the histogram must not treat bins as fractions; that would be a 100× error.
- **Dwell can legitimately be NULL.** When `distribution_weight` is `0.0`, every bin is `0` and **both scalars are NULL**, while `total_visits` is still non-zero. Null dwell is "no distribution derivable for this slot," not a fault — a live conformer must carry it through rather than coercing it to `0`, which would silently drag any average down.

Demo-mode data remains synthetic with unchanged provenance; this governs the live path only.

## Appendix: BlueZoo table map (do-not-conflate notes)

| BlueZoo table | What it measures | Relationship to this app |
|---|---|---|
| `sensor_visits` | Inner-zone visit counts — "also known as impressions" (BlueZoo's own caption) | **= our impressions.** The one confirmed 1:1 mapping. |
| `sensor_visitors` | Occupancy (min/avg/max) per 15-minute period | *Not* visits: occupancy is a point-in-time count, visits are events. Candidate (unconfirmed) relative of circulation. |
| `sensor_dwell` | Distribution of visit-duration bins (**0–100 percentages**) per 15-minute slot, **plus undocumented `distribution_average_duration` / `distribution_median_duration` scalars, in integer seconds** (verified against real data 2026-07-27) | **= our `dwell_time_seconds`, read directly.** Do not weight bins. NULL when `distribution_weight = 0`; carry the null through rather than coercing to 0. |
| `sensor_visits` `valid` column | Per-**sensor** (not per-slot) status that flips over a sensor's lifetime; `null` is an undocumented third state | **Unresolved and high-stakes:** `valid=false` is half of all rows and 72% of all counts. Whether to exclude it swings impressions ~4×. Make the policy explicit and logged; see open question 18. |
| `sensor_visitors_per_minute` | Fine-grained occupancy time series | Unused today; candidate input for playout attribution (Phase 10). |
| `group_uv_daily/weekly/monthly/custom` | Unique visitor counts, deduplicated over a period | "Unique reach" — a *different* metric from impressions; never conflate deduplicated visitors with visit counts. See open question 6 ("Unique-reach metric (Phase 3 glossary)") in `.docs/version2-plan/99-open-questions.md`. |
| `group_flow_transition/correlation/duration/segmentation` | Cross-zone traffic-flow journeys | Carries a `campaign_id` field that is **BlueZoo's own "flow campaign" concept — unrelated to this app's ad campaigns.** When mapping BlueZoo data, never reuse the bare name `campaign_id` for this app's ad-campaign id; pick a distinct field name (e.g. `ad_campaign_id`) to avoid collision. |
| `sensor_pulses` | Sensor telemetry/health (uptime, connectivity) | Not audience data — must never appear in any impressions/revenue rollup. |
