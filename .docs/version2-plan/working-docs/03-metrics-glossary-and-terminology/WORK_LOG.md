# Work Log — Workstream 03: metrics-glossary-and-terminology

Append-only, newest at the bottom. Owned by the `tracking-workstream-progress` skill.

## 2026-07-16 17:24 — kickoff: worktree created
Branch `version_2_metrics-glossary` created off `version_2` (1fb1d77, post-workstream-02 merge), worktree at `.claude/worktrees/version_2_metrics-glossary`. Base verified. STATUS.md row set to "kickoff in progress" in main checkout. Phase doc research: pending.

**Amended 2026-07-16 — phase doc research done.** All claims verified against current code and live BlueZoo docs:
- Both duplicate mock generators exist: mock_data.py:168 and review_tools.py:454 (Phase 5's target, cited here as evidence of drift).
- RPI recomputed inline at (current lines): metrics_tools.py 217, 248, 352, 554, 658 (+ SQL ratio-of-sums at 307 in get_top_performing_ads) and campaign_tools.py:254 (get_campaign, def at 188). Matches the "at least 13 sites" claim's spirit; exact inventory is Phase 4's job.
- video_metrics columns confirmed (db.py:141-152): impressions, dwell_time_seconds (scalar), circulation, revenue.
- BlueZoo docs RE-VERIFIED LIVE (api.bluezoo.io, fetched today): sensor_visits — "measure the number of devices seen within the inner detection range of a sensor, also known as impressions" (exact caption); sensor_dwell — "a distribution of visit durations per 15-minute slots" (bins, not scalar — confirms the phase doc's correction); sensor_visitors — occupancy min/avg/max per 15-minute period. Also noted: BlueZoo Fetch API is deprecated, discontinued 2025-12-31 — Real-time API replaces it (relevant to Phase 11, amended there if not already known).
- README.md metric prose located (lines 9, 31-32, 53, 57 — incl. the client's operational RPI definition at line 9); agent.py:308 carries the RPI formula in the analytics prompt.
- docs/METRICS.md does not exist; nothing references it yet.
- DIVERGENCE: phase doc Step 2 says "link from README.md" — conflicts with the standing README-untouched rule (CLAUDE.md). Resolution to propose: link from SETUP_INSTRUCTIONS.md + CLAUDE.md pointer instead; amend phase doc with provenance on approval.

## 2026-07-16 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement: docs/METRICS.md glossary (five definitions, circulation/dwell marked unresolved, BlueZoo table appendix), links via SETUP_INSTRUCTIONS.md + CLAUDE.md — README stays untouched (divergence resolved in favor of the standing rule; phase doc to be amended with provenance) — zero changes under app/, demo-scenario step explicitly skipped as docs-only. Next: writing-plans.

## 2026-07-16 — plan approved (checkpoint 3)
Owner approved the 2-task plan (commit e7b1ed5): Task 1 creates docs/METRICS.md (full literal content in plan — 5 definitions, live-verified BlueZoo quotes, ratio-of-sums rule, table appendix); Task 2 wires links (SETUP_INSTRUCTIONS.md before '## Test', CLAUDE.md project-overview pointer), amends phase-doc Step 2 with README-divergence provenance, and proves zero behavior change. Executing via subagent-driven-development.

## 2026-07-16 — Task 1 complete (SDD task ledger mirror)
docs/METRICS.md created (commit 69bd304), review clean: exact transcription of the approved glossary content, 6 sections, no code blocks, all cross-referenced phase-doc paths verified to exist.

## 2026-07-16 — Task 2 complete (SDD task ledger mirror)
Links wired (commit fdd38bf): SETUP_INSTRUCTIONS.md "Metrics glossary" section, CLAUDE.md project-overview pointer, phase-doc Step 2 provenance amendment. Review approved after one evidence fix: initial report showed only the integration count; full make test re-run evidenced (unit 88 passed/1 skipped, integration 5 passed, exit 0). Zero diff under app/, README.md and DEMO_GUIDE.md untouched.

## 2026-07-16 — demo-scenario verification: SKIPPED (checkpoint 5)
Per verifying-with-demo-scenarios' skip rule for genuinely non-agent-facing work: this phase is documentation-only (docs/METRICS.md + two doc pointers + phase-doc amendment), zero changes under app/, no tool contract or prompt changes — there is no agent behavior to observe. The full automated suite passing unchanged (see Task 2 entry) is the phase's own validation per the phase doc. Skip pre-declared in the approved working doc and plan.

## 2026-07-16 — final whole-branch review: Ready to merge
Fable reviewer, range 1fb1d77..c54c3d7. Initial verdict "Needs fixes" on one Important finding (docs/METRICS.md cited open questions by the phase doc's local numbers 1/2 instead of 99-open-questions.md's 5/6) plus one accepted Minor (WORK_LOG referenced the git-ignored SDD ledger path). Both fixed in c54c3d7 (cross-references now carry the confirmed numbers + quoted heading titles); re-review confirmed resolved, constraints re-verified, no new issues. Third (Minor, line-number drift between phase doc and working doc) accepted as no-action — expected re-verification against post-ws02 code.

## 2026-07-16 — finish: PR open (checkpoint 6, pending merge)
PR #3 into version_2: https://github.com/bluezoo/video-ad-optimization-agent/pull/3 — awaiting owner confirmation to self-merge per the sequencing model.

## 2026-07-16 — finish: merged (checkpoint 6 complete)
PR #3 squash-merged into version_2 as 2bb2452; worktree and branch (local + origin) removed.
