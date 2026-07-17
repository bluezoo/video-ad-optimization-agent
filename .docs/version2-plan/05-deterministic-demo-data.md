# Phase 5 — Deterministic Demo Data (port the donor generator)

> **Amended (workstream replan-data-track, 2026-07-16):** rewritten from "hand-build a deterministic generator" to "port the proven generator from the donor repo." The owner's personal repo `/Users/lavi/gwork/ad-campaign-agent` (this repo's upstream ancestor — see `99-open-questions.md` Q1) contains a working, tested, deterministic, **BlueZoo-shaped** metrics generator (`services/audience_provider/seed.py`) that supersedes the design this phase originally planned to invent. Porting it also serves the owner's stated prime motive: closest possible alignment with BlueZoo's data schema and metrics. Original current-state analysis below remains valid and is kept.

## Goal

Replace the two independently-drifted random-metric generators (called from three separate places) with **one deterministic, BlueZoo-shaped generator ported from the donor repo**, so demo numbers are reproducible, internally consistent, and already shaped like the data BlueZoo's real sensors will eventually supply.

## Current state (confirmed live bug — corrected to three call sites, not two)

Two separate functions named `_generate_mock_video_metrics()` exist and disagree, and there are **three** call sites across them, not two:

- `app/database/mock_data.py:168-235` — impressions range 800-2000, `revenue_per_impression = random.uniform(0.02, 0.08) * multiplier`. Called from `populate_mock_data()` at line 383. **Its date window runs backward from today** (`mock_data.py:188`) — i.e., "the last N days."
- `app/tools/review_tools.py:454-513` — a **completely separate implementation**, impressions range 800-1500, RPI range $0.08-$0.15. Called from two places: `activate_video()` at `review_tools.py:168`, **and** `generate_additional_metrics()` at `review_tools.py:563` (this second call site was missed in the first draft of this phase). **Its date window runs forward from a supplied start date** (`review_tools.py:484`) — the opposite direction from the seed-time generator.

Result: two videos activated in the same demo session, seeded from the same "mock data," can show RPI figures that differ by nearly 2x purely because of which function happened to generate them — a visible inconsistency in a live demo, and a correctness problem for the RPI-across-creatives comparison the client specifically asked about (Phase 7 depends on this being fixed first). **A single shared seed alone does not fix this** — the two generators don't just disagree on RNG ranges, they disagree on which direction time runs, so unifying them requires one anchor-date-and-direction model, not just one RNG.

## The donor generator (what gets ported)

`ad-campaign-agent`'s `services/audience_provider/seed.py` (~200 lines + tests):

