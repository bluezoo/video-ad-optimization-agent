---
name: verifying-with-demo-scenarios
description: Use before claiming a workstream's implementation is done — runs the automated test suite, then drives a local adk web (or api_server) instance through vertical-specific demo scenarios via chrome-devtools MCP to confirm actual agent/tool behavior, not just green tests
---

# Verifying With Demo Scenarios

## Overview

Passing `make test-unit`/`make test-e2e`/`make test-integration` proves the code does what the tests assert — it does not prove the ADK agent actually behaves correctly end-to-end from a user's perspective (tool selection, routing between sub-agents, HITL activation flow, chart/artifact rendering). This skill closes that gap: run a real local `adk web` instance and drive it through a scripted demo scenario, inspecting the Trace tab / network traffic to confirm the right tools fired with the right arguments and the right output came back.

**Announce at start:** "I'm using verifying-with-demo-scenarios to verify Phase <N> against the <vertical> scenario."

## When to Use

- The final task of every `.docs/version2-plan/` workstream, before `requesting-code-review`/`finishing-a-development-branch` — per `subagent-driven-development`'s Integration section, this is a required plan task, not optional polish.
- **Not** a replacement for unit/e2e/integration tests — run those first; this skill assumes they're already green and checks the layer they can't reach.

## Step 0: Mark the Checkpoint

On starting this skill, update the workstream's `.docs/version2-plan/STATUS.md` row to `verify in progress` (single-writer, in the **main checkout** — see `tracking-workstream-progress`).

## Step 1: Pick or Write the Scenario

`DEMO_GUIDE.md` (repo root) is fashion-specific and stays untouched — and it is **never run directly** by a verifier: it's a human demo script with no expected-tool-call assertions, so there's no way to tell pass from fail. It's the adaptation source only.

Runnable scenarios live in `docs/demo-scenarios/<vertical>.md`, in the same Act/Scene shape as `DEMO_GUIDE.md` (Query + what to check), plus explicit expected-tool-call assertions per scene (which tool, roughly which arguments, what a correct response contains).

**`docs/demo-scenarios/fashion.md` does not exist yet.** The first workstream whose verification exercises the fashion vertical writes it in this step, adapted from `DEMO_GUIDE.md` with the assertions added. Likewise, if the phase touched a vertical with no existing scenario doc (see the product-schema/prompt generalization phases), write one before running — a phase claiming "works for any vertical" with no non-fashion scenario to prove it is not actually verified.

## Step 2: Run It

Dispatch to the `demo-scenario-verifier` subagent (keeps chrome-devtools' verbose trace/screenshot output out of the controlling session's context). When more than one vertical is affected, dispatch one verifier per scenario **sequentially, never in parallel** — `make dev` hardcodes port 8501 in the Makefile, so concurrent verifiers would collide on the same server. Requires the `chrome-devtools` MCP server (declared in the repo's `.mcp.json`; runs via `npx`, no separate install).

1. Start `make dev` (or `adk web`/`adk api_server` directly) in the workstream's worktree — after killing any stale server on the port (see the subagent's pre-step).
2. Navigate to the local UI with chrome-devtools MCP (`navigate_page`, `take_snapshot`).
3. Drive each scene's query through the chat input.
4. Confirm the expected tool(s) fired, with sane arguments, and the response matches what the scenario expects. For `adk web`, use the Trace tab (Event/Request/Response/Graph). For `api_server`, assert against the `/run` response body itself — it carries the full event list, including every `functionCall`/`functionResponse` — rather than reconstructing calls from browser network traffic.
5. Screenshot anything visual (charts, activated video) as evidence.
6. Report PASS/FAIL per scene, with trace/screenshot evidence paths — never a bare "looks right."

## Step 3: Record the Result

Append the verification result to the workstream's `WORK_LOG.md` (via `tracking-workstream-progress`): pass/fail, which scenario(s), path to the verifier's evidence. A failing scenario blocks `finishing-a-development-branch` — fix and re-verify, don't proceed with a known-failing demo path.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "Unit tests pass, that's enough" | Unit tests don't exercise the LLM's tool routing or the actual ADK request/response cycle — this is exactly the gap this skill closes. |
| "I tested this manually earlier in the session, no need to re-run" | "Earlier in the session" isn't evidence attached to this workstream's record — run it fresh and record the result in `WORK_LOG.md`. |
| "This phase doesn't touch the UI, skip verification" | Most phases touch tool behavior the UI's trace view is the only practical way to observe — skip only for genuinely non-agent-facing work (e.g. a pure internal refactor with unchanged tool contracts), and say so explicitly in `WORK_LOG.md` rather than silently omitting the step. |

## Red Flags

- Claiming a workstream done with no demo-scenario evidence in `WORK_LOG.md`.
- A scenario doc with queries but no expected-tool-call assertions (can't tell pass from fail).
- Running the scenario against a stale `adk web` process left over from a previous workstream instead of this worktree's code.

## Verification Checklist

- [ ] `STATUS.md` row set to `verify in progress` (main checkout) when this skill started
- [ ] Scenario doc exists (or was written) for every vertical this phase touches — never `DEMO_GUIDE.md` directly
- [ ] `demo-scenario-verifier` ran against this worktree's own `make dev`/`adk web`, not a stale process (port 8501 cleared first)
- [ ] Multiple scenarios were run sequentially, not in parallel
- [ ] Trace/response-event evidence collected per scene, not just a final chat response
- [ ] Result (pass/fail + evidence path) appended to `WORK_LOG.md`

## See Also

- `demo-scenario-verifier` (`.claude/agents/demo-scenario-verifier.md`) — the subagent this skill dispatches
- `tracking-workstream-progress` — where the result gets recorded
- `DEMO_GUIDE.md` — the fashion-specific template this skill's scenario docs are adapted from
