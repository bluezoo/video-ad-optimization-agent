# Workstream 07 — rpi-across-creatives-chart — WORK_LOG

Append-only, newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-19 — kickoff: worktree created (checkpoint 1)
Worktree .claude/worktrees/version_2_rpi-chart, branch version_2_rpi-chart off version_2 @ 49ae21b (post-ws06 merge). Phase doc: .docs/version2-plan/07-rpi-across-creatives-chart.md (deps 4+5, both merged). Known headline issue from the ws05 amendment: demo RPI is a strict flat 0.05 for every creative, so an RPI-across-creatives chart over unmodified Phase 5 data is a flat line — resolution options go to the owner at the working-doc gate. Research done (3 parallel agents): all phase-doc claims verified (line numbers drifted, claims hold); reuse target found (get_campaign_insights per-video query); anchor-vs-now days-filter hazard identified (new tool defaults all-time); artifact contract documented (ToolContext save_artifact pattern); flat-RPI options A/B/C developed with full blast radii. DISCOVERY: ws05 never added numpy to scripts/deploy_ae_inline.py requirements (AE deploy would crash importing mock_data->demo_data->seed.py) — to be fixed in this workstream alongside matplotlib. Working doc drafted; flat-RPI decision pending at the gate.

## 2026-07-19 — DISCOVERY: numpy missing from Agent Engine deploy requirements (ws05 gap)
Assumed (ws05, SETUP_INSTRUCTIONS numpy note): numpy dependency fully wired. Actual: scripts/deploy_ae_inline.py:291-298 requirements list lacks numpy, while the AE runtime imports it at startup (mock_data.py:28 → demo_data/derive.py → seed.py:27 `import numpy as np`; CLAUDE.md: AE DB repopulates from mock data on restart) — an AE deploy from current version_2 would crash at import. Blast radius: scripts/deploy_ae_inline.py only (app/requirements.txt is correct; deploy_ae.sh path installs from requirements.txt and is fine). Fix lands in this workstream's dependency task (numpy + matplotlib added to that list together).

## 2026-07-19 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement. Owner decision at the gate (the ws05-deferred flat-RPI tension): **Option A — deterministic per-creative RPI factor**, constant across days, seeded per (campaign, video), band [0.03, 0.07] around DEMO_RPI; reverses the ws05 strict-flat choice by explicit owner sign-off. Options B (flat + multi-metric) and C (daily jitter) rejected — reasoning recorded in working-doc.md. numpy-AE DISCOVERY fix folded into the dependency task. Next: writing-plans.

## 2026-07-19 — checkpoint 3: plan approved
Plan committed f27e3c7 (4 tasks: Option A data change; compare_creatives_within_campaign; matplotlib chart tool + deps incl. numpy-AE fix; agent wiring + scenario updates + provenance). Owner approved execution via SDD without check-ins until verification.

## 2026-07-19 — Task 1 complete (mirrors .superpowers/sdd/progress.md)
Option A per-creative RPI factor: commits 5700aad + fix 70bcb48 (range c8d0652..70bcb48), review approved. Controller caught a reviewer-missed deviation — implementer had deleted the DEMO_RPI==0.05 canonical assertion from TestConstants; restored in 70bcb48. Unit suite 151 passed.

## 2026-07-19 — Task 2 complete (mirrors .superpowers/sdd/progress.md)
compare_creatives_within_campaign tool: commit 4ad6f6f (range 671dc3d..4ad6f6f), review approved. 5 new unit tests; 156 unit tests green. Minor notes deferred to final review: dwell 1dp rounding (plan-mandated), docstring phrasing.

## 2026-07-19 — Task 3 complete (mirrors .superpowers/sdd/progress.md)
generate_creative_comparison_chart (matplotlib Figure+Agg, artifact contract) + matplotlib in app/requirements.txt + matplotlib AND numpy (ws05 DISCOVERY fix) in deploy_ae_inline.py: commit b07366d (range ccf4dbd..b07366d), review approved. 3 new async tests (first ToolContext AsyncMock in suite); 159 unit tests green.

## 2026-07-19 — Task 4 complete (mirrors .superpowers/sdd/progress.md)
Agent wiring + F3.2 criteria reshape + new Scenario F4 + phase-doc resolution note: commit ea97b50 (range 36fdc6f..ea97b50), review approved. Full make test green (159 unit + 5 integration). All 4 plan tasks done.

## 2026-07-19 — checkpoint 5: demo scenario verification PASS
F3 (updated criteria): 2/2 scenes PASS — F3.1 metric-day counts 30→+3→33; F3.2 per-ad ratios equal own reported RPI (0.0605/0.0595/0.0589), in band, distinct. Report: .superpowers/sdd/f3-verification.md.
F4 (new): PASS — generate_creative_comparison_chart fired (campaign 4), artifact_saved true, 1280x720 PNG rendered, winner=max RPI (asian-cafe-sophisticated 0.0546; RPI rank differs from impressions rank — real comparison confirmed), chart_data==comparison payload exactly. Verified via /run event list + fetched artifact bytes (accepted api-server evidence path). Report: .superpowers/sdd/f4-verification.md. Non-failing deviation: one extraneous get_campaign_map_data call before the chart tool.

## 2026-07-19 — final whole-branch review: READY TO MERGE
Range 49ae21b..c825dbd (15 commits). Zero Critical/Important findings. All deferred per-task Minors triaged acceptable (reviewer empirically tested the $-in-title mathtext hazard — non-issue). Reviewer's STATUS.md note was against the worktree's stale copy; main-checkout row is current. Review: .superpowers/sdd/final-review.md.

## 2026-07-19 — checkpoint 6: finished — merged
PR #8 squash-merged into version_2 as 60ac50f. Worktree removed, branch deleted (local + remote). STATUS row → merged.
