# Workstream 10 — playout-attribution: WORK_LOG

Append-only durable history (see tracking-workstream-progress).

## 2026-07-22 — checkpoint 1: kickoff — worktree created
Branch version_2_playout-attribution off version_2 @ 759d0c8 (post-ws09 merge 20d7347).
Phase doc: .docs/version2-plan/10-playout-attribution.md. Dependencies 4/5/8 all merged
per STATUS. Owner kickoff notes to verify in research: (a) doc's "Current state" predates
ws05 — real current state is app/demo_data/derive.py, whose header declares this phase
replaces it with the ad-play join; seed.py untouched; (b) ws07 per-creative RPI factor in
derive.py powers demo scenario F4 — the join-derived world must preserve per-creative RPI
differentiation; (c) honor replan amendments: ad_campaign_id (never bare campaign_id),
BlueZooVisitInterval scoped to sensor_visits fields only, no sub-15-min live-window
assumptions; (d) demo_guide.md refresh required before PR (metric values change).
(Research findings appended when kickoff research completes.)
