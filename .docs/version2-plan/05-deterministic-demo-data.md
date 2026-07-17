# Phase 4 — Deterministic Demo Data (port the donor generator)

> **Amended (workstream replan-data-track, 2026-07-16):** rewritten from "hand-build a deterministic generator" to "port the proven generator from the donor repo." The owner's personal repo `/Users/lavi/gwork/ad-campaign-agent` (this repo's upstream ancestor — see `99-open-questions.md` Q1) contains a working, tested, deterministic, **BlueZoo-shaped** metrics generator (`services/audience_provider/seed.py`) that supersedes the design this phase originally planned to invent. Porting it also serves the owner's stated prime motive: closest possible alignment with BlueZoo's data schema and metrics. Original current-state analysis below remains valid and is kept.

## Goal

Replace the two independently-drifted random-metric generators (called from three separate places) with **one deterministic, BlueZoo-shaped generator ported from the donor repo**, so demo numbers are reproducible, internally consistent, and already shaped like the data BlueZoo's real sensors will eventually supply.

## Current state (confirmed live bug — corrected to three call sites, not two)

Two separate functions named `_generate_mock_video_metrics()` exist and disagree, and there are **three** call sites across them, not two:

- `app/database/mock_data.py:168-235` — impressions range 800-2000, `revenue_per_impression = random.uniform(0.02, 0.08) * multiplier`. Called from `populate_mock_data()` at line 383. **Its date window runs backward from today** (`mock_data.py:188`) — i.e., "the last N days."
- `app/tools/review_tools.py:454-513` — a **completely separate implementation**, impressions range 800-1500, RPI range $0.08-$0.15. Called from two places: `activate_video()` at `review_tools.py:168`, **and** `generate_additional_metrics()` at `review_tools.py:563` (this second call site was missed in the first draft of this phase). **Its date window runs forward from a supplied start date** (`review_tools.py:484`) — the opposite direction from the seed-time generator.

Result: two videos activated in the same demo session, seeded from the same "mock data," can show RPI figures that differ by nearly 2x purely because of which function happened to generate them — a visible inconsistency in a live demo, and a correctness problem for the RPI-across-creatives comparison the client specifically asked about (Phase 6 depends on this being fixed first). **A single shared seed alone does not fix this** — the two generators don't just disagree on RNG ranges, they disagree on which direction time runs, so unifying them requires one anchor-date-and-direction model, not just one RNG.

## The donor generator (what gets ported)

`ad-campaign-agent`'s `services/audience_provider/seed.py` (~200 lines + tests):

- **Deterministic by construction:** SHA-seeded `random.Random` per `(campaign_id, store_id, date)` — byte-identical reruns across processes, no `PYTHONHASHSEED` dependence. This is exactly the stable-hash requirement this phase's first draft specified by hand.
- **BlueZoo-shaped output:** 15-minute sensor grain (48 slots, 09:00–21:00), visit counts (inner/outer, incoming/outgoing), dwell-time *distributions* (106 histogram bins, matching BlueZoo's `sensor_dwell` shape), unique-visitor frequency buckets, flow transitions.
- **Demo realism baked in:** lunch/after-school peaks, weekend multipliers, per-campaign uplift factors — numbers that look credible in front of a prospect without hand-tuning.
- **Data ships as code**, not fixtures: any `(campaign, store/screen, date)` key yields deterministic data on demand — which is what lets a freshly onboarded product (Phase 14) get plausible metrics with zero fixture authoring.

## Steps

1. Port `seed.py` from the donor into this repo (e.g. `app/demo_data/seed.py` for now — the provider-seam home arrives in Phase 10a; keep the module import-light so relocating it later is mechanical). Port its unit tests alongside. Adapt naming to this repo's vocabulary (`screen` where the donor says `store`, per Phase 9's `Screen` concept) and key generation off this app's IDs.
2. **Reconcile date-window semantics** (unchanged requirement from the first draft): one fixed demo anchor date (set when the demo DB is seeded) and one explicit windowing rule, applied identically at seed time and at activation time. Both existing call-path behaviors (backward-from-today and forward-from-start-date) are replaced by this one rule.
3. Add a thin derivation layer that aggregates the generator's BlueZoo-shaped 15-minute visit frames into the per-video daily rows the current `video_metrics` table and tools consume (`impressions` = sum of inner visit counts over the video's active windows for that day; `revenue` = impressions × the canonical RPI constant; stored RPI via `compute_rpi()` from Phase 3, never an inline multiplication). **This keeps Phase 4 tool-invisible**: no tool or agent-instruction changes; the same tables get better numbers. Phase 9 later replaces this derivation with the real ad-play join; Phase 10a moves the generator behind the provider seam. Don't bake per-video-per-day assumptions into the generator itself — only into this deliberately disposable derivation layer.
4. Define **one** canonical demo RPI constant in one place (resolving the old open question: pick the donor's effective range, which lands near the more conservative end — flag to the owner if demo realism preferences differ) and delete every other inline revenue/RPI constant on this path.
5. Update all three call sites (`app/database/mock_data.py:383`, `app/tools/review_tools.py:168`, `app/tools/review_tools.py:563`) to use the ported generator + derivation layer.
6. Remove both now-dead `_generate_mock_video_metrics()` implementations entirely — do not leave either in place "for compatibility" (confirm via `grep -rn "_generate_mock_video_metrics" app/ tests/`).

### Forward compatibility (Phases 9, 10a, 14)

- Phase 9 reroutes impressions/revenue through the `AdPlayRecord` join, consuming the generator's visit frames directly — the step-3 derivation layer is what it deletes, so keep that layer thin and isolated.
- Phase 10a moves the generator behind the ported `AudienceProvider` seam as the synthetic provider — keep the generator free of app-global imports so that move is a file relocation, not a refactor.
- Phase 14 (product onboarding) relies on "any key yields data": do not add any precomputed-fixture dependency that would break generation for products/campaigns created after seed time.

## Validation

- [ ] Same `(campaign, screen, date)` key twice → byte-identical frames, including across separate process runs (proves SHA-based seeding survived the port).
- [ ] Different keys → different-but-plausible output (not degenerate/constant); spot-check the realism curves (peaks, weekend lift) survived the port.
- [ ] A demo run that seeds a campaign via `populate_mock_data()` and then activates one of its videos via `activate_video()` shows RPI figures consistent with `compute_rpi()`, with no visible discontinuity between "seeded at DB init" and "generated at activation time" data — both on the step-2 windowing rule.
- [ ] `generate_additional_metrics()` (`review_tools.py:563`) also uses the ported path — a test confirms the third call site wasn't missed.
- [ ] `grep -rn "_generate_mock_video_metrics"` returns zero hits; exactly one RPI constant exists on the demo-data path.
- [ ] `make test-unit` and `make test-e2e` pass; update any test fixture that depended on the old RNG ranges or date-window behavior.

## Exit criteria

One deterministic, BlueZoo-shaped generator (ported from the donor, with its tests), used by every code path that needs mock data, feeding the existing `video_metrics` shape through a thin derivation layer, with RPI computed only via Phase 3's shared `compute_rpi()`.

## Dependencies

Phase 3 (needs `compute_rpi()` to exist). Donor repo readable locally at `/Users/lavi/gwork/ad-campaign-agent` (port at file/function granularity with review — never bulk-copy; the donor lacks this repo's Phase 0/1 fixes).

## Open questions

None remaining. (The old RPI-range question is resolved by step 4's single canonical constant — flagged to the owner only if the resulting demo numbers look off.)
