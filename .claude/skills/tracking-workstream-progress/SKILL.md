---
name: tracking-workstream-progress
description: Use at the start of every session touching a .docs/version2-plan/ workstream (especially after context compaction or a resumed session) and at every phase transition within one — owns the cross-workstream STATUS.md and the per-workstream WORK_LOG.md
---

# Tracking Workstream Progress

## Overview

Two durable, git-tracked files carry the workstream lifecycle across context compaction and across workstreams: `.docs/version2-plan/STATUS.md` (cross-workstream index) and `.docs/version2-plan/working-docs/<NN>-<name>/WORK_LOG.md` (per-workstream, append-only). Neither is `subagent-driven-development`'s own `.superpowers/sdd/progress.md` ledger — that one is git-ignored scratch, scoped to a single implement-phase execution, and gone once the worktree is cleaned up after merge. These two are the permanent record.

`<NN>` is the phase doc's **filename prefix**, which equals the phase number since the 2026-07-16 renumbering (Phase 7's doc is `07-rpi-across-creatives-chart.md`, so its directory is `working-docs/07-rpi-across-creatives-chart/`). Same rule as `starting-a-workstream`.

**Announce at start:** "I'm using tracking-workstream-progress to [check status / update the log]."

## When to Use

- **Mandatory first action** of any session touching a workstream — every resume after context compaction, every session pickup, and before starting a new workstream (to see what earlier ones actually did, not just what the plan says they should have done).
- At every checkpoint listed below.
- This does not replace `.superpowers/sdd/progress.md` — that ledger still runs during `subagent-driven-development`; this skill's job is making sure its entries also land somewhere durable.

## Resume Check (run this first, always)

```bash
cat .docs/version2-plan/STATUS.md
cat .docs/version2-plan/working-docs/<NN>-<name>/WORK_LOG.md
```

Trust these files over your own memory of the conversation — that is the entire point of writing them down. If `STATUS.md` shows this phase already past kickoff, do not restart `starting-a-workstream`; resume at the step the log says you're at.

## STATUS.md — Cross-Workstream Index

One row per phase, updated in place (not appended). The `Doc` column carries the phase-doc filename prefix — equal to the `Phase` number since the 2026-07-16 renumbering; keep both columns filled (rows and records predating the renumbering used 0-based phase numbers, one less than the doc prefix):

```markdown
| Phase | Doc | Name | Status | Branch | PR | Last updated | Note |
|---|---|---|---|---|---|---|---|
| 6 | `07` | rpi-across-creatives-chart | implement in progress | version_2_rpi-chart | - | 2026-07-13 | Task 2/4 done |
```

Valid `Status` values and who sets them (every value has exactly one writer skill — if you're setting a value outside its skill, something's off-process):

