---
name: finishing-a-development-branch
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Detect environment → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Detect Environment

**Determine workspace state before presenting options:**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
```

This determines which menu to show and how cleanup works:

| State | Menu | Cleanup |
|-------|------|---------|
| `GIT_DIR == GIT_COMMON` (normal repo) | Standard 4 options | No worktree to clean up |
| `GIT_DIR != GIT_COMMON`, named branch | Standard 4 options | Provenance-based (see Step 6) |
| `GIT_DIR != GIT_COMMON`, detached HEAD | Reduced 3 options (no merge) | No cleanup (externally managed) |

### Step 3: Determine Base Branch

**In this repo, a `version_2_<feature>` branch always targets `version_2`, never `main`/`master`.** Check the branch name first:

```bash
git rev-parse --abbrev-ref HEAD   # version_2_<feature>?
git merge-base HEAD version_2 2>/dev/null
```

If the branch isn't a `version_2_*` workstream branch, fall back to the generic detection:

```bash
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 4: Present Options

**Normal repo and named-branch worktree — present exactly these 4 options:**

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Detached HEAD — present exactly these 3 options:**

```
Implementation complete. You're on a detached HEAD (externally managed workspace).

1. Push as new branch and create a Pull Request
2. Keep as-is (I'll handle it later)
3. Discard this work

Which option?
```

**Don't add explanation** - keep options concise.

### Step 5: Execute Choice

#### Option 1: Merge Locally

```bash
# Get main repo root for CWD safety
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"

# Merge first — verify success before removing anything
git checkout <base-branch>
git pull
git merge <feature-branch>

# Verify tests on merged result
<test command>

# Only after merge succeeds: cleanup worktree (Step 6), then delete branch
```

Then: Cleanup worktree (Step 6), then delete branch:

```bash
git branch -d <feature-branch>
```

For a `version_2_<feature>` workstream: mark its row in `.docs/version2-plan/STATUS.md` as "merged" and append a finish-checkpoint line to its `WORK_LOG.md` (see `tracking-workstream-progress`).

#### Option 2: Push, Create PR, and (for workstreams) Self-Merge

