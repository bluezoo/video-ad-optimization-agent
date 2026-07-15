---
name: starting-a-workstream
description: Use when beginning work on a .docs/version2-plan/ phase for the first time — creates the isolated worktree/branch, re-validates the phase doc against current code, and produces an approved working doc before any implementation plan is written
---

# Starting a Workstream

## Overview

Kick off one `.docs/version2-plan/` phase: isolate it in its own worktree/branch, re-check the phase doc's claims against the actual current codebase (phase docs are written ahead of implementation and can go stale), and negotiate a working doc the user explicitly approves before any plan or code exists.

**Announce at start:** "I'm using the starting-a-workstream skill to kick off Phase <N>."

## Naming: what `<NN>` means

`<NN>` in every path below is **the phase doc's filename prefix**, not the phase number — they're offset by one (Phase 6's doc is `07-rpi-across-creatives-chart.md`, so its workstream directory is `working-docs/07-rpi-across-creatives-chart/`). The filename prefix is the only unambiguous, sortable identifier; `tracking-workstream-progress` uses the same rule. STATUS.md's Phase column keeps the phase number — that's fine, the two coexist; just never use the phase number in a directory name.

## When to Use

- Beginning any `.docs/version2-plan/NN-*.md` phase for the first time.
- **NOT for:** resuming a workstream already in progress — use `tracking-workstream-progress`'s resume check and pick up where the log says you are, don't re-run kickoff. **NOT for:** work with no phase doc — use `brainstorming` instead.

## Sequencing policy (self-merge model)

The owner can raise **and merge** PRs on this repo. Workstreams therefore run **sequentially by default**: finish one (PR into `version_2`, merge it yourself per `finishing-a-development-branch`), then create the next worktree from the freshly-updated `version_2`. A phase whose dependencies aren't `merged` in STATUS.md does not start — no branching off unmerged workstream branches, no stacking. Two phases may run in parallel only if 00-overview.md marks them independent of each other, and even then each still branches from `version_2` only.

## Step 0: Resume check and prerequisites

- Run `tracking-workstream-progress`'s resume check first — read `.docs/version2-plan/STATUS.md`. If this phase's row is anything other than "not started," stop and hand off to whichever step it's actually at.
- **Prerequisite:** the process infra (`.claude/skills/`, `.claude/agents/`, `STATUS.md`, current `CLAUDE.md`) must already be committed on `version_2`. A worktree materializes only committed content — if `git ls-tree version_2 --name-only .docs/version2-plan/STATUS.md` comes back empty, stop and commit the infra first.
- Check this phase's dependencies (STATUS.md Note column / phase doc Dependencies line) are all `merged`. If not, per the sequencing policy above, finish those first.

## Step 1: Isolate

Do **not** use `EnterWorktree({name})` here — its default `baseRef: fresh` branches from `origin/main` (this repo's default branch), not `version_2`, and no local checkout state changes that. Create the worktree explicitly off `version_2`, then enter it by path:

```bash
git fetch origin && git checkout version_2 && git pull   # be current first
git worktree add .claude/worktrees/version_2_<feature> -b version_2_<feature> version_2
```

Then `EnterWorktree({path: ".claude/worktrees/version_2_<feature>"})`.

- Verify: `git rev-parse --abbrev-ref HEAD` shows `version_2_<feature>`, and `git merge-base HEAD version_2` equals `git rev-parse version_2`.
- **If that verification fails** (wrong base): exit the worktree (`ExitWorktree` with `action: "remove"`), delete the branch (`git branch -D version_2_<feature>`), and redo this step — do not try to fix a wrong-base worktree in place with rebase.
- Register the workstream in `.docs/version2-plan/STATUS.md` with status "kickoff in progress" — per `tracking-workstream-progress`, STATUS.md is single-writer and lives in the **main checkout**, not this worktree.
- Create the workstream's durable log now: `mkdir -p .docs/version2-plan/working-docs/<NN>-<name>` (in the worktree) and write `WORK_LOG.md` with its first entry — checkpoint 1, "kickoff: worktree created" (append "phase doc research done" to the same entry when Step 2 completes).

## Step 2: Research

Read the phase doc in full, then re-verify every concrete claim against the actual current code — file:line citations, function names, table/schema shapes — because phase docs are written ahead of implementation and drift. Where the phase doc cites `file:line`, open that file and confirm the claim still holds; note anywhere it doesn't. Check the phase's `Dependencies` line against `STATUS.md`, not just against the phase doc's own narrative — a dependency phase doc can claim "done" while `STATUS.md` shows it's actually still mid-implementation.

If research invalidates a claim in *another* phase's doc (not just this one's), that's a discovery — handle it per `tracking-workstream-progress`'s Discoveries section (log + amend with provenance in this branch), don't just note it privately in the working doc.

## Step 3: Generate approach options (only when there's a genuine design choice)

Skip this step for mechanical phases (config swap, bug fix, dependency bump) — go straight to Step 4.

Run it when the phase doc leaves open *how* to build something, not just *what* (e.g., "which BlueZoo endpoint answers a sub-15-minute window," "what's the chart artifact's output contract"):

1. Reframe the phase's goal as "How might we <goal>."
2. Generate 2-3 real candidate approaches — not padding; if there's genuinely one sane approach, say so and move to Step 4.
3. Stress-test each against: fit with this repo's existing patterns (e.g. `compute_rpi()` as the single source of truth, ADK tool conventions), maintainability, and the plan's own "don't overcomplicate" philosophy (`.docs/version2-plan/00-overview.md`).
4. Put the recommended approach **and** the rejected alternatives (with why) into the working doc's "Implementation approach" section, so the reasoning survives even for a reader who'd have picked differently.

## Step 4: Draft the working doc

Save to `.docs/version2-plan/working-docs/<NN>-<name>/working-doc.md`:

```markdown
# Workstream <NN>: <name>

**Branch:** version_2_<feature>
**Phase doc:** .docs/version2-plan/NN-*.md

## Research findings
[What Step 2 confirmed or found stale, with file:line evidence]

## Implementation approach
[The chosen approach; alternatives considered and why rejected, if Step 3 ran]

## Test plan
[Concrete: which unit/e2e/integration tests, AND which demo scenario(s) under
docs/demo-scenarios/ this phase must pass via verifying-with-demo-scenarios —
never leave this as "make test-unit passes," which doesn't prove agent behavior]

## Out of scope
[Explicit — what this workstream will NOT touch]
```

## Step 5: Approval gate

Before asking for approval, restate intent across six dimensions and require an explicit yes:

- **Outcome** — what will exist when this workstream is done
- **User** — who this serves (the client's demo, a specific vertical, internal cleanup)
- **Why now** — why this phase, in this order, per the phase doc's sequencing
- **Success** — the concrete pass/fail from the test plan
- **Constraint** — anything binding (don't touch X, must stay demo-mode-safe, etc.)
- **Out of scope** — repeat it; don't just imply it

For any open question, ask one at a time with your own confidence-rated hypothesis attached ("I think the answer is X, ~70% confident — because...") rather than an open-ended question — this forces a fast confirm-or-correct instead of restarting the analysis. Stop asking once your understanding would be ~95% predictable; don't manufacture more questions past that point.

**Require an explicit yes to the restated six-dimension summary before writing a plan or touching code.** "Sounds good" against a vague restatement is not approval — restate concretely enough that a yes is a real commitment.

## Step 6: Handoff

Once approved: append checkpoint 2 ("working doc approved") to the workstream's `WORK_LOG.md`, mark `STATUS.md` "plan in progress" (in the main checkout), and invoke `writing-plans` (seeded from the working doc's "Implementation approach").

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "The phase doc already says exactly what to do, skip research" | Phase docs are written ahead of implementation against a snapshot of the code — re-verify file:line claims, don't trust them silently. |
| "This is a simple phase, skip the approval gate" | Simple phases still branch on assumptions (which table, which existing function to extend) — a 30-second confirm is cheaper than redoing the work. |
| "I'll generate options for every phase, to be thorough" | Padding options for a mechanical fix wastes review time — only generate them where a real design choice exists. |
| "The user approved the overall process once, no need for per-workstream approval" | Approving the process isn't approving every future working doc — each workstream still needs its own explicit yes. |

## Red Flags

- Starting to write a plan or touch code before the working doc has an explicit yes.
- A working doc with no "Out of scope" section.
- A test plan that only says "existing tests pass," naming no demo scenario.
- Using `EnterWorktree({name})` instead of `git worktree add … version_2` + `EnterWorktree({path})` — the name form branches off `origin/main` regardless of what's checked out locally.
- Starting a phase whose dependencies aren't `merged` in STATUS.md, or branching off anything other than `version_2`.
- Reaching Step 4 with no `WORK_LOG.md` on disk (checkpoint 1 was skipped).

## Verification Checklist

- [ ] Process infra confirmed committed on `version_2` before the worktree was created
- [ ] Worktree created via `git worktree add … version_2` + `EnterWorktree({path})`, confirmed off `version_2` (`git merge-base HEAD version_2` == `git rev-parse version_2`)
- [ ] `WORK_LOG.md` created with checkpoint 1 during Step 1 (not retroactively)
- [ ] Every phase-doc file:line claim re-checked against current code
- [ ] Working doc has Research findings, Implementation approach, Test plan (naming a demo scenario), Out of scope
- [ ] Explicit yes received to the six-dimension restatement
- [ ] `STATUS.md` row updated in the main checkout; checkpoint 2 appended on approval

## See Also

- `tracking-workstream-progress` — `STATUS.md`/`WORK_LOG.md` mechanics
- `writing-plans` — next step after approval
- `verifying-with-demo-scenarios` — what the test plan's demo-scenario check actually runs