- **Deterministic by construction:** SHA-seeded `random.Random` per `(campaign_id, store_id, date)` — byte-identical reruns across processes, no `PYTHONHASHSEED` dependence. This is exactly the stable-hash requirement this phase's first draft specified by hand.
- **BlueZoo-shaped output:** 15-minute sensor grain (48 slots, 09:00–21:00), visit counts (inner/outer, incoming/outgoing), dwell-time *distributions* (106 histogram bins, matching BlueZoo's `sensor_dwell` shape), unique-visitor frequency buckets, flow transitions.
- **Demo realism baked in:** lunch/after-school peaks, weekend multipliers, per-campaign uplift factors — numbers that look credible in front of a prospect without hand-tuning.
- **Data ships as code**, not fixtures: any `(campaign, store/screen, date)` key yields deterministic data on demand — which is what lets a freshly onboarded product (Phase 15) get plausible metrics with zero fixture authoring.

## Port corrections — verified against BlueZoo's live published API docs (2026-07-16)

> **Amended (workstream replan-data-track, 2026-07-16):** at the owner's request, the donor schema was verified field-by-field against the live `api.bluezoo.io` docs before implementation (full record: `working-docs/replan-data-track/bluezoo-mapping-verification.md`). Verdict: **partial — proceed, but do not port verbatim.** The donor's structure is confirmed real (14-table inventory, 106 dwell bins, grain layout, 15-min slots, exact `sensor_visits` column names all match the live docs), but the port must correct:
>
> 1. **Dwell bin names → HHMM encoding.** 61 of 106 donor bin names use minutes (`distribution_bin_0060_to_0065`); BlueZoo's real names are HHMM (`distribution_bin_0100_to_0105`; boundary bin `_0058_to_0100`, not `_0058_to_0060`). Regenerate the names and fix the in-memory provider's minutes-assuming midpoint decoder.
> 2. **`campaign_id` → `ad_campaign_id` on every table** (METRICS.md's rule; BlueZoo's own `campaign_id` on flow tables means their unrelated flow-campaign concept). Also correct the donor spec's wrong claim that BlueZoo stamps campaign on `group_uv_*` (those are `group_id`-keyed).
> 3. **Impressions = inner-only**, as step 3 below already mandates — the donor code computes inner+outer; follow this plan, not the donor. Replace the hard-coded `0.05` in the donor's `top_videos_by_revenue` SQL with the step-4 canonical constant.
> 4. **Circulation stays provenance-flagged synthetic** — the donor hard-wires `circulation = outgoing_outer_count`, exactly the candidate mapping Q5/METRICS.md forbid ("circulation" appears nowhere in BlueZoo's docs).
> 5. Smaller alignments: `min_/max_visitors_*` → `minimum_/maximum_visitors_*`; `cuv_freq_*` INT64 → FLOAT64; document that BlueZoo's `sensor_dwell.total_visits` means visits that *ended* in the slot (inner-only) and that per-pair `average_journey_duration_seconds` is a donor invention.
>
> **Pin the donor revision:** the donor tree is dirty on exactly these files (committed HEAD `b6e3302` differs from its working tree on `mock_bigquery.py`) — record per ported file which revision it came from. **Naming policy for the whole mimic:** BlueZoo-literal *column* names inside deliberately renamed *tables*, with every divergence enumerated in one mapping table (kept with the ported spec), so column fidelity and the accepted table renames don't get re-litigated. Demo data uses **UTC day buckets**, documented as a convention (BlueZoo's daily-bucket timezone is an open ask — see Q18).

## Steps

1. Port `seed.py` from the donor into this repo (e.g. `app/demo_data/seed.py` for now — the provider-seam home arrives in Phase 11a; keep the module import-light so relocating it later is mechanical). Port its unit tests alongside. Adapt naming to this repo's vocabulary (`screen` where the donor says `store`, per Phase 10's `Screen` concept) and key generation off this app's IDs.
2. **Reconcile date-window semantics** (unchanged requirement from the first draft): one fixed demo anchor date (set when the demo DB is seeded) and one explicit windowing rule, applied identically at seed time and at activation time. Both existing call-path behaviors (backward-from-today and forward-from-start-date) are replaced by this one rule.
3. Add a thin derivation layer that aggregates the generator's BlueZoo-shaped 15-minute visit frames into the per-video daily rows the current `video_metrics` table and tools consume (`impressions` = sum of inner visit counts over the video's active windows for that day; `revenue` = impressions × the canonical RPI constant; stored RPI via `compute_rpi()` from Phase 4, never an inline multiplication). **This keeps Phase 5 tool-invisible**: no tool or agent-instruction changes; the same tables get better numbers. Phase 10 later replaces this derivation with the real ad-play join; Phase 11a moves the generator behind the provider seam. Don't bake per-video-per-day assumptions into the generator itself — only into this deliberately disposable derivation layer.
4. Define **one** canonical demo RPI constant in one place (resolving the old open question: pick the donor's effective range, which lands near the more conservative end — flag to the owner if demo realism preferences differ) and delete every other inline revenue/RPI constant on this path.
5. Update all three call sites (`app/database/mock_data.py:383`, `app/tools/review_tools.py:168`, `app/tools/review_tools.py:563`) to use the ported generator + derivation layer.
6. Remove both now-dead `_generate_mock_video_metrics()` implementations entirely — do not leave either in place "for compatibility" (confirm via `grep -rn "_generate_mock_video_metrics" app/ tests/`).

### Forward compatibility (Phases 10, 11a, 15)

- Phase 10 reroutes impressions/revenue through the `AdPlayRecord` join, consuming the generator's visit frames directly — the step-3 derivation layer is what it deletes, so keep that layer thin and isolated.
- Phase 11a moves the generator behind the ported `AudienceProvider` seam as the synthetic provider — keep the generator free of app-global imports so that move is a file relocation, not a refactor.
- Phase 15 (product onboarding) relies on "any key yields data": do not add any precomputed-fixture dependency that would break generation for products/campaigns created after seed time.

## Validation

- [ ] Same `(campaign, screen, date)` key twice → byte-identical frames, including across separate process runs (proves SHA-based seeding survived the port).
- [ ] Different keys → different-but-plausible output (not degenerate/constant); spot-check the realism curves (peaks, weekend lift) survived the port.
- [ ] A demo run that seeds a campaign via `populate_mock_data()` and then activates one of its videos via `activate_video()` shows RPI figures consistent with `compute_rpi()`, with no visible discontinuity between "seeded at DB init" and "generated at activation time" data — both on the step-2 windowing rule.
- [ ] `generate_additional_metrics()` (`review_tools.py:563`) also uses the ported path — a test confirms the third call site wasn't missed.
- [ ] `grep -rn "_generate_mock_video_metrics"` returns zero hits; exactly one RPI constant exists on the demo-data path.
- [ ] `make test-unit` and `make test-e2e` pass; update any test fixture that depended on the old RNG ranges or date-window behavior.

## Exit criteria

One deterministic, BlueZoo-shaped generator (ported from the donor, with its tests), used by every code path that needs mock data, feeding the existing `video_metrics` shape through a thin derivation layer, with RPI computed only via Phase 4's shared `compute_rpi()`.

## Dependencies

Phase 4 (needs `compute_rpi()` to exist). Donor repo readable locally at `/Users/lavi/gwork/ad-campaign-agent` (port at file/function granularity with review — never bulk-copy; the donor lacks this repo's Phase 1/2 fixes).

## Open questions

None remaining. (The old RPI-range question is resolved by step 4's single canonical constant — flagged to the owner only if the resulting demo numbers look off.)
