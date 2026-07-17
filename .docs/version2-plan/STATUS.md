# Version 2 Workstream Status

Cross-workstream index, owned by the `tracking-workstream-progress` skill. **Read this before starting or resuming any phase** — it's the source of truth for what's actually done, not what a phase doc's own narrative claims.

Update rows in place as a workstream progresses; don't append new rows for the same phase. See `tracking-workstream-progress`'s `SKILL.md` for the full checkpoint list and the companion per-workstream `working-docs/<NN>-<name>/WORK_LOG.md`.

**Status values:** `not started` · `kickoff in progress` · `plan in progress` · `implement in progress` · `verify in progress` · `PR open` · `merged` · `discarded`

**Numbering:** phase number = doc filename prefix (Phase 7 ↔ `07-rpi-across-creatives-chart.md`). Phases start at 1; `00-overview.md` is the overview, not a phase. Renumbered 2026-07-16 (workstream replan-data-track) from the old 0-based scheme, so anything written before then — merged PR #1–#4 titles/discussions, old commit messages — may use old phase numbers, which are one less than today's. The **Doc** column stays as the explicit mapping; workstream folders under `working-docs/` and worktree/branch names use the doc prefix, which now equals the phase number.

| Phase | Doc | Name | Status | Branch | PR | Last updated | Note |
|---|---|---|---|---|---|---|---|
| 1 | `01` | emergency-model-currency-fix | merged | version_2_model-currency-fix | [#1](https://github.com/bluezoo/video-ad-optimization-agent/pull/1) | 2026-07-14 | merged 9f12738; incl. conftest fix + preview-model probe |
| 2 | `02` | bug-fixes-and-cleanup | merged | version_2_bug-fixes-and-cleanup | [#2](https://github.com/bluezoo/video-ad-optimization-agent/pull/2) | 2026-07-16 | merged e0a0a52; incl. DB-isolation fix + test de-vacuation discoveries |
| 3 | `03` | metrics-glossary-and-terminology | merged | version_2_metrics-glossary | [#3](https://github.com/bluezoo/video-ad-optimization-agent/pull/3) | 2026-07-16 | merged 2bb2452; docs/METRICS.md is the metrics source of truth; demo skipped by design (docs-only) |
| 4 | `04` | centralize-rpi-metrics | merged | version_2_centralize-rpi-metrics | #4 | 2026-07-16 | squash commit a29f182; demo F2 PASS; final review clean |
| 5 | `05` | deterministic-demo-data | not started | - | - | 2026-07-13 | depends on Phase 4 |
| 6 | `06` | app-mode-config-skeleton | not started | - | - | 2026-07-13 | - |
| 7 | `07` | rpi-across-creatives-chart | not started | - | - | 2026-07-13 | depends on Phases 4, 5 |
| 8 | `08` | product-schema-generalization | not started | - | - | 2026-07-13 | depends on Phase 2 |
| 9 | `09` | prompt-and-agent-generalization | not started | - | - | 2026-07-13 | depends on Phase 8 |
| 10 | `10` | playout-attribution | not started | - | - | 2026-07-13 | depends on Phases 4, 5, 8 |
| 11 | `11` | live-bluezoo-adapter | not started | - | - | 2026-07-13 | depends on Phases 6, 10; blocked on open questions 1, 2 |
| 12 | `12` | live-pos-adapter | not started | - | - | 2026-07-13 | depends on Phases 4, 6, 11; blocked on open questions 3, 4 |
| 13 | `13` | production-hardening-live-mode | not started | - | - | 2026-07-13 | depends on Phases 11, 12 |
| 14a | `14a` | image-model-upgrade-nano-banana | not started | - | - | 2026-07-13 | depends on Phase 1 only |
| 14b | `14b` | video-model-upgrade-omni-flash | not started | - | - | 2026-07-13 | depends on Phase 1, ideally after 14a |
| — | `—` | replan-data-track (docs only) | PR open | version_2_replan-data-track | [#5](https://github.com/bluezoo/video-ad-optimization-agent/pull/5) | 2026-07-16 | amends Phases 5/6/8/10/11, splits 11 into 11a/11b, adds Phase 15 (`15-product-onboarding.md`); scope grew at owner request: 1-based phase renumbering (phase = doc prefix) + donor mimic verified against live BlueZoo published docs (see working-docs/replan-data-track/bluezoo-mapping-verification.md); on merge: split Phase 11 row into 11a/11b + add Phase 15 row |
