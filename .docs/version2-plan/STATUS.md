# Version 2 Workstream Status

Cross-workstream index, owned by the `tracking-workstream-progress` skill. **Read this before starting or resuming any phase** — it's the source of truth for what's actually done, not what a phase doc's own narrative claims.

Update rows in place as a workstream progresses; don't append new rows for the same phase. See `tracking-workstream-progress`'s `SKILL.md` for the full checkpoint list and the companion per-workstream `working-docs/<NN>-<name>/WORK_LOG.md`.

**Status values:** `not started` · `kickoff in progress` · `plan in progress` · `implement in progress` · `verify in progress` · `PR open` · `merged` · `discarded`

| Phase | Name | Status | Branch | PR | Last updated | Note |
|---|---|---|---|---|---|---|
| 0 | emergency-model-currency-fix | implement in progress | version_2_model-currency-fix | - | 2026-07-14 | plan approved; VIDEO_GEN_MODEL rename amendment |
| 1 | bug-fixes-and-cleanup | not started | - | - | 2026-07-13 | - |
| 2 | metrics-glossary-and-terminology | not started | - | - | 2026-07-13 | - |
| 3 | centralize-rpi-metrics | not started | - | - | 2026-07-13 | depends on Phase 2 |
| 4 | deterministic-demo-data | not started | - | - | 2026-07-13 | depends on Phase 3 |
| 5 | app-mode-config-skeleton | not started | - | - | 2026-07-13 | - |
| 6 | rpi-across-creatives-chart | not started | - | - | 2026-07-13 | depends on Phases 3, 4 |
| 7 | product-schema-generalization | not started | - | - | 2026-07-13 | depends on Phase 1 |
| 8 | prompt-and-agent-generalization | not started | - | - | 2026-07-13 | depends on Phase 7 |
| 9 | playout-attribution | not started | - | - | 2026-07-13 | depends on Phases 3, 4, 7 |
| 10 | live-bluezoo-adapter | not started | - | - | 2026-07-13 | depends on Phases 5, 9; blocked on open questions 1, 2 |
| 11 | live-pos-adapter | not started | - | - | 2026-07-13 | depends on Phases 3, 5, 10; blocked on open questions 3, 4 |
| 12 | production-hardening-live-mode | not started | - | - | 2026-07-13 | depends on Phases 10, 11 |
| 13a | image-model-upgrade-nano-banana | not started | - | - | 2026-07-13 | depends on Phase 0 only |
| 13b | video-model-upgrade-omni-flash | not started | - | - | 2026-07-13 | depends on Phase 0, ideally after 13a |
