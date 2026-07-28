# WORK_LOG — 11b live-bluezoo-adapter (conformer)

Phase 11b, doc `11-live-bluezoo-adapter.md`. Branch `version_2_live-bluezoo-adapter-conformer` off `version_2` (23b0dfe).

## 2026-07-27 — checkpoint 1: kickoff — worktree created
Worktree `.claude/worktrees/version_2_live-bluezoo-adapter-conformer`, base verified == version_2. Research pending (this entry amended when Step 2 completes).

Owner directives at kickoff (binding):
- Honour the three pre-kickoff scoping decisions at the foot of 11-*.md — do NOT reopen: (1) REST-first behind the 11a seam (OUR assumption — surface in working doc, get explicit yes); (2) ONE class implementing ONE method, no registry/plugin framework/second abstraction — growing layers = stop and re-scope; (3) CachedBlueZooAudienceDataSource OPTIONAL, designated trim — if dropped, say so and amend Exit criteria.
- Rule R (WHERE valid, exclusion logged) is a recommendation NOT confirmed by BlueZoo — explicit, logged, CONFIGURABLE policy, never baked in.
- Read-only against BlueZoo, no writes ever. MO_92 = real customer data: redact identifiers, never commit a key, sweep branch pre-PR.
- This workstream CHANGES agent-visible behavior — demo-scenario verification + DEMO_GUIDE.md journeys are MANDATORY before PR (unlike the two research predecessors; do not cite their skip precedent).
- make test stays network-free (350 tests / ~32s protected); live conformer tests go in the live tier (make test-live) so test runs never bill customer quota.
- Credentials already in app/.env (Morpheus/MO_92).
