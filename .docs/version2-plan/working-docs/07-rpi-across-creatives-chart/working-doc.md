# Workstream 07: rpi-across-creatives-chart

**Branch:** version_2_rpi-chart
**Phase doc:** .docs/version2-plan/07-rpi-across-creatives-chart.md (deps: Phases 4, 5 — both merged)
**Base:** version_2 @ 49ae21b (post-ws06 merge)

## Research findings

Kickoff research (2026-07-19, three parallel agents: metrics/agent surface, chart/artifact surface, flat-RPI design space). All phase-doc claims hold; line numbers drifted:

- `compare_campaigns()` is now `app/tools/metrics_tools.py:656-764` (doc said 608-717); campaign-level only, RPI via `compute_rpi()` (which lives at `app/tools/metrics_shared.py:14`, signature `compute_rpi(total_revenue: float, total_impressions: float) -> float`, ratio-of-sums per METRICS.md).
- `generate_metrics_visualization()` is now `:788-1125`, `CHART_TEMPLATES` at `:34-165`; AI-image-drawn charts confirmed. Its **artifact contract** is the pattern to copy: async tool, trailing `tool_context: ToolContext = None`, PNG bytes → `types.Part.from_bytes(mime_type="image/png")` → `await tool_context.save_artifact(...)`, graceful no-artifact branch when `tool_context is None`, returns metadata + `data_summary` (never bytes).
- `app/agent.py:365` (`analytics_agent = LlmAgent(`) and `:370` (`tools=[`) — exactly right; instruction `ANALYTICS_AGENT_INSTRUCTION` at `:289-363` has a clear house style (per-tool `##` section + Response Guidelines entry).
- `matplotlib` absent from `app/requirements.txt` — confirmed, must be added.
- **Reuse target:** `get_campaign_insights` already runs the per-video aggregation this phase needs (`metrics_tools.py:574-591`: GROUP BY video, activated-only, SUM revenue/impressions, variation metadata, per-video RPI at `:613`). `get_top_performing_ads` overlaps too but ranks/limits and *drops zero-revenue videos* (HAVING at `:374`) — wrong semantics for a complete side-by-side comparison.
- **Anchor-vs-now hazard:** existing `days` filters use SQLite `date('now', …)`, but ws05 demo data lives in a fixed `[anchor−29, anchor]` window — a days filter can silently exclude demo rows as `now` drifts. The new comparison defaults to all-time (no days filter).

**DISCOVERY (ws05 latent gap):** ws05 added `numpy` to `app/requirements.txt` but NOT to `scripts/deploy_ae_inline.py`'s requirements list (`:291-298`). Agent Engine repopulates the DB from mock data on restart, and `mock_data.py → demo_data/derive.py → seed.py` imports numpy at module level — an AE deploy today would crash at import. Fixed in this workstream (one line) since we're touching that list for matplotlib anyway; logged per the Discoveries protocol.

## The flat-RPI decision (owner gate — this is the headline question)

ws05's owner decision made demo revenue = `round(impressions × 0.05, 2)` (`app/demo_data/constants.py:12`, `derive.py:94`), so **RPI is exactly 0.05 for every creative — the phase's namesake chart is a flat line over unmodified data**. Impressions/revenue *magnitudes* genuinely differ per creative (up to ~2.4× via the seeded `video_fraction` band [0.25, 0.6]); only the ratio is constant. Downstream phases verified clean: Phase 10 deletes `derive.py` wholesale; Phase 11 only requires one canonical RPI constant.

**Option A — deterministic per-creative RPI factor (constant across days). RECOMMENDED.**
Add `video_rpi(ad_campaign_id, video_id)` beside `video_fraction` in `derive.py`: `DEMO_RPI × (0.6 + seeded_uniform × 0.8)` → each creative gets a stable RPI in [0.03, 0.07]; revenue line becomes `impressions × video_rpi(...)`. Same sha256 seeding → cross-process determinism; keyed per (campaign, video) → no-discontinuity preserved untouched; `DEMO_RPI` stays the single canonical base constant (Phase 11 requirement). Each creative's ratio is still ONE exact constant across its 30 days — internal-consistency checks keep their teeth, the constants just differ per creative (so "which creative is winning" has a real, stable answer, and RPI ranking ≠ impressions ranking).
*Blast radius:* one test (`test_demo_derive.py::test_revenue_is_flat_demo_rpi` → per-creative-constant + band + differs-across-creatives), Scenario F3.2's pass criteria (same reshape), two docstrings, provenance amendments in the 07 phase doc. Reverses the ws05 strict-flat decision — which is exactly the deferred tension this gate exists to resolve.

