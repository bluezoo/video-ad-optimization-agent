# Phase 2 — Metrics Glossary & Terminology Alignment

## Goal

Write down one authoritative definition for every metric this app uses (impressions, RPI, revenue, circulation, dwell time), aligned to BlueZoo's own vocabulary where BlueZoo already defines the term. This becomes the single source of truth Phase 3 (centralization) and Phase 10 (live BlueZoo adapter) both build on.

## Why this is smaller than the original plan assumed

The original plan treated impressions/RPI terminology as something needing a translation layer between "this app's concept" and "BlueZoo's concept." Having now read BlueZoo's actual Data Warehouse API docs (`https://api.bluezoo.io/#89e2277d-43ef-424b-b4d6-6f473538f108`), that's mostly not true: BlueZoo already defines "impressions" as inner-zone visit counts, and this app's usage is already compatible. This phase is "adopt and document BlueZoo's existing definitions," not "invent a reconciliation."

## Current state

This app currently computes metrics in **at least 13 different places** (per direct codebase read), each with its own inline formula and no shared definition:

- `app/database/mock_data.py:168-235` — `_generate_mock_video_metrics()`, one RNG range for impressions/RPI.
- `app/tools/review_tools.py:454-513` — a **second**, independently-written `_generate_mock_video_metrics()` with different RNG ranges (see Phase 4 for the fix).
- `app/tools/metrics_tools.py` — `get_campaign_metrics()`, `get_top_performing_ads()`, `get_campaign_insights()`, `compare_campaigns()`, `generate_metrics_visualization()` — each recomputes revenue/impressions aggregates and RPI independently.
- `app/tools/campaign_tools.py:184-292` (`get_campaign()`) — recomputes RPI again.

No single function or constant currently defines what these terms mean; every call site re-derives them from raw column math.

BlueZoo's own definitions (from `api.bluezoo.io` docs, fetched directly):

| BlueZoo table | What it measures | Notes |
|---|---|---|
| `sensor_visits` | Inner-zone visit counts | **Explicitly captioned "also known as impressions"** in BlueZoo's own docs |
| `sensor_visitors` | Occupancy (min/avg/max) over a time window | Not the same as visits — occupancy is a point-in-time count, visits are an event count |
| `sensor_dwell` | Dwell time | **Correction from review — does not map directly.** BlueZoo's `sensor_dwell` is a *distribution of visit-duration bins* for visits ending within a 15-minute slot, not a single scalar. This app's `dwell_time_seconds` column (`app/database/db.py:139-151`) stores one scalar average per video/day. Mapping one to the other requires a defined, documented aggregation rule (e.g., a weighted mean across bins) — do not treat this as a direct 1:1 mapping in the glossary; write it down as "requires an aggregation rule, unresolved" and validate against a real BlueZoo response before finalizing (Phase 10). |
| `sensor_visitors_per_minute` | Fine-grained occupancy time series | Not currently used by this app; may be useful for playout attribution (Phase 9) |
| `group_uv_daily/weekly/monthly/custom` | Unique visitor counts, deduplicated over a period | Different metric from raw visit/impression counts — do not conflate |
| `group_flow_transition/correlation/duration/segmentation` | Cross-zone traffic-flow journeys | Has a `campaign_id` field — **this is BlueZoo's own "flow campaign" concept, unrelated to this app's ad-campaign concept.** Do not reuse the name `campaign_id` for this app's ad campaigns when mapping to/from BlueZoo data; pick a distinct field name to avoid collision. |
| `sensor_pulses` | Sensor telemetry/health (uptime, connectivity) | Not audience data — do not include in any impressions/revenue rollup |

BlueZoo's RPI (revenue-per-impression) is confirmed (via a direct the client quote in BlueZoo's own marketing materials) to be BlueZoo's own coined, marketed metric — `revenue / impressions`. This app already computes the same ratio; the glossary just needs to make the formula canonical and consistent everywhere.

## Steps

**Correction from review:** the original draft of this phase proposed a Python module full of prose docstring/constants (`IMPRESSION_DEFINITION`, `RPI_FORMULA` as strings). That's indirection without enforcement — a string constant doesn't stop a call site from ignoring it. Put the human-readable definitions in a plain markdown doc instead, and let Phase 3's actual code (`compute_rpi()`, typed metric identifiers) be the only place a definition is expressed as something executable.

1. Create `docs/METRICS.md` with the definitions below, in plain prose — this is the single source of truth a human (or an implementation model) reads before touching any metric-related code:
   - **Impressions**: one inner-zone visit event, attributed to a specific screen and time window (matches BlueZoo `sensor_visits`).
   - **RPI**: `total_revenue / total_impressions`, computed over a given window — **ratio of sums, never sum of ratios** (this directly codifies the fix Phase 3 implements as code, so it's written down here as the rule that code must follow, not fixed twice).
   - **Circulation** (the `video_metrics.circulation` column, `app/database/db.py:139-151`): written explicitly as **"app-local synthetic metric; BlueZoo mapping unresolved, see open question below"** rather than a guessed mapping. This unblocks Phase 3 (which just needs *a* definition to centralize against) without requiring the BlueZoo-alignment question to be answered first.
   - **Dwell time** (`dwell_time_seconds`): written as **"app-local scalar average; BlueZoo `sensor_dwell` alignment requires a bin-aggregation rule, unresolved until Phase 10"** — same pattern as circulation, don't overclaim a mapping that hasn't been validated against real data yet.
   - **Revenue**: explicitly **not** a BlueZoo metric — BlueZoo measures audience/attention, not sales. Revenue comes from a separate source (PoS or attribution model — see Phase 11), and RPI is only meaningful once both sides are joined.
2. Link `docs/METRICS.md` from `README.md`, replacing any ad-hoc metric explanations currently scattered in code comments.
3. Do **not** create a Python constants module and do **not** yet change any of the existing metric-computation call sites — the precise, corrected inventory of every call site lives in Phase 3 (the original estimate of roughly 13 sites undercounted a few, found during review). This phase only establishes the definitions, in documentation, with zero executable code.

## Validation

- [ ] `docs/METRICS.md` exists, is linked from `README.md`, and contains no code — this phase is documentation only, not refactoring.
- [ ] No behavior change: `make test` passes unchanged, since no runtime code path has been touched.

## Exit criteria

One authoritative definition exists in `docs/METRICS.md` for impressions, RPI, revenue, circulation, and dwell time — with circulation and dwell time explicitly marked as "BlueZoo mapping unresolved" rather than blocking on that mapping being confirmed first.

## Dependencies

None — pure documentation/constants, safe to do any time. Sequenced here because Phase 3 needs it.

## Open questions

1. **What does `circulation` mean in this app's schema, and does it map to a specific BlueZoo table?** Candidate mapping (unconfirmed): `circulation` = broader foot-traffic/opportunity-to-see count near a screen (possibly BlueZoo `sensor_visitors` occupancy, or an outer-zone visit count), as distinct from `impressions` = inner-zone attention count (BlueZoo `sensor_visits`). This is a plausible retail-signage-industry pattern (circulation = OTS, impressions = actual attention) but is **not confirmed** against BlueZoo's docs or the client's own usage — needs a direct check with BlueZoo before being written into the glossary as fact.
2. Does BlueZoo have a canonical definition of "unique reach" (via `group_uv_*`) that this app should surface as a distinct metric from impressions, or is impressions-only sufficient for the RPI use case the client cares about?
