# Workstream 06 — app-mode-config-skeleton — WORK_LOG

Append-only, newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-18 — kickoff: worktree created (checkpoint 1)
Worktree .claude/worktrees/version_2_app-mode-config, branch version_2_app-mode-config off version_2 @ 49d015c (post-ws05 merge). Phase doc: .docs/version2-plan/06-app-mode-config-skeleton.md (rated Small; no dependencies). Research done (3 parallel agents: config/runtime, deploy, docs/tests): all phase-doc claims verified; drift found — test_config.py already exists (reload pattern ready), deploy step 6 misses the primary deploy_ae_inline.py path (env_vars dict :304-308), invalid value must raise ValueError (deploy_ae_inline catches ImportError), AppMode as str-Enum per house style, SETUP_INSTRUCTIONS.md :97 reserves the APP_MODE note. Working doc drafted.

## 2026-07-18 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement. Owner decisions at the gate: (1) deploy wiring covers BOTH explicit paths — scripts/deploy.sh AND scripts/deploy_ae_inline.py env_vars dict (deploy_ae.sh needs nothing, reads app/.env); agent_engine_app.py force-set deferred to Phase 11/12. (2) Demo-scenario run skipped per verifying-with-demo-scenarios' non-agent-facing allowance — replaced by the 4-case startup smoke matrix + full make test; skip to be logged at verification. Next: writing-plans.

## 2026-07-18 — plan approved (checkpoint 3)
Owner approved plan.md (cfa4d37): 3 tasks — (1) AppMode enum + validated APP_MODE + 7 tests + smoke matrix; (2) forward APP_MODE in deploy.sh and deploy_ae_inline.py, dry-run/AST verification; (3) docs in CLAUDE.md/SETUP_INSTRUCTIONS.md/DEPLOYMENT.md + full make test. Execution via subagent-driven-development, no check-ins until verification.