| Status | Set by |
|---|---|
| `not started` | initial row (this file's seed, or `starting-a-workstream` Step 1 registering a new phase) |
| `kickoff in progress` | `starting-a-workstream` Step 1 |
| `plan in progress` | `starting-a-workstream` Step 6 (working doc approved) |
| `implement in progress` | `writing-plans` Plan Approval (plan approved) |
| `verify in progress` | `verifying-with-demo-scenarios` Step 0 |
| `PR open` / `merged` / `discarded` | `finishing-a-development-branch` |

**Single-writer rule:** `STATUS.md` is only ever edited in the **main checkout** — never in a worktree, so concurrent/successive workstreams can't produce conflicting copies of the shared index. From inside a worktree, resolve the main checkout with:

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
# edit "$MAIN_ROOT/.docs/version2-plan/STATUS.md", then commit it directly on version_2
```

`WORK_LOG.md`, by contrast, lives **branch-side** — edit it in the worktree, commit it on the workstream branch; it reaches `version_2` with the PR.

## WORK_LOG.md — Per-Workstream Durable History

Append-only, one entry per checkpoint, newest at the bottom:

```markdown
## 2026-07-13 14:02 — kickoff approved
[six-dimension restatement summary, or link to working-doc.md]

## 2026-07-13 15:40 — Task 2 complete (mirrors .superpowers/sdd/progress.md)
commits abc1234..def5678, review clean

## 2026-07-13 17:10 — demo scenario verification: PASS
beverage-vertical scenario, see verification report path
```

### Checkpoints — append at each of these, never skip one

Each checkpoint has a named writer — the skill that owns that step appends it, so no checkpoint depends on anyone "remembering":

1. Kickoff: worktree created, phase doc research done — written by `starting-a-workstream` Step 1 (created with the worktree), amended when Step 2's research completes
2. Working doc approved — written by `starting-a-workstream` Step 6
3. Plan approved — written by `writing-plans`' Plan Approval section
4. Every `subagent-driven-development` task-ledger append (mirrored here verbatim — see that skill's Durable Progress section)
5. Demo-scenario verification result (pass/fail, which scenario, path to the verifier subagent's report) — written by `verifying-with-demo-scenarios` Step 3
6. Finish — written by `finishing-a-development-branch` (merged / PR open+link / discarded)

## Discoveries — when reality diverges from the plan

Every workstream surfaces new facts: "we planned X, but implementation/research shows it's actually Y." These are **event entries**, appended whenever they happen (unlike the numbered checkpoints, which are lifecycle-fixed). Never let a discovery live only in conversation — conversation is exactly what compaction destroys. The moment one lands:

**1. Log it.** Append a `DISCOVERY` entry to this workstream's `WORK_LOG.md`:

```markdown
## 2026-07-20 11:30 — DISCOVERY: BlueZoo API rejects sub-15-min windows
Assumed (10-playout-attribution.md:41): windows down to 5 min supported.
Actual: API returns 422 below 15 min — confirmed against sandbox, curl output in scratch/.
Blast radius: Phase 11 attribution granularity; 99-open-questions Q17; this plan's Task 3.
```

**2. Sweep the blast radius** — grep `.docs/version2-plan/*.md` (and the current plan) for the invalidated assumption. Three targets, in order:

- **This workstream:** amend the working doc / plan. If the discovery changes the *approved scope* (not just implementation detail), stop and re-run the approval gate before continuing — a plan built on X isn't approved for Y.
- **Downstream phase docs:** amend every affected `NN-*.md` **in this workstream's branch**, marking the change with provenance so the client can see why the plan moved: `> **Amended (workstream <NN>, 2026-07-20):** <what changed and why, one or two lines>`. If the discovery answers or reshapes an open question, update `99-open-questions.md` the same way. If it changes a dependency between phases, update the `STATUS.md` Note column (main checkout).
- **Durable knowledge:** promote facts that outlive this workstream to where future sessions actually look — operational gotchas into `CLAUDE.md`, env/setup changes into `SETUP_INSTRUCTIONS.md`, owner preferences/process corrections into Claude's memory directory.

**3. Ship the amendments with this workstream's PR.** That's the invariant this buys: **after every merge, the remaining plan docs are current as of everything learned so far.** The next workstream's kickoff research (re-verify phase-doc claims) then confirms freshness instead of excavating drift.

Branch-side amendments to plan docs are safe precisely because workstreams are sequential (self-merge model) — there's never a second branch editing the same docs concurrently.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "I remember what happened, no need to read the log" | You're reading this specifically after compaction, when you don't reliably remember — that's the premise of this skill. |
| "I'll batch all the WORK_LOG entries at the end" | Batching defeats the purpose — if you compact mid-batch, the gap is exactly what's lost. Append at the checkpoint, not after. |
| "The SDD ledger already has this, why duplicate it" | The SDD ledger is git-ignored scratch, gone after the worktree is cleaned up post-merge. WORK_LOG.md is what's left. |
| "I'll fix the downstream phase docs when I get to those phases" | By then the discovery's context is gone and the doc reads as authoritative. Amend at discovery time, in this branch, with provenance — that's the whole point of the Discoveries section. |

## Red Flags

- Starting work on a workstream without having read `STATUS.md` and its `WORK_LOG.md` first.
- A `WORK_LOG.md` with gaps at checkpoints 1-6 (one silently skipped).
- `STATUS.md` rows left "in progress" after a PR merges or a branch is discarded.
- A "turns out it's actually Y" moment discussed in conversation with no `DISCOVERY` entry in `WORK_LOG.md` and no amendment in the affected downstream docs.

## Verification Checklist

- [ ] `STATUS.md` and this workstream's `WORK_LOG.md` were read before any action this session
- [ ] `STATUS.md` row reflects the current real state (not stale)
- [ ] Every checkpoint above has a corresponding `WORK_LOG.md` entry

## See Also

- `starting-a-workstream` — creates the initial `STATUS.md` row and `WORK_LOG.md`
- `subagent-driven-development` — Durable Progress section, mirrored into `WORK_LOG.md`
- `finishing-a-development-branch` — final `STATUS.md` update
