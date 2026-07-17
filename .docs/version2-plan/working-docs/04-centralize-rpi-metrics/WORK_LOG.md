# WORK_LOG — Workstream 04: centralize-rpi-metrics

Append-only per-workstream history (see `tracking-workstream-progress`). Newest at the bottom.

## 2026-07-16 — kickoff: worktree created (checkpoint 1)
Worktree .claude/worktrees/version_2_centralize-rpi-metrics on branch version_2_centralize-rpi-metrics, base 925bdbd (version_2 with workstream 03 merged — docs/METRICS.md exists). Phase-doc research pending.

## 2026-07-16 — kickoff: phase doc research done (checkpoint 1 amendment)
All claims re-verified via Explore agent against base 925bdbd: full RPI inventory current (maps_tools set drifted to {558, 584, 962, 1011-1013}); get_campaign_insights' three defects confirmed; summary=None contract unchanged; weekly bug at metrics_tools.py:923. DIVERGENCE: the "Phase 1 weekly-RPI regression test" the Validation section references does not exist (ws02 flagged the bug only) — this workstream writes it. Phase doc amended with provenance for both. Working doc drafted.

## 2026-07-16 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement: shared metrics_shared.py (compute_rpi/compute_weighted_average), full call-site migration, weekly-bug fix, get_campaign_insights repair, optional filters on get_top_performing_ads, no-data contract normalization. Zero-impressions → 0.0; Phase 4 owns generator unification; SQL AVG(dwell) untouched. Success gate: new shared-function + weekly-regression + parity tests, make test green, demo scenario fashion F2 both scenes.

## 2026-07-16 — plan approved (checkpoint 3)
Owner approved the 7-task plan (commit 8241551): T1 metrics_shared.py + tests + glossary note; T2 get_campaign_metrics migration + enriched daily rows + no-data status-error contract; T3 get_top_performing_ads optional filters; T4 get_campaign_insights repair (scoping/trend/day-grouping); T5 mechanical migrations + phase-doc amendment (generator step vacuous); T6 maps_tools + weighted regional dwell; T7 weekly-chart fix + weekly-RPI regression tests. Executing via subagent-driven-development.
