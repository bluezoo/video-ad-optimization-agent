# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Google ADK multi-agent system that closes the loop on in-store video ad optimization: Veo3 generates candidate video ads, BlueZoo sensors measure impressions, revenue-per-impression (RPI) picks winners, and winners seed the next generation round. Root agent is a Coordinator that routes to a Campaign Agent, Media Agent, and Analytics Agent, plus Review tools for human-in-the-loop (HITL) video activation.

Key source layout: `app/agent.py` (agent graph), `app/config.py` (models/env), `app/tools/` (campaign, video, review, metrics, maps, image tools), `app/database/` (SQLite + mock data), `app/models/` (Pydantic models), `app/agent_engine_app.py` (Agent Engine entrypoint).

`docs/METRICS.md` is the authoritative glossary for every metric (impressions, RPI, revenue, circulation, dwell time) — read it before changing metric-related code; code comments and README prose do not override it.

## Version 2 plan

**`.docs/version2-plan/` is the sole authoritative plan for ongoing work.** Start at `00-overview.md` for sequencing and philosophy, then the numbered phase docs (`01-*.md` through `15-*.md`); `99-open-questions.md` consolidates every phase's open questions. `STATUS.md` in that folder is the cross-workstream progress index — read it before starting or resuming any phase.

`.docs/2026-07-12-version2-review-and-plan.md` is superseded and moved to `.docs/.backup/` (gitignored, kept locally as historical record only) — do not treat it as current.

## Workstream process

Each `.docs/version2-plan/` phase is implemented as an isolated **workstream**: a git worktree on branch `version_2_<feature>`, branched off `version_2` (never `main`). Progress becomes visible to the client (who owns `origin`) via a PR into `version_2` per workstream, not a single big-bang merge.

**Self-merge, sequential:** the owner raises *and merges* each workstream PR into `version_2`, then the next worktree is created from the freshly-updated `version_2`. No stacking on unmerged workstream branches; a phase whose dependencies aren't `merged` in `STATUS.md` doesn't start. Working docs, plans, and `WORK_LOG.md`s under `.docs/version2-plan/working-docs/` are git-tracked and ship with each PR — deliberate, so the client sees the process record, not just diffs.

