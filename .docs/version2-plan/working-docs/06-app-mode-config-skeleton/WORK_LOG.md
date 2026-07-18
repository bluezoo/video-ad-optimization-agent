# Workstream 06 — app-mode-config-skeleton — WORK_LOG

Append-only, newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-18 — kickoff: worktree created (checkpoint 1)
Worktree .claude/worktrees/version_2_app-mode-config, branch version_2_app-mode-config off version_2 @ 49d015c (post-ws05 merge). Phase doc: .docs/version2-plan/06-app-mode-config-skeleton.md (rated Small; no dependencies). Research done (3 parallel agents: config/runtime, deploy, docs/tests): all phase-doc claims verified; drift found — test_config.py already exists (reload pattern ready), deploy step 6 misses the primary deploy_ae_inline.py path (env_vars dict :304-308), invalid value must raise ValueError (deploy_ae_inline catches ImportError), AppMode as str-Enum per house style, SETUP_INSTRUCTIONS.md :97 reserves the APP_MODE note. Working doc drafted.

## 2026-07-18 — working doc approved (checkpoint 2)
Owner approved the six-dimension restatement. Owner decisions at the gate: (1) deploy wiring covers BOTH explicit paths — scripts/deploy.sh AND scripts/deploy_ae_inline.py env_vars dict (deploy_ae.sh needs nothing, reads app/.env); agent_engine_app.py force-set deferred to Phase 11/12. (2) Demo-scenario run skipped per verifying-with-demo-scenarios' non-agent-facing allowance — replaced by the 4-case startup smoke matrix + full make test; skip to be logged at verification. Next: writing-plans.

## 2026-07-18 — plan approved (checkpoint 3)
Owner approved plan.md (cfa4d37): 3 tasks — (1) AppMode enum + validated APP_MODE + 7 tests + smoke matrix; (2) forward APP_MODE in deploy.sh and deploy_ae_inline.py, dry-run/AST verification; (3) docs in CLAUDE.md/SETUP_INSTRUCTIONS.md/DEPLOYMENT.md + full make test. Execution via subagent-driven-development, no check-ins until verification.

## 2026-07-18 — Task 1 complete (mirrors .superpowers/sdd/progress.md)
commits 9e7bb0c..ffe2873, review clean (Approved, 12/12 spec items). AppMode + validated APP_MODE in app/config.py; 7 new tests (148 unit total green); lint clean; 4-case smoke matrix correct. Deviation adjudicated: implementer used StrEnum instead of the brief's (str, Enum) — accepted, ruff.toml targets py311 so StrEnum is the lint-preferred form; ≤3.10 ImportError concern moot.

## 2026-07-18 — Task 2 complete (mirrors .superpowers/sdd/progress.md)
commits 7a1a477..50f61ba, review clean (Approved, exact match to brief). APP_MODE forwarded in scripts/deploy.sh (--set-env-vars, default demo) and scripts/deploy_ae_inline.py (env_vars dict); deploy_ae.sh untouched by design. Implementer's dry-run gap closed by controller: actual generated gcloud command shows --set-env-vars=APP_MODE=demo (and =connected when set).

## 2026-07-18 — Task 3 complete (mirrors .superpowers/sdd/progress.md)
commits ef6337c..741ab17, review clean (Approved; every documented claim cross-checked against code). APP_MODE documented in CLAUDE.md Environment, SETUP_INSTRUCTIONS.md (Optional block + Phase 6 workstream bullet), DEPLOYMENT.md Optional table. Full make test green (148 unit / e2e / 5 integration). All 3 plan tasks complete.

## 2026-07-18 — verification: PASS via startup smoke matrix; demo scenario explicitly SKIPPED (checkpoint 5)
Demo-scenario run skipped per verifying-with-demo-scenarios' allowance for genuinely non-agent-facing work, owner-approved at the working-doc gate: this phase changes zero tool/agent behavior (APP_MODE has no consumers), and every fashion.md scenario scripts agent behavior. Substitute evidence, run at the full `import app.agent` level:
- unset → boot OK, mode = demo
- APP_MODE=demo → boot OK, mode = demo
- APP_MODE=connected → boot OK, mode = connected (readable, inert)
- APP_MODE=garbage → ValueError: "Invalid APP_MODE='garbage'. Allowed values: demo, connected; unset defaults to 'demo'." (exit 1; same failure at pytest collection)
Deploy validation: actual `deploy.sh --dry-run` command contains --set-env-vars=APP_MODE=demo (and =connected when set); deploy_ae_inline.py env_vars verified by grep + AST parse. Full make test green in Task 3 (148 unit / e2e / 5 integration).
