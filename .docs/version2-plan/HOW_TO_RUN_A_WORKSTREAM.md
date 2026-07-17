# How to Run a Workstream — from "start Phase N" to shipped

Owner-facing walkthrough of the full workstream lifecycle: which skill fires at each step, what Claude does autonomously, and the exact moments your input is required. The skills themselves (`.claude/skills/`) are the enforcement mechanism; this doc is the map. If this doc and a skill ever disagree, the skill wins — then fix this doc.

Running example throughout: **Phase 7, the RPI-across-creatives chart** (phase doc `07-rpi-across-creatives-chart.md` — the filename prefix `07` equals the phase number since the 2026-07-16 renumbering, and is what names the workstream's folders/branch).

---

## The cast

| Step | Skill / agent | Produces | Needs your explicit yes? |
|---|---|---|---|
| 0. Resume check | `tracking-workstream-progress` | (reads STATUS.md + WORK_LOG.md) | no |
| 1. Kickoff | `starting-a-workstream` | worktree + branch, working doc | **yes — working doc** |
| 2. Plan | `writing-plans` | task-by-task plan.md | **yes — plan** |
| 3. Implement | `subagent-driven-development` | code, tests, commits | no (per-task subagents self-review) |
| 4. Verify | `verifying-with-demo-scenarios` → `demo-scenario-verifier` agent | PASS/FAIL + trace/screenshot evidence | no |
| 5. Review | `requesting-code-review` | whole-branch review findings | no (you see the findings) |
| 6. Finish | `finishing-a-development-branch` | PR into `version_2`, self-merge, cleanup | **yes — merge confirmation** |

Durable records at every step: `STATUS.md` (one row per phase, updated only in the main checkout) and the workstream's `WORK_LOG.md` (append-only, lives in the branch, ships with the PR).

## One-time prerequisite (before the first workstream ever)

The process infra — `.claude/skills/`, `.claude/agents/`, `.mcp.json`, `STATUS.md`, current `CLAUDE.md` — must be **committed on `version_2`** first. A worktree materializes only committed content; an uncommitted skill doesn't exist inside the worktree. `starting-a-workstream` checks this and refuses to proceed otherwise.

---

## Walkthrough: shipping Phase 7

### You type

> Start the workstream for Phase 7 (07-rpi-across-creatives-chart).

That single sentence is enough. Everything below is what happens next.

### Step 0 — Resume check (automatic)

Claude reads `STATUS.md`. Phase 7's row says `not started` → kickoff proceeds. (If it said anything else, Claude resumes at whatever step the row + `WORK_LOG.md` indicate instead of restarting — this is also exactly what happens after a crashed or compacted session.)

It also checks Phase 7's dependencies are `merged` in STATUS.md. Dependencies not merged → the workstream doesn't start; finish those first. Sequential, always.

### Step 1 — Kickoff (`starting-a-workstream`)

Claude:
1. Creates the worktree explicitly off `version_2` (never via plain `EnterWorktree`, which would branch off `origin/main`):
   ```bash
   git fetch origin && git checkout version_2 && git pull
   git worktree add .claude/worktrees/version_2_rpi-chart -b version_2_rpi-chart version_2
   ```
   then enters it and verifies `git merge-base HEAD version_2 == git rev-parse version_2`.
2. Registers the STATUS.md row (`kickoff in progress`, in the main checkout) and creates `working-docs/07-rpi-across-creatives-chart/WORK_LOG.md` with checkpoint 1.
3. **Re-verifies the phase doc against current code** — every `file:line` cite, every claimed function/schema. Phase docs are written ahead of implementation; this step catches drift before it becomes a wrong plan.
4. Drafts `working-doc.md`: research findings, implementation approach (with rejected alternatives when a real design choice existed), test plan (naming which `docs/demo-scenarios/` scenario must pass), out of scope.

**Your moment #1:** Claude restates intent across six dimensions (outcome, user, why now, success criteria, constraints, out-of-scope) and asks for an explicit yes. Push back here — this is the cheapest place to change direction. No plan or code exists until you approve.

### Step 2 — Plan (`writing-plans`)

Claude turns the approved working doc into `working-docs/07-rpi-across-creatives-chart/plan.md`: bite-sized tasks, each with exact file paths, real code in every step, test-first, a commit per task. No placeholders, no "add error handling later."

**Your moment #2:** explicit yes on the plan. On approval: checkpoint 3 in WORK_LOG.md, STATUS → `implement in progress`.

### Step 3 — Implement (`subagent-driven-development`)

Per task: a fresh implementer subagent executes it, a fresh reviewer subagent gates it, and the ledger entry mirrors into `WORK_LOG.md` (checkpoint 4, one per task). The tracked PostToolUse hook runs `make test-unit` after every `app/**/*.py` edit — inside the worktree too, since `.claude/settings.json` is committed.

You don't need to be present per-task. Check in whenever; `WORK_LOG.md` always shows the true position.

### Step 4 — Verify (`verifying-with-demo-scenarios`)

STATUS → `verify in progress`. Beyond green tests, Claude dispatches the `demo-scenario-verifier` agent: it kills anything stale on port 8501, starts `make dev` *in this worktree*, drives the scenario's queries through the ADK web UI via chrome-devtools MCP, and checks the **Trace tab** (or the `/run` response's event list for `api_server`) to confirm the right tools fired with sane arguments. Evidence (screenshots, trace observations) lands in the report; result goes into `WORK_LOG.md` (checkpoint 5).

