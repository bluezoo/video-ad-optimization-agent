# Version 2 Workstream Status

Cross-workstream index, owned by the `tracking-workstream-progress` skill. **Read this before starting or resuming any phase** — it's the source of truth for what's actually done, not what a phase doc's own narrative claims.

Update rows in place as a workstream progresses; don't append new rows for the same phase. See `tracking-workstream-progress`'s `SKILL.md` for the full checkpoint list and the companion per-workstream `working-docs/<NN>-<name>/WORK_LOG.md`.

**Status values:** `not started` · `kickoff in progress` · `plan in progress` · `implement in progress` · `verify in progress` · `PR open` · `merged` · `discarded`

**Numbering (read once, saves confusion):** phase numbers are 0-based; doc filename prefixes are 1-based, because `00-overview.md` is the overview, not a phase. So they're offset by one — Phase 0's doc is `01-*.md`, Phase 6's is `07-*.md`. This is deliberate and *not* being renumbered (every "depends on Phase N" cross-reference in the plan uses phase numbers). The **Doc** column below is the authoritative mapping; workstream folders under `working-docs/` and worktree/branch names key off the doc prefix, never the phase number.

| Phase | Doc | Name | Status | Branch | PR | Last updated | Note |
|---|---|---|---|---|---|---|---|
| 0 | `01` | emergency-model-currency-fix | merged | version_2_model-currency-fix | [#1](https://github.com/bluezoo/video-ad-optimization-agent/pull/1) | 2026-07-14 | merged 9f12738; incl. conftest fix + preview-model probe |
| 1 | `02` | bug-fixes-and-cleanup | merged | version_2_bug-fixes-and-cleanup | [#2](https://github.com/bluezoo/video-ad-optimization-agent/pull/2) | 2026-07-16 | merged e0a0a52; incl. DB-isolation fix + test de-vacuation discoveries |
| 2 | `03` | metrics-glossary-and-terminology | merged | version_2_metrics-glossary | [#3](https://github.com/bluezoo/video-ad-optimization-agent/pull/3) | 2026-07-16 | merged 2bb2452; docs/METRICS.md is the metrics source of truth; demo skipped by design (docs-only) |
| 3 | `04` | centralize-rpi-metrics | verify in progress | version_2_centralize-rpi-metrics | - | 2026-07-16 | all 7 tasks complete; make test green; demo F2 running |
| 4 | `05` | deterministic-demo-data | not started | - | - | 2026-07-13 | depends on Phase 3 |
| 5 | `06` | app-mode-config-skeleton | not started | - | - | 2026-07-13 | - |
| 6 | `07` | rpi-across-creatives-chart | not started | - | - | 2026-07-13 | depends on Phases 3, 4 |
| 7 | `08` | product-schema-generalization | not started | - | - | 2026-07-13 | depends on Phase 1 |
| 8 | `09` | prompt-and-agent-generalization | not started | - | - | 2026-07-13 | depends on Phase 7 |
| 9 | `10` | playout-attribution | not started | - | - | 2026-07-13 | depends on Phases 3, 4, 7 |
| 10 | `11` | live-bluezoo-adapter | not started | - | - | 2026-07-13 | depends on Phases 5, 9; blocked on open questions 1, 2 |
| 11 | `12` | live-pos-adapter | not started | - | - | 2026-07-13 | depends on Phases 3, 5, 10; blocked on open questions 3, 4 |
| 12 | `13` | production-hardening-live-mode | not started | - | - | 2026-07-13 | depends on Phases 10, 11 |
| 13a | `14a` | image-model-upgrade-nano-banana | not started | - | - | 2026-07-13 | depends on Phase 0 only |
| 13b | `14b` | video-model-upgrade-omni-flash | not started | - | - | 2026-07-13 | depends on Phase 0, ideally after 13a |
