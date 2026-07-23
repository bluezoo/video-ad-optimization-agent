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

## 2026-07-22 — checkpoint 3: plan approved
plan.md approved by owner ("Yes — approved, execute"). 6 tasks: (1) image
comparison harness+doc, (2) Veo polling consolidation TDD, (3) Interactions
prototype, (4) controller gate NO-GO/GO (GO requires owner-approved Task 4G
amendment), (5) gemini-3.6-flash default flip + Phase 16 provenance,
(6) demo-scenario verification (F1 release gate, F5.2, from-scratch 2.1/2.2).
Pre-flight fix: removed unused sqlite3 import from plan's Task-2 test code.

## 2026-07-22 — Task 1 done: image-model comparison (14a) + Q14 evidence
Live side-by-side run (scripts/compare_image_models.py, Vertex global,
google-genai 2.14.0): gemini-3-pro-image vs gemini-3.1-flash-lite-image,
8/8 OK — the with-reference case activated (sage-satin-camisole.png reachable
in GCS product-images/), so both models were compared with-reference
symmetrically.

Q14 evidence (observed output resolutions — both models, every case, landed
in the 1K pricing tier):
- fashion-scene: 768x1376 (pro) / 768x1376 (lite)
- retail-scene: 768x1376 / 768x1376
- chart-16x9: 1376x768 / 1376x768
- fashion-scene-with-reference: 768x1376 / 768x1376
~1MP portrait for scenes and 1376x768 for 16:9 charts is what today's default
already produces — Stage-1 frames feed Veo (which re-renders at video res) and
charts render legibly at dashboard-preview size, so 1K output is acceptable
for the current in-store-screen/dashboard-preview uses; nothing in the
pipeline consumes >1K today.

Full metrics table, per-case visual grading, pricing link-check
(~$0.134/image pro vs ~$0.034 lite at 1K), and the recommendation — KEEP
gemini-3-pro-image as the shared-knob default (lite's chart output has
duplicate-title/label artifacts; split-knob is the future cost lever) — in
image-model-comparison.md alongside this log. No app code changed.
Harness deviations from plan (recorded in task report): build_scene_image_prompt
takes a typed Product (Phase 8), so the harness converts its row-dicts via
Product.from_row; fashion category corrected "summer"→"top" so the case
exercises the wearable archetype as the plan intends.

## 2026-07-23 — checkpoint 4: Tasks 1-3 complete (mirrors .superpowers/sdd/progress.md)
Task 1 (image comparison): 01e06d5..efdcbd4, review clean. 8/8 live cases
(2 models x 4 cases incl. with-reference via GCS-mode product image).
Reviewer independently opened the PNGs and confirmed the doc's gradings.
Two disclosed adaptations: Product.from_row (typed signature), category
summer->top (real seeded category, keeps wearable archetype).
Task 2 (Veo polling consolidation): efdcbd4..3ef5c13, review clean. Helpers
_wait_for_veo_operation/_extract_video_bytes; 3 call sites converted;
generate_video_ad semantics + local-mode save path preserved byte-for-byte;
8 new tests (first-ever coverage of these paths); 314 unit + 25 e2e green.
Task 3 (Interactions prototype): 3ef5c13..ee63ee4, review clean. Probe ran
live twice (4 videos generated). Headline: previous_interaction_id explicitly
UNSUPPORTED for gemini-omni-flash-preview; interactions.get 500s on
sync-created ids. Findings doc committed; decisive NO-GO input for Task 4.