**This is the default/expected option for a `version_2_<feature>` workstream.** The owner can raise **and** merge PRs on this repo, so the full workstream flow is PR → self-merge → cleanup → next worktree from the freshly-updated `version_2` (see `starting-a-workstream`'s sequencing policy).

```bash
# Push branch
git push -u origin <feature-branch>
# Open the PR against the base branch from Step 3
# (version_2 for version_2_<feature> workstream branches — never main for those)
gh pr create --base <base-branch> --title "<title>" --body "..."
```

**PR body convention** (workstream PRs): link the phase doc (`.docs/version2-plan/NN-*.md`), summarize what changed, and state how it was verified — test commands run and which `docs/demo-scenarios/` scenario passed. The commit-message rule extends here: no `Co-Authored-By: Claude` or any other AI-attribution footer in PR bodies.

**Path A — workstream self-merge (default for `version_2_<feature>`):** confirm with the owner, then merge the PR yourself:

```bash
gh pr merge <pr-number> --squash --delete-branch   # or --merge, owner's call
```

After the merge lands: clean up the worktree (Step 6), then `git checkout version_2 && git pull` in the main checkout, and update tracking (see `tracking-workstream-progress`) — this workstream's `STATUS.md` row → `merged` (single-writer, in the main checkout), plus a finish-checkpoint line in its `WORK_LOG.md`. The next workstream's worktree branches from this fresh `version_2`.

**Path B — PR left open (non-workstream branches, or the owner wants review time first):** stop after creating the PR. **Do NOT clean up the worktree** — it's needed alive to iterate on PR feedback. Mark the `STATUS.md` row "PR open" with the PR link and append a finish-checkpoint line to `WORK_LOG.md`; run Path A's merge + cleanup steps when the PR is merged later.

#### Option 3: Keep As-Is

Report: "Keeping branch <name>. Worktree preserved at <path>."

**Don't cleanup worktree.**

#### Option 4: Discard

**Confirm first:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
```

Then: Cleanup worktree (Step 6), then force-delete branch:
```bash
git branch -D <feature-branch>
```

For a `version_2_<feature>` workstream: mark its row in `.docs/version2-plan/STATUS.md` as "discarded" with a one-line reason, and append a finish-checkpoint line to its `WORK_LOG.md`.

### Step 6: Cleanup Workspace

**Runs for Options 1 and 4, and for Option 2 Path A after the PR is merged.** Option 2 Path B and Option 3 always preserve the worktree.

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
```

**If `GIT_DIR == GIT_COMMON`:** Normal repo, no worktree to clean up. Done.

**If worktree path is under `.claude/worktrees/`:** This worktree is session-managed via `EnterWorktree` (that's how `starting-a-workstream` creates them). Do **not** run raw `git worktree remove` — use `ExitWorktree({action: "remove"})` (add `discard_changes: true` only for Option 4, after the typed confirmation), which restores the session to the main checkout and removes the worktree in one step. If ExitWorktree reports no active worktree session (e.g. a fresh session that never entered it), fall back to the manual removal below.

**If worktree path is under `.worktrees/` or `worktrees/`:** Superpowers created this worktree — we own cleanup.

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove "$WORKTREE_PATH"
git worktree prune  # Self-healing: clean up any stale registrations
```

**Otherwise:** The host environment (harness) owns this workspace. Do NOT remove it. If your platform provides a workspace-exit tool, use it. Otherwise, leave the workspace in place.

## Quick Reference

| Option | Merge | Push | Keep Worktree | Cleanup Branch |
|--------|-------|------|---------------|----------------|
| 1. Merge locally | yes | - | - | yes |
| 2A. PR + self-merge (workstream default) | via PR | yes | cleaned after merge | yes (via PR) |
| 2B. PR left open | - | yes | yes | - |
| 3. Keep as-is | - | - | yes | - |
| 4. Discard | - | - | - | yes (force) |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Open-ended questions**
- **Problem:** "What should I do next?" is ambiguous
- **Fix:** Present exactly 4 structured options (or 3 for detached HEAD)

**Cleaning up worktree while a PR is still open (Option 2 Path B)**
- **Problem:** Remove worktree user needs for PR iteration
- **Fix:** Cleanup only for Options 1 and 4, or for Option 2 Path A *after* the merge has landed

**Deleting branch before removing worktree**
- **Problem:** `git branch -d` fails because worktree still references the branch
- **Fix:** Merge first, remove worktree, then delete branch

**Running git worktree remove from inside the worktree**
- **Problem:** Command fails silently when CWD is inside the worktree being removed
- **Fix:** Always `cd` to main repo root before `git worktree remove`

**Cleaning up harness-owned worktrees the wrong way**
- **Problem:** Raw `git worktree remove` on a session-managed worktree leaves the harness pointing at a deleted directory
- **Fix:** `.claude/worktrees/` paths → `ExitWorktree`; `.worktrees/`/`worktrees/` paths → manual removal; anything else → leave it alone

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request
- Remove a worktree before confirming merge success
- Clean up worktrees you didn't create (provenance check)
- Run `git worktree remove` from inside the worktree

**Always:**
- Verify tests before offering options
- Detect environment before presenting menu
- Present exactly 4 options (or 3 for detached HEAD)
- Get typed confirmation for Option 4
- Confirm with the owner before self-merging a workstream PR (Option 2 Path A)
- Clean up worktree only for Options 1 & 4, or Option 2 Path A after merge
- Use `ExitWorktree` for `.claude/worktrees/` paths, never raw `git worktree remove`
- `cd` to main repo root before manual worktree removal
- Run `git worktree prune` after manual removal