**Option B — keep flat RPI; chart leads with impressions + revenue bars, RPI annotated.**
Zero data-layer change. But the flagship metric carries no information; an RPI row pinned at exactly 0.05 for every creative looks like a bug in a live demo; and with flat RPI the revenue ranking is definitionally identical to the impressions ranking (redundant bars). Dwell can't differentiate either (pure per-day noise, no per-video signal).

**Option C — Option A + per-day RPI jitter (±10% around each creative's mean).**
Most realistic-looking trendlines, but destroys the exact internal-consistency check (F3.2's whole point — catching a legacy random-generator leak) for realism inside a layer Phase 10 deletes anyway. The cross-creative aggregate chart looks identical to A's.

Recommendation: **A** — the only option that makes the phase's actual deliverable real, confined to the disposable layer, inheriting every ws05 invariant mechanically, with a small, fully-enumerated blast radius.

## Implementation approach

1. **Data-layer change per the owner's Option choice** (A assumed): `video_rpi()` in `app/demo_data/derive.py` + revenue line change; update `test_demo_derive.py` flat-RPI test, Scenario F3.2 criteria, `constants.py`/`derive.py` docstrings; provenance amendments (07 phase doc's ws05 note gets a resolution note).
2. **`compare_creatives_within_campaign(campaign_id: int)`** in `app/tools/metrics_tools.py`: per-video aggregation (activated-only, all-time window — anchor hazard above), one `compute_rpi()` call per video (ratio-of-sums), returns per creative: video_id, variation_name + parsed variation metadata (setting/mood/etc. from `variation_params`, same parse as `get_top_performing_ads:382`), total_impressions, total_revenue, average_dwell, RPI, rpi_rank — plus a campaign-level summary and winner. Includes zero-metric activated videos (explicitly, with zeroed metrics) rather than silently dropping them.
3. **Deterministic chart:** new async tool `generate_creative_comparison_chart(campaign_id, tool_context=None)` — matplotlib **Agg via `Figure` + `FigureCanvasAgg` directly (no pyplot global state in the async server)**, rendered to `io.BytesIO`, 16:9 (figsize 12.8×7.2 @ 100dpi, documented as a new convention), bar chart of RPI per creative labeled with variation names; artifact saved via the exact existing ToolContext pattern; returns artifact metadata + the same structured comparison data (chart data and returned data come from ONE `compare_creatives_within_campaign()` call, so a unit test can assert chart-input == function-return exactly, per phase validation).
4. **Dependencies:** `matplotlib` added to `app/requirements.txt` AND `scripts/deploy_ae_inline.py`; numpy DISCOVERY fix in the same deploy list.
5. **Agent wiring:** both new tools added to the Analytics Agent tool list (`app/agent.py:370`), instruction extended in house style (own `##` section + Response Guidelines entry distinguishing creative-level from campaign-level `compare_campaigns`).
6. **Not touched:** the existing AI-image `generate_metrics_visualization` path (stays as-is for its four chart types), `CHART_TEMPLATES`, seed.py frames, DB schema.

## Test plan

- Unit: `compare_creatives_within_campaign` correctness against seeded deterministic data (known video fractions/RPI factors → exact expected values; rpi ranking independent of impressions ranking under Option A); zero-metric-video inclusion; single-video campaign; nonexistent campaign error. Chart tool: first-ever ToolContext mock (AsyncMock `save_artifact`) asserting PNG bytes + filename pattern; chart-data-equals-return-data assertion; `tool_context=None` graceful branch. No `slow` marker needed (deterministic render, no API).
- Updated: `test_demo_derive.py` flat-RPI test per Option A; `make test` fully green.
- Demo scenarios: re-run **F3** (updated criteria under Option A: each creative's ratio constant-across-days, within [0.03, 0.07], differing across creatives); write and run **new Scenario F4** — "which of these creatives is winning" → `compare_creatives_within_campaign` and/or the chart tool fire, response names the top creative by RPI with correct numbers, chart artifact renders (screenshot evidence).

## Out of scope

- No change to the AI-image chart path (`generate_metrics_visualization`, `CHART_TEMPLATES`) — deterministic charting is added alongside, not replacing.
- No per-day RPI jitter (Option C rejected unless owner picks it); no tying RPI to variation attributes.
- No GCS-URL output contract (artifact-via-ToolContext chosen, matching every existing visual tool).
- No Phase 10 attribution logic; `derive.py` remains the disposable layer Phase 10 replaces.
- README.md / DEMO_GUIDE.md untouched.
