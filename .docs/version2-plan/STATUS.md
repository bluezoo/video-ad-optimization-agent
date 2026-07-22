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
| 4 | `04` | centralize-rpi-metrics | merged | version_2_centralize-rpi-metrics | [#4](https://github.com/bluezoo/video-ad-optimization-agent/pull/4) | 2026-07-16 | squash commit a29f182; demo F2 PASS; final review clean |
| 5 | `05` | deterministic-demo-data | merged | version_2_deterministic-demo-data | [#6](https://github.com/bluezoo/video-ad-optimization-agent/pull/6) | 2026-07-18 | squash-merged as a5a0f17; F2+F3 demo scenarios PASS; final review clean |
| 6 | `06` | app-mode-config-skeleton | merged | version_2_app-mode-config | [#7](https://github.com/bluezoo/video-ad-optimization-agent/pull/7) | 2026-07-19 | squash-merged as 2e05f9d; smoke-matrix verification (demo scenario skipped by design — no agent-facing change); final review zero findings |
| 7 | `07` | rpi-across-creatives-chart | merged | version_2_rpi-chart | [#8](https://github.com/bluezoo/video-ad-optimization-agent/pull/8) | 2026-07-19 | squash-merged as 60ac50f; F3 (updated criteria) + new F4 PASS; final review clean; incl. numpy-AE deploy fix |
| 8 | `08` | product-schema-generalization | merged | version_2_product-schema | [#9](https://github.com/bluezoo/video-ad-optimization-agent/pull/9) | 2026-07-21 | squash-merged as 5d3e1f8; F1.1/F2.1 regression + new F5 PASS; final review clean; owner manual test (user-journey guide) passed — 2 findings routed to Phases 9/15 via DISCOVERY amendments |
| 9 | `09` | prompt-and-agent-generalization | merged | version_2_prompt-generalization | [#10](https://github.com/bluezoo/video-ad-optimization-agent/pull/10) | 2026-07-22 | merged 20d7347 (squash); archetype registry + ad style policy; demo verify PASS (F1 2/2, F5 2/2); spawned Phase 16 (Q19 resolved), amended Phase 15 |
| 10 | `10` | playout-attribution | merged | version_2_playout-attribution | [#11](https://github.com/bluezoo/video-ad-optimization-agent/pull/11) | 2026-07-22 | squash debd5a4; owner manual test round all-pass; carried minors noted in 11-*.md |
| 11a | `11` | audience-provider-seam (port) | implement in progress | version_2_live-bluezoo-adapter | - | 2026-07-22 | working doc approved (lean visit-interval seam + APP_MODE factory, fail-closed connected); carried items 1+2 in scope |
| 11b | `11` | live-bluezoo-adapter (conformer) | not started | - | - | 2026-07-16 | depends on 11a; blocked on open questions 1, 2 (mimic already validated against published docs — see Q2/Q18) |
| 12 | `12` | live-pos-adapter | not started | - | - | 2026-07-13 | depends on Phases 4, 6, 11; blocked on open questions 3, 4 |
| 13 | `13` | production-hardening-live-mode | not started | - | - | 2026-07-13 | depends on Phases 11, 12 |
| 14a | `14a` | image-model-upgrade-nano-banana | not started | - | - | 2026-07-13 | depends on Phase 1 only |
| 14b | `14b` | video-model-upgrade-omni-flash | not started | - | - | 2026-07-13 | depends on Phase 1, ideally after 14a |
| 15 | `15` | product-onboarding | not started | - | - | 2026-07-16 | depends on Phases 8, 9, 11a |
| — | `—` | replan-data-track (docs only) | merged | version_2_replan-data-track | [#5](https://github.com/bluezoo/video-ad-optimization-agent/pull/5) | 2026-07-17 | merged a4e0e76 (squash); replan + 1-based renumbering + BlueZoo mimic verification (working-docs/replan-data-track/bluezoo-mapping-verification.md); 11a/11b + Phase 15 rows added above |
| 16 | `16` | live-api-testing | not started | - | - | 2026-07-22 | new phase (owner directive, resolves Q19); dependency: Phase 9 merged |