For Phase 7 this means: the new chart tool actually gets invoked by the Analytics Agent for a "compare RPI across creatives" query, and the chart artifact renders. A failing scenario blocks finishing — fix and re-verify.

If the phase touches a vertical with no scenario doc yet, writing one (adapted from `DEMO_GUIDE.md`, plus expected-tool-call assertions) is part of this step. `DEMO_GUIDE.md` itself is never run directly and never edited.

### Step 5 — Review (`requesting-code-review`)

Whole-branch review against the plan before anything ships. Findings come back to you; real issues get fixed in the branch (via `receiving-code-review`).

### Step 6 — Finish (`finishing-a-development-branch`)

Claude runs the full suite one last time, then:

```bash
git push -u origin version_2_rpi-chart
gh pr create --base version_2 --title "..." --body "..."   # phase-doc link + what changed + how verified; no AI-attribution footers
```

**Your moment #3:** confirm the self-merge. Then:

```bash
gh pr merge <pr> --squash --delete-branch
```

Worktree exits and is removed, `version_2` is pulled fresh in the main checkout, STATUS → `merged` + finish checkpoint in WORK_LOG.md (which is now part of `version_2` history, PR'd along with the code).

### Next workstream

> Start the workstream for Phase 8.

New worktree, branched from the `version_2` that now *contains* Phase 7. Same loop.

---

## Mid-workstream discoveries: "we thought X, it's actually Y"

This will happen constantly, and it's the difference between plans that stay useful and plans that rot. The protocol (owned by `tracking-workstream-progress`, Discoveries section — this is the summary):

1. **Log it immediately** — a `DISCOVERY` entry in `WORK_LOG.md`: what was assumed (with the doc cite), what's actually true (with evidence), and the suspected blast radius. Conversation is not a record; compaction eats it.
2. **Sweep the blast radius** — three targets, checked in order:
   - **This workstream:** amend the working doc/plan. If the discovery changes *approved scope* (not just implementation detail), Claude stops and re-runs the approval gate with you.
   - **Downstream plan docs:** every affected `NN-*.md` gets amended *in this branch*, marked with provenance — `> **Amended (workstream 07, 2026-07-20):** …` — so the client-visible history shows why the plan moved. Answered/reshaped open questions update `99-open-questions.md`; changed inter-phase dependencies update the STATUS.md Note column.
   - **Durable knowledge:** operational facts every future session needs → `CLAUDE.md` gotchas; env/setup changes → `SETUP_INSTRUCTIONS.md`; your preferences and process corrections → Claude's persistent memory.
3. **Amendments ship with this workstream's PR.** The invariant: after every merge, the remaining plan is current as of everything learned so far. The next kickoff's re-verification step then *confirms* freshness instead of excavating months of drift.

Worked example: during Phase 11 implementation, the BlueZoo sandbox rejects sub-15-minute windows that `10-playout-attribution.md` assumed were available. Same turn: DISCOVERY entry in WORK_LOG.md → `10-*.md` amended with provenance → Q17 in `99-open-questions.md` updated (it asked exactly this) → Phase 7's chart granularity note checked for impact → if it's an API behavior every future session must know, one line in CLAUDE.md's gotchas. All of it lands in the Phase 11 PR.

**Your role:** discoveries that change scope, cost, or an open-question answer get surfaced to you at the moment they're found — not batched into the PR description. Everything else is recorded and flows through the PR for your review at merge time.

---

## Trivial-phase fast path

For a phase `00-overview.md` rates Trivial (e.g. Phase 1, the two-config-string model swap): step 3's per-task subagent dispatch may be replaced by inline execution of a one-task plan. **Everything else is non-negotiable** — working-doc approval, plan approval, real verification, WORK_LOG/STATUS checkpoints, PR + self-merge. The fast path trims ceremony, not evidence.

## Interruptions, compaction, new sessions

Whatever the reason the thread broke: the first action of any session touching a workstream is the resume check — read `STATUS.md`, read that workstream's `WORK_LOG.md`, resume at the step they indicate. The files outrank anyone's memory of the conversation, including Claude's. You can also just type:

> Where are we? Check the workstream status.

## Your approval moments, in total

1. Working doc (kickoff) — shapes *what and how*.
2. Plan — shapes *the exact task breakdown*.
3. Self-merge confirmation — ships it.
4. Ad hoc: scope-changing discoveries, and any open question a phase hits that only you (or BlueZoo) can answer.

Everything else — research, task execution, testing, demo verification, code review, tracking — runs without you, and leaves a durable trail you can audit at any point in `STATUS.md`, `WORK_LOG.md`, and the PR.

## Prompt cheatsheet

| You want | You type |
|---|---|
| Begin a phase | "Start the workstream for Phase N (`<NN>-<name>`)." |
| Resume anything | "Where are we? Check the workstream status." |
| Mid-flight status | "Show me this workstream's WORK_LOG." |
| Record a fact you know is wrong in the plan | "Discovery: <X is actually Y> — log it and sweep the plan docs." |
| Ship it | "Looks good — raise the PR and merge it." |
