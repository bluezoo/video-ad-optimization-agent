# Workstream 11a — audience-provider-seam (port) — WORK_LOG

Phase doc: `.docs/version2-plan/11-live-bluezoo-adapter.md` — **11a half only** (steps 2, 4, and the synthetic conformer from step 3). 11b (live conformer) stays blocked on open questions 1/2 and is NOT this workstream.

This directory (`working-docs/11-live-bluezoo-adapter/`) is 11a's record; a future 11b workstream gets its own log (e.g. `11b-*`), not appends here.

## 2026-07-22 — checkpoint 1: kickoff, worktree created

- Worktree `.claude/worktrees/version_2_live-bluezoo-adapter`, branch `version_2_live-bluezoo-adapter`, base `version_2` @ 62bc6b7 (merge-base verified).
- STATUS.md 11a row → `kickoff in progress` (main checkout, commit c53930a).
- Dependencies checked in STATUS.md: Phase 5 (a5a0f17), Phase 6 (2e05f9d), Phase 10 (debd5a4) — all `merged`.
- Owner kickoff directives (verbatim from request): "start the Phase 11a workstream (.docs/version2-plan/11-live-bluezoo-adapter.md — the 11a 'audience-provider-seam (port)' half only; 11b stays blocked on open questions 1/2) … item 1 (_load_attribution_windows empty-list IN () guard) and item 2 (mock_data/review_tools SQL duplication) should be picked up here since this phase reshapes exactly that provider seam. APP_MODE (Phase 6) is the mode knob this phase finally wires to provider selection. ultracode"
- Scope notes: ws10 carried items 3 (closed-window history growth) and 4 (repo-wide lint red) stay deferred — owner directed only items 1+2 into this workstream.
- Research (checkpoint 1 amendment slot): pending.

## 2026-07-22 — checkpoint 1 amendment: kickoff research done

Ultracode workflow `ws11a-kickoff-research` (3 parallel sonnet readers, 500k tokens, all clean). Full structured findings archived in the session workflow journal; essentials:

- **Donor seam verified** (`/Users/lavi/gwork/ad-campaign-agent/services/audience_provider/`, read-only): ABC `provider.py:42`, factory + fail-loud guard `__init__.py:47-183`, `MockInMemoryProvider`, `MockBigQueryProvider`, sqlglot `QueryGuard`, `register_provider_for_tests`. All three phase-doc caveats confirmed at exact lines (0.05 ×3 incl. an SQL literal at `mock_bigquery.py:500`; string-replace `_qualify_tables` at `mock_bigquery.py:219-227`; viz stub at donor `metrics_tools.py:319-363`). Donor interface has **no daily-grain read** (root cause of its viz stub). **No shared contract-test suite exists in the donor** — new infra for us. Donor traps not to copy: fail-loud check falsely couples to `GCS_BUCKET`; default provider is BQ (wrong default for our demo mode); `AUDIENCE_DEMO_SEED` reach-in to campaign_service; BQ provider instantiates the in-memory provider internally for dwell aggregation.
- **This repo:** APP_MODE (config.py:17-37) has zero consumers — premise holds. seed.py import-light + docstring seam promise verbatim. Carried item 1 confirmed (`review_tools.py:117-137`, `IN ()` on empty list, unreachable today) and item 2 confirmed (`mock_data.py:362-366` duplicates the 4-line window load; layering rule exists only as an inline comment). `BlueZooVisitInterval` is decorative — never constructed in production; the join consumes only `frames["screen_visits"]` (verified directly: `attribution.py:159`, dwell is a separate seeded RNG). No ABC/Protocol/provider naming anywhere in app/ — seam is 100% net-new. Daily-grain nuance: only `get_campaign_metrics`/`get_campaign_insights` GROUP BY metric_date; the creatives chart reads per-video all-time; ALL read tools consume the materialized `video_metrics` table, never the generator.
- **Plan docs:** Q1/Q2 still open → 11b exclusion stands; Q11/Q12/Q17 irrelevant to 11a. Phase 6 amendment pins the fail-closed guard contract (clear specific error at the factory for connected-mode-without-adapter). All five ws05 port corrections verified implemented. 11a rated Medium in 00-overview.

## 2026-07-22 — DISCOVERY: Phase 10 never defined an "AudienceDataSource" interface
Assumed (11-live-bluezoo-adapter.md:5): the donor interface gets "renamed/merged with Phase 10's `AudienceDataSource` DTO contract — one interface, not two."
Actual: `AudienceDataSource` appears nowhere in 10-playout-attribution.md — Phase 10 defined DTOs only (`AdPlayRecord`, the `BlueZooVisitInterval` shape); the interface name is coined by doc 11 itself (its step 2, line 37). There was never a second interface to merge; Phase 10 supplied the return-type shape.
Blast radius: doc 11 line 5 framing only — no downstream doc repeats the claim. Amended doc 11 in this branch with provenance; working doc frames it correctly ("one new interface returning Phase 10's DTO").
Related minor: `app/demo_data/constants.py` docstring says the donor duplicated 0.05 in *two* places; donor audit found *three* (third: SQL literal `mock_bigquery.py:500`). One-line docstring fix folded into this workstream.

