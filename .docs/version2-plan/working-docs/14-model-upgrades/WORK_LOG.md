# WORK_LOG — Workstream 14 (combined): model upgrades

Combined workstream covering Phase 14a (image model / Nano Banana 2 Lite),
Phase 14b (video model / Omni Flash, experimental), plus the agent-model
default change to `gemini-3.6-flash` pulled forward from Phase 16 step 3
(owner directive, 2026-07-22). One branch (`version_2_model-upgrades`), one
PR; STATUS.md rows 14a and 14b both track it. Structured as three sequential
tasks — 14a → 14b → agent default — each independently verified and committed.

## 2026-07-22 — checkpoint 1: kickoff, worktree created
Worktree .claude/worktrees/version_2_model-upgrades on branch
version_2_model-upgrades, base version_2 @ 38041a3 (includes owner commit
1ec85cb — Phase 16 GCS state-leak item — and both STATUS kickoff rows).
Owner constraints for this ws: golden prompt files stay byte-identical (they
pin code-built prompt text, not model output); amend 16-live-api-testing.md
with provenance to move the model-default item here; record Q14/Q15 evidence
(image resolutions, video-output notes) in this WORK_LOG during verification;
new journeys in root DEMO_GUIDE.md. Phase-doc research: pending.