Lifecycle, each step backed by a skill in `.claude/skills/` — a mix of skills vendored from the `superpowers` plugin (some modified for this repo's conventions) and three written for this repo (`starting-a-workstream`, `tracking-workstream-progress`, `verifying-with-demo-scenarios`); see each `SKILL.md`'s frontmatter `description` for when to use it:

1. **Resume check** — `tracking-workstream-progress`: read `STATUS.md` + this workstream's `WORK_LOG.md` first, always (mandatory after any context compaction or session resume).
2. **Kickoff** — `starting-a-workstream`: create the worktree/branch, re-verify the phase doc's claims against current code, produce a working doc, get explicit approval before any plan or code exists.
3. **Plan** — `writing-plans`: turn the approved working doc into a task-by-task implementation plan, saved alongside the working doc.
4. **Implement** — `subagent-driven-development`: fresh implementer + reviewer subagent per task; every ledger entry also mirrors into the workstream's durable `WORK_LOG.md`.
5. **Verify** — `verifying-with-demo-scenarios`: beyond the automated test suite, drive a local `adk web`/`api_server` instance through vertical-specific demo scenarios (`docs/demo-scenarios/<vertical>.md`, modeled on `DEMO_GUIDE.md`'s Act/Scene shape but not replacing it — its client-facing demo script stays fashion-specific; since 2026-07-22 the file also hosts the owner's "Workstream Testing Journeys" section, see below) via chrome-devtools MCP (declared in the repo's `.mcp.json`), dispatched to the `demo-scenario-verifier` subagent (`.claude/agents/`), one scenario at a time (the dev server port is fixed at 8501).
6. **Review & finish** — `requesting-code-review` for the whole branch, then `finishing-a-development-branch` (modified: PR into `version_2`, then self-merge per the sequencing model above).

**Trivial-phase fast path:** for a phase `00-overview.md` rates Trivial (e.g. Phase 1's two-config-string change), step 4's per-task subagent dispatch may be replaced by inline execution of a one-task plan. Everything else stays non-negotiable: working-doc and plan approval, real verification, `WORK_LOG.md`/`STATUS.md` checkpoints, PR via `finishing-a-development-branch`.

**Owner demo guide (rule changed 2026-07-22, ws11a):** workstream manual-testing journeys — copy-paste prompts/commands + expected results — live in the root `DEMO_GUIDE.md`, section **"Workstream Testing Journeys"** (owner directive: always the root guide, never a workstream-side file). Any workstream that changes agent-visible behavior (tools, prompts, routing, instructions, artifacts) must add/adjust its journeys there before raising its PR, and prune journeys its change invalidates. `.docs/version2-plan/demo_guide.md` remains as the historical record of pre-ws11a journeys (ws08-ws10 parts) — don't add new journeys to it; it superseded ws08's one-off `USER_JOURNEY_TEST_GUIDE.md` the same way.

**Discoveries (plan-reality divergence):** when work reveals a planned assumption is wrong ("we thought X, it's actually Y"), follow `tracking-workstream-progress`'s Discoveries section: log a `DISCOVERY` entry in the workstream's `WORK_LOG.md`, amend every affected downstream phase doc and `99-open-questions.md` in the same branch with a provenance note (`> **Amended (workstream <NN>, date):** …`), and promote durable facts to `CLAUDE.md`/`SETUP_INSTRUCTIONS.md`/memory. Plan docs are living documents — after every merge they must be current as of everything learned so far. `.docs/version2-plan/HOW_TO_RUN_A_WORKSTREAM.md` is the owner-facing walkthrough of the whole lifecycle, including this.

Setup/deployment instructions for this evolving work live in `SETUP_INSTRUCTIONS.md`, not `README.md` — leave `README.md` as the client-facing doc it already is.

## Commands

```bash
make install        # create .venv, install app/requirements.txt
make dev            # run ADK web UI locally on :8501 (alias: make playground)
make test           # unit + e2e (default; fast, zero LLM calls, seconds)
make test-unit      # tests/unit only, ~4s, no LLM calls — fastest feedback loop
make test-e2e       # tests/e2e workflow tests, ~1s, no LLM calls
make test-integration  # targeted subset of the live tier (tests/integration only, real LLM) — not part of `make test`
make test-live      # LIVE tier: tests/integration + tests/live against real Vertex APIs — ~11min, costs real money (owner: cost accepted, correctness first); needs app/.env, guard fails loudly if missing
make test-live-report  # agents-cli grade/compare reporting layer over live eval traces — INFORMATIONAL, not a gate (Task 15)
make test-all       # everything including slow Veo tests, ~10+ min
make test-coverage  # pytest --cov=app, HTML report in htmlcov/
make reset-db       # wipe campaigns.db, next `make dev` repopulates demo data
```

Run a single test: `pytest tests/unit/test_campaign_tools.py::TestClass::test_name -v`.

Pytest markers: `slow` (>30s, Veo/chart generation), `integration` (needs LLM), `live` (needs real Vertex APIs — Veo/image-gen/judge, part of the live tier), `veo` (needs Veo 3.1 API), `e2e`. **`make test` no longer runs `tests/integration`** (workstream 16) — integration moved to the live tier alongside the new `tests/live` (media pipeline + Gemini-judge tests); see the tier map above and the "live tier" section in `SETUP_INSTRUCTIONS.md` for setup and the flakiness watchlist.

Lint/format with ruff (config in `ruff.toml`): `make lint` (check only), `make format` (auto-fix + format). A `PostToolUse` hook (`.claude/settings.json`, git-tracked, needs `jq`) runs `make test-unit` automatically after edits to `app/**/*.py` — so the safety net works inside worktrees too. Personal settings (model overrides, plugins, env) belong in the gitignored `.claude/settings.local.json`, never in the tracked `settings.json`.

## Repo etiquette

- Do not add a `Co-Authored-By: Claude` (or similar AI attribution) trailer to commit messages — and the same rule applies to PR bodies.
- `README.md` is client-facing and stays untouched; local/dev setup instructions live in `SETUP_INSTRUCTIONS.md` instead (including corrections to anything `README.md` gets wrong — never edit `README.md` itself).
- `.claude/skills/` vendors the `superpowers` plugin's skills locally (some modified, plus three repo-specific ones — see the "Workstream process" section above) rather than depending on the global plugin install, so this repo's conventions travel with the branch. This is a one-time vendor, not auto-synced against upstream `superpowers` updates — re-vendor manually if a future superpowers release is worth pulling in. Inside these vendored skills, cross-references are bare skill names, never `superpowers:`-prefixed — the prefix would resolve to the global, unmodified plugin copies.

## Environment

Vertex AI path: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GCS_BUCKET`. AI Studio path: `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, `GOOGLE_API_KEY`, `GCS_BUCKET`. Optional: `GOOGLE_MAPS_API_KEY` (or `MAPS_API_KEY`) for maps tools — tests skip cleanly if unset. Vars go in `app/.env`. Optional: `APP_MODE=demo|connected` (default `demo`; empty counts as unset; any other value fails startup with a `ValueError` at config load) — inert until Phase 11 wires provider selection, and deliberately the only user-facing mode knob.

## Gotchas

- **Gemini 3.x models need `GOOGLE_CLOUD_LOCATION=global`** (the `us`/`eu` multi-region endpoints also work; most single regions like `us-central1` don't). `MODEL`, `IMAGE_GENERATION`, and `VIDEO_GEN_MODEL` in `app/config.py` are all Gemini 3.x / Veo 3.1 models — don't point deploys at a single-region endpoint for them. All three default to GA IDs and are env-overridable (`AGENT_MODEL`, `IMAGE_GENERATION_MODEL`, `VIDEO_GEN_MODEL`) for testing preview models.
- **Agent Engine only supports Python 3.9–3.13**, not 3.14+. `make deploy-ae-global` auto-selects `.venv-deploy` (Python 3.12) or falls back to `python3.12`/`python3.11` — see the `DEPLOY_PYTHON` logic in the Makefile.
- **`BuiltInCodeExecutor` cannot be combined with function-calling tools** in ADK — they're mutually exclusive on the same agent (see comment in `app/agent.py`).
- Deploying to Agent Engine requires granting `roles/storage.objectAdmin` on the GCS bucket to the Reasoning Engine service agent (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) — run `make setup-ae-permissions` or it's handled automatically by `scripts/deploy_ae_inline.py`.
- DB path differs by environment (see `app/config.py`): project root locally, `app/campaigns.db` on Cloud Run, `/tmp/campaigns.db` on Agent Engine (ephemeral, repopulates from mock data on restart).
- Tests run against a **copy** of `campaigns.db`, never the real one — see `tests/conftest.py` fixtures (`test_db`, `shared_test_db`, `fresh_test_db`).
- **The integration eval suite's old vacuity is fixed (workstream 16, 2026-07-23) — the mechanism, refined.** `tests/conftest.py`'s autouse fixture still sets `GOOGLE_CLOUD_PROJECT=test-project` for unit tests (needed, unchanged) and every eval inference under that fake project still 403s — but ADK's `LocalEvalService` itself was never the bug: it correctly records per-case `InferenceStatus.FAILURE` / `final_eval_status=FAILED`. The actual vacuity was in `AgentEvaluator`'s pytest aggregation (`evaluate_eval_set`), which compares only *mean metric scores* and never inspects `final_eval_status` — with an inference failure there are no metric scores to average, so the assert silently passed on zero real LLM calls. `tests/integration/eval_harness.py` (workstream 16) fixes this properly: it drives the same underlying `LocalEvalService` but asserts per-case `final_eval_status` directly (`assert_eval_outcomes`), scores three independent dimensions per case (tools `ANY_ORDER`, trajectory `IN_ORDER`, answer `final_response_match_v2` LLM-judge), isolates each case against a fresh seeded DB copy, and has two owner-approved bounded one-shot retries (answer re-judge; deterministic-dims-only re-inference) — both loudly logged when they fire, never silent. `make test` no longer runs `tests/integration` at all (moved to `make test-live`, alongside the new `tests/live` media/judge tests) — see the "Commands" tier map above. **Cost note (owner, 2026-07-23): accepted — correctness first.** Full `make test-live` is real Vertex/Veo/image-model spend, ~11 minutes; see `SETUP_INSTRUCTIONS.md`'s live-tier section for setup, prerequisites, and a flakiness watchlist. `99-open-questions.md` Q19 records the resolution.