## 2026-07-22 — checkpoint 2: working doc approved
Owner approved the six-dimension restatement verbatim ("Yes — approved, write the plan"): lean visit-interval seam (AudienceDataSource ABC + SyntheticAudienceDataSource + APP_MODE-keyed factory with fail-closed connected mode), carried items 1+2 via shared app/demo_data/windows.py helper, refactor invariant = byte-identical video_metrics + existing tests unmodified, demo verify = F3 + F4 + connected-mode fail-closed smoke. Working doc: working-doc.md @ 533eb25.

## 2026-07-22 — checkpoint 3: plan approved
Owner approved ("Yes — approved, execute"). Plan: plan.md @ f089a73 — 7 tasks (1 shared window loader/carried items, 2 ABC+battery, 3 synthetic source, 4 APP_MODE factory+fail-closed, 5 golden-pinned join refactor, 6 docs/demo_guide, 7 demo verify). Execution: subagent-driven-development via ultracode workflow (owner's kickoff directive), Tasks 1-6; Task 7 is the verify phase.

## 2026-07-22 — checkpoint 4: Tasks 1-6 complete (mirrors .superpowers/sdd/progress.md)
Ultracode workflow `ws11a-implement`: 12 agents (6 implementer + 6 reviewer), zero fix rounds, zero Minor findings.
- Task 1: 3d68935..49697e7 — app/demo_data/windows.py shared loader (carried items 1+2); review_tools alias + mock_data rewire. 4/4 new tests, test-unit 247 green.
- Task 2: 49697e7..24c88d5 — AudienceDataSource ABC + AudienceDataSourceContract battery.
- Task 3: 24c88d5..3554d6b — SyntheticAudienceDataSource + public campaign_seed_config (alias kept); battery 10/10 incl. equivalence + subset-determinism.
- Task 4: 3554d6b..50fd288 — APP_MODE-keyed factory, fail-closed connected RuntimeError, test seam; factory 6/6.
- Task 5: 50fd288..40c0aba — golden pin (pre-refactor capture) then join routed through the seam; golden PASS post-refactor, test-unit 264/264, test-e2e 25/25, existing tests unmodified.
- Task 6: 40c0aba..a406c15 — seed.py/constants.py docstrings + demo_guide "Part 0b" (APP_MODE journeys incl. connected-mode terminal check).
Reviewer cannotVerify items adjudicated by controller: each covered by a later task's tests or the pre-existing pinned suites — none escalated.

## 2026-07-22 — checkpoint 5: demo-scenario verification PASS
- F3 (fashion.md, campaign metrics/RPI): 2/2 scenes PASS — 30→+3→33 metric days, per-creative RPIs 0.0605/0.0595/0.0589 identical to ws10's run (byte-identical invariant observed end-to-end). Session 45e86eba…; evidence /tmp/ws11a-evidence/f31_*, f32_*.
- F4 (creatives comparison chart): 1/1 PASS — generate_creative_comparison_chart(campaign_id=4), artifact rendered, chart_data byte-consistent with comparison payload, cent-rounding arithmetic verified. Evidence /tmp/ws11a-evidence/f4_*.
- Connected-mode fail-closed smoke: APP_MODE=connected factory call raises the specific RuntimeError (names connected/Phase 11b/APP_MODE=demo). Evidence /tmp/ws11a-evidence/connected_fail_closed.txt; also pinned by tests/unit/test_audience_factory.py.
- Controller sanity pass: make test-unit 264 passed / 1 skipped on the finished branch.
Both verifier scenes ran against this worktree's own make dev on :8501 (fresh reset-db), sequentially. Two non-blocking LLM-prose nits noted by verifiers (a stray text fragment in one answer; one wrong video-id digit in a prose table) — tool payloads clean in both, not defects of this change.

## 2026-07-22 — checkpoint 6 (partial): PR open
Final whole-branch review (opus): "Ready to merge", zero Critical/Important; two non-blocking Minor notes (one addressed in 357a9d7, one documented behavioral note on the synthetic screen_id//100 convention). PR #12 → version_2: https://github.com/bluezoo/video-ad-optimization-agent/pull/12. Awaiting owner confirmation before self-merge per finishing-a-development-branch Path A.
