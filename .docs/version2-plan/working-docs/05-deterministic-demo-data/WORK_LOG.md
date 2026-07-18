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

## 2026-07-17 17:20 — Task 6 complete (mirrors .superpowers/sdd/progress.md)
commits fcf3e4c..a0b934a, review clean (fresh haiku reviewer, Approved). f11e78f: BLUEZOO_MAPPING.md (donor pin b6e3302 recorded; five port corrections documented) + SETUP_INSTRUCTIONS.md numpy note. a0b934a: controller fix for the only 2 branch-introduced lint errors (ruff UP017 in app/database/db.py + tests/unit/test_demo_meta.py, from Task 3's anchor helpers). Lint discrepancy resolved: the other 62 `make lint` errors are byte-identical on base 1008c79 (incl. all 7 in app/tools/review_tools.py) — pre-existing, out of scope for this workstream. Full `make test` green (141 unit / 25 e2e / 5 integration). All 6 plan tasks complete.

## 2026-07-17 19:05 — demo scenario verification: PASS (checkpoint 5)
Fresh `make dev` on :8501 from this worktree, fresh-seeded DB. Full `make test` green first (141 unit / 25 e2e / 5 integration).
- Scenario F2 (workstream 02 chart regression): 2/2 scenes PASS — F2.1 chart success with 30 data points all at RPI 0.05; F2.2 clean no-data guard for a fresh campaign. Evidence: /tmp/ws05-verify/f2/.
- Scenario F3 (new, this workstream): F3.1 PASS (get_video_status → 30 metric days; generate_additional_metrics(days=3) → days_generated 3; re-check → 33 days, RPI still 0.05, revenue 811.80 = 16236 × 0.05 exact); F3.2 PASS (get_top_performing_ads: every row satisfies revenue = impressions × 0.05 exactly, all RPI 0.05). Evidence: /tmp/ws05-verify/f3/.
- Plan-vs-reality note: F3.1 as first drafted assumed the seeded demo DB contains pending videos to activate — false, and pre-existing base behavior (mock_data seeds all 10 videos `activated`, identical at base 1008c79). Scene reworked (commit 64d67b2) to assert the seeded 30-day window + anchor extension instead; HITL activation seeding remains covered by tests/unit/test_review_tools.py::TestDeterministicActivation. Not a code bug; no downstream phase-doc impact.

## 2026-07-17 19:40 — final whole-branch review: Ready to merge
Fresh reviewer, full package 1008c79..68e1442 (22 commits, 19 files, +2751/−301). All focus checks PASS: five port corrections verified in code at exact bin indices; single DEMO_RPI constant; both legacy generators deleted; tool contracts unchanged; determinism proven incl. cross-process; no forbidden touches (README/DEMO_GUIDE untouched, no .env, no AI trailers). Zero Critical/Important; 3 informational Minors (startup DELETE-then-INSERT reseed window; pre-existing weak assertions; 62 pre-existing lint errors) — none blocking. Full report: .superpowers/sdd/final-review.md (scratch) — verdicts mirrored here.

## 2026-07-18 — finish: merged (checkpoint 6)
PR #6 squash-merged into version_2 as a5a0f17 (owner-confirmed). Worktree removed, local + remote workstream branch deleted. STATUS.md row → merged. Workstream 05 closed.
