# Workstream 06 — app-mode-config-skeleton — WORK_LOG

Append-only, newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-18 — kickoff: worktree created (checkpoint 1)
Worktree .claude/worktrees/version_2_app-mode-config, branch version_2_app-mode-config off version_2 @ 49d015c (post-ws05 merge). Phase doc: .docs/version2-plan/06-app-mode-config-skeleton.md (rated Small; no dependencies). Research done (3 parallel agents: config/runtime, deploy, docs/tests): all phase-doc claims verified; drift found — test_config.py already exists (reload pattern ready), deploy step 6 misses the primary deploy_ae_inline.py path (env_vars dict :304-308), invalid value must raise ValueError (deploy_ae_inline catches ImportError), AppMode as str-Enum per house style, SETUP_INSTRUCTIONS.md :97 reserves the APP_MODE note. Working doc drafted.
