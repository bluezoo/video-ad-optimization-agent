# Phase 6 — RPI-Across-Creatives Comparison

## Goal

Ship the specific comparison view Bill is most likely to want to see live: RPI, side by side, across the different video creatives/variations in a campaign. This is BlueZoo's own flagship metric (RPI), applied to the thing this app's whole loop exists to produce (multiple creative variations competing on performance).

## Why this is pulled forward, and why it needs Phases 3-4 first

RPI-across-creatives is only trustworthy once (a) RPI is computed the same way everywhere (Phase 3) and (b) demo data isn't internally inconsistent (Phase 4). Building this comparison view before those two phases would mean showing Bill a chart whose numbers might not even agree with each other depending on which code path generated them — worse than not showing it at all.

## Current state

- `compare_campaigns()` (`app/tools/metrics_tools.py:608-717`) compares at the campaign level, not the creative/variation level within a campaign — the granularity Bill actually wants ("which of these video variations won") isn't directly exposed today.
- `generate_metrics_visualization()` (`app/tools/metrics_tools.py:720-1061`) renders charts by prompting an **image-generation model** to draw them (`CHART_TEMPLATES`, lines 35-166), rather than using a deterministic charting library. This means the visual representation of the numbers is not guaranteed to match the numbers — an LLM drawing "a bar chart with these values" can visually misrepresent proportions, labels, or ordering. This was correctly flagged as a concern in the original plan and is carried forward here.

## Steps

1. Add a variation/creative-level comparison function (e.g., `compare_creatives_within_campaign(campaign_id)`) alongside `compare_campaigns()`, using `compute_rpi()` from Phase 3 and the deterministic data from Phase 4. It should return, per video/variation: RPI, total impressions, total revenue, and whatever variation metadata already exists (`app/models/variation.py`'s `CreativeVariation` fields — setting, mood, etc.) so the comparison is legible, not just a list of IDs.
2. For the actual chart/visualization: do not extend the AI-image-rendering approach (`CHART_TEMPLATES`) to this new comparison. Instead, render it with a deterministic charting library. **Confirmed during review: `matplotlib` is not currently in `app/requirements.txt`** — this phase must add it explicitly as a new dependency, not assume it's already available.
3. **Define the output/artifact contract explicitly before implementing** — this was underspecified in the first draft. The existing chart tool (`generate_metrics_visualization()`, `app/tools/metrics_tools.py:720-1061`) saves its output as an ADK artifact via `ToolContext`, not as an ordinary local file. Decide whether the new tool follows the same pattern (PNG bytes saved through `ToolContext`, consistent with the rest of this app's tool conventions) or returns a GCS URL — and document the choice, since it affects both the implementation and how the Analytics Agent's instruction should describe the tool's output to the LLM.
4. Expose this as a new tool the Analytics Agent can call — add it to the Analytics Agent's tool list and instruction text (`app/agent.py:365` is the current tool list to extend), with a clear description distinguishing it from the existing campaign-level `compare_campaigns()`.
5. Return both the chart artifact (for visual demos) and the underlying structured data (for cases where a human or another agent wants the numbers directly, not just an image) — this is a small addition since the data is already computed in step 1.

## Validation

- [ ] `compare_creatives_within_campaign()` returns correct, `compute_rpi()`-consistent figures for a campaign with multiple activated video variations (test against Phase 4's deterministic fixtures — same seed in, same comparison out, every run).
- [ ] The rendered chart's bar heights/values are generated programmatically from the same data structure the function returns (not independently re-derived or re-prompted), so a unit test can assert the chart's underlying data matches the function's return value exactly.
- [ ] Manually exercise this through the ADK web UI (`make dev`) with a campaign that has 2+ activated variations with different RPI, and confirm the comparison reads correctly and matches what `get_campaign_insights()` / `compare_creatives_within_campaign()` report independently.

## Exit criteria

Bill (or anyone) can ask the Analytics Agent "which of these creatives is winning" and get a correct, deterministically-rendered RPI comparison across the campaign's video variations.

## Dependencies

Phase 3 (shared `compute_rpi()`), Phase 4 (deterministic demo data so the comparison is stable across demo runs).

## Open questions

None functionally — this is a new read-only reporting feature built on already-established groundwork. If a specific visual chart style/branding is expected for demos in front of Bill, confirm that separately; it doesn't block building the correct underlying data path.
