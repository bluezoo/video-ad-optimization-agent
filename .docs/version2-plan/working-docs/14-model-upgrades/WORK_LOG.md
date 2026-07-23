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

## 2026-07-22 — checkpoint 1 amendment: phase-doc research done
4-agent research fan-out (workflow wf_71089b40-7e6) re-verified every claim in
14a/14b/16-step-3 against current code; full evidence in working-doc.md.
Headlines: IMAGE_GENERATION is a shared knob across FOUR call sites/three
agents (phase doc's Stage-1-only framing stale); retail-core PNGs don't exist
on disk (non-fashion comparison starts referenceless); Veo loop 3 has
different timeout semantics (DB-update+return vs raise) and the bytes
extraction is also triplicated; golden prompt files contain no model IDs
(byte-identity safe by construction); MODEL also drives analyze_video().
Live probes this kickoff: gemini-3.6-flash and gemini-3.1-flash-lite-image
both respond on Vertex global; gemini-3.6-flash is GA (2026-07-21 per model
page). Baseline in fresh worktree: 306 unit + 25 e2e green. Working doc
drafted; awaiting owner approval gate.

## 2026-07-22 — checkpoint 2: working doc approved
Owner approved via explicit yes ("Yes — approved, write the plan") to the
six-dimension restatement. Evaluation-first 14a confirmed (no silent image
default switch — any switch is an owner decision on the comparison evidence).
