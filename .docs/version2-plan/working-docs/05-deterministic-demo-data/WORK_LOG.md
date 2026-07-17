# Workstream 05: deterministic-demo-data — WORK_LOG

Append-only. Newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-17 — kickoff: worktree created; phase doc research done
Branch version_2_deterministic-demo-data off version_2 @ 1008c79 (post-replan; Phase 4 dependency merged as a29f182). Research (3 parallel readers: repo claims, donor generator, port corrections): all phase-doc claims CONFIRMED (±1 line drift on review_tools cites: def :455, calls :169/:564). Donor pinned at b6e3302 (feat/plan3-slice1-bq-mvp tip == HEAD; working tree dirty on mock_bigquery.py + 4 scripts, untouched — all reads via git show). Port corrections distilled from bluezoo-mapping-verification.md. Key findings for the working doc: donor seed.py is numpy+pandas (neither in app/requirements.txt); no screen entity exists in this repo (campaign IS the store binding); zero tests assert the old generators' RNG ranges/date direction; flat revenue=impressions×constant would make RPI identical across creatives (Phase 7 tension — flagged to owner).

## 2026-07-17 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement. Two explicit owner decisions recorded in the working doc: (1) STRICT FLAT RPI CONSTANT — revenue = impressions × DEMO_RPI (0.05), no per-video variance factor; flat-RPI tension consciously deferred to Phase 7 (its phase doc amended with provenance this branch); (2) numpy only — added to requirements; frames as lists of dicts, no pandas. Next: writing-plans.

## 2026-07-17 — plan approved (checkpoint 3)
Owner approved the 6-task plan (commit 3a23dcc), including the two plan-time working-doc corrections (synthetic dwell per METRICS.md; absolute per-video fractions). Executing via subagent-driven-development.

## 2026-07-17 — Task 1 complete (mirrors .superpowers/sdd/progress.md)
commits 4327655..986970c, review clean — app/demo_data/seed.py ported (HHMM bins verified incl. _0058_to_0100 boundary), numpy dep added, 10 tests incl. cross-process determinism. One justified lint deviation (zip strict=True, ruff B905, behavior-neutral).

## 2026-07-17 — Task 2 complete (mirrors .superpowers/sdd/progress.md)
commits bceee4e..ee424f2, review clean — constants.py (DEMO_RPI=0.05, DEMO_WINDOW_DAYS=30) + derive.py (inner-only impressions, absolute per-video fractions, synthetic dwell/circulation), 9 tests. Reviewer verified flat-RPI round-trip and the no-discontinuity property.

## 2026-07-17 — Task 3 complete (mirrors .superpowers/sdd/progress.md)
commits e7679e2..61aec1b, review clean — demo_meta table (init + reset) and get/set_demo_anchor_date helpers in db.py, 3 tests, UTC convention honored. Reviewer's single ⚠️ (fresh_test_db fixture existence) resolved by controller: conftest.py:166-169.

## 2026-07-17 — Task 4 complete (mirrors .superpowers/sdd/progress.md)
commits ff19a91..d533ce9, review clean — populate_mock_data() now derives deterministic metrics on [anchor-29, anchor]; old mock_data generator deleted; import random removed. Plan-vs-reality note: the plan's reseeding test was impossible against populate's original "already exists" early-return; the implementer's minimal two-mode restructure (create-once / regen-metrics-always) was reviewed as genuinely required and backward-compatible (conftest, make dev, reset-db unaffected). Unit 138 passed, e2e 25 passed.

## 2026-07-17 — Task 5 complete (mirrors .superpowers/sdd/progress.md)
commits 789b6c4..0b8a84b, review clean — activate_video fills [anchor-29, anchor]; generate_additional_metrics advances the global anchor and extends every activated video atomically, count scoped to the requested video; second _generate_mock_video_metrics deleted (repo-wide grep now zero hits); response contracts byte-compatible. Unit 141 passed, e2e 25 passed.
