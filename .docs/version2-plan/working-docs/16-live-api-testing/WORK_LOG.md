# Workstream 16 — live-api-testing — WORK_LOG

Append-only running log. Per the owner's execution directive 7 (phase doc
§"Execution directives"), this log is kept **continuously current** — every
step, every fix, and every owner decision/input (verbatim where short) is
recorded at the moment it happens. It is the reference of record; nothing
rests on conversation memory.

## 2026-07-23 — checkpoint 1: kickoff — worktree created

- Branch `version_2_live-api-testing` off `version_2` @ f8df319 (verified:
  merge-base == version_2 HEAD). Worktree `.claude/worktrees/version_2_live-api-testing`.
- STATUS.md row 16 → `kickoff in progress` (main checkout, commit 3fc55d0).
- Phase doc read in full — three layers noted: original steps 1–6 (step 3
  already done in ws14, kept as no-op re-verification), 6 carried-in open
  items, and the **binding** "Execution directives (owner, 2026-07-23)"
  section (coverage bar = output-validated everything; 3-dimension evals;
  agents-cli as the eval-building toolchain; July-2026-current doc sources
  only; incremental commits; ask-don't-assume on expected behavior; this
  running-log discipline).
- Owner kickoff message (2026-07-23, verbatim constraints beyond the doc):
  upgrade agents-cli to latest + `agents-cli setup` + study its eval
  architecture and report what it can create BEFORE any working doc; fetch
  current ADK eval docs via context7 + google-dev-knowledge MCP only; plan
  as small incremental stages each committed when green; at the working-doc
  gate also propose whether the repo-wide lint cleanup (ws10 carried item 4)
  folds in; ws14 WORK_LOG has two candidate eval cases (cold-start duplicate
  create_product; legacy variation fields in saved JSON).
- Next: agents-cli upgrade/setup/study + doc fetch + phase-claim
  re-verification (kickoff research), then working doc.

## 2026-07-23 — kickoff research done (checkpoint 1 amendment)

- **agents-cli:** verified 1.1.0 IS the latest on PyPI (`uv tool upgrade` refreshed
  deps only); `agents-cli setup --workspace --skip-auth --agent claude-code` installed
  7 ADK skills into this worktree's `.claude/skills/` (committed 3fd4879):
  adk-code, deploy, **eval**, observability, publish, scaffold, workflow.
- **Research fan-out (4 parallel agents, ~720k tokens), reports committed under
  `research/`:**
  - `agents-cli-architecture.md` — full eval surface (generate/grade/run/compare/
    metric + experimental dataset synthesize/analyze/optimize/submit/results);
    17 built-in server-side LLM-judged metrics incl. separate tool-use /
    trajectory / task-success / final-response dimensions; **`eval generate`
    cannot run here today** (requires agents-cli-manifest.yaml + uv sync, repo
    has neither; hard 600s whole-dataset timeout would also break Veo cases;
    no DB isolation); **`eval grade` works project-free** (--traces --output
    --config) → hybrid recommended: our pytest live harness emits traces,
    agents-cli grades/compares. Custom LLMMetric (configurable judge model,
    multimodal per its skill's multimodal-eval.md) + CodeExecutionMetric
    available; GECKO_TEXT2IMAGE/TEXT2VIDEO exist but undocumented (spike-only).
  - `adk-eval-docs-context7.md` — current EvalSet/EvalCase schema (.test.json ≡
    .evalset.json); `tool_trajectory_avg_score` now supports
    `{threshold, match_type: EXACT|IN_ORDER|ANY_ORDER}`; `criteria` dict param
    DEPRECATED in favor of `eval_config=EvalConfig`; new judge-metric family
    (final_response_match_v2, rubric_based_{final_response,tool_use,
    multi_turn_trajectory}_quality_v1, hallucinations_v1, safety_v1, …).
    **Vacuity root cause refined from source:** LocalEvalService does NOT
    swallow failures — it sets InferenceStatus.FAILURE and
    final_eval_status=FAILED per case; the gap is AgentEvaluator's pytest
    aggregation, which only compares mean metric scores (empty when all
    inference failed) and never inspects final_eval_status → vacuity guard
    should assert on final_eval_status, not capture loggers (better than the
    phase doc's step-1 sketch). **transfer_to_agent confirmed via current
    upstream fixture as an ordinary tool_uses entry**
    `{"name": "transfer_to_agent", "args": {"agent_name": …}}`.
  - `adk-eval-docs-gdk.md` — adk.dev current: 4 eval run modes (web UI, pytest,
    `adk eval`, new `adk conformance` deterministic replay); 12-criterion table
    (criteria page authoritative; overview list stale); GCP-project-required
    subset (safety_v1, multi_turn_*) — we have ADC; per-case rubrics additive.
  - `repo-claim-verification.md` — **all 13 phase-doc claims CONFIRMED, none
    stale.** Open item 6 leak REPRODUCED live (1 failed, real 403 to
    test-bucket, tests/e2e test_video_review_table). `make lint`: 42 errors,
    30 auto-fixable (ws10 item 4). No tests/integration/conftest.py, no
    test_config.json, no test-live target anywhere. Existing slow/veo tests
    MOCK Veo — no genuinely-live media test exists today. Judge inputs:
    archetypes app/tools/prompt_archetypes.py:16-24, no-text policy
    prompt_builders.py:32-40. ws14 eval candidates verbatim at
    14-model-upgrades/WORK_LOG.md:147-151. reset-db echo says "22 fashion
    products", actual 28. Root conftest: app.config imported line 45 BEFORE
    session env fixture (54-77) — ws15 mechanism confirmed. Worktree .venv
    Python 3.14 + google-adk 2.5.0; app/.env copied from main checkout
    (gitignored).
- Next: working doc draft → owner gate (incl. lint fold-in proposal, agents-cli
  hybrid architecture decision, skills-vendor-on-branch flag).

## 2026-07-23 — checkpoint 2: working doc approved (owner)

Owner gate answers (verbatim):
1. Working doc: "Yes — approved, write the plan" (hybrid pytest+agents-cli
   architecture, 10-stage incremental plan, coverage matrix approved).
2. Lint fold-in (ws10 item 4): "Yes — fold in as stage 0 (Recommended)".
3. agents-cli skills vendor: "Keep on branch (Recommended)" — commit 3fd4879
   stands, ships to client with the PR.
Next: writing-plans → plan.md alongside this doc, then plan-approval gate.

## 2026-07-23 — checkpoint 3: plan approved (owner)

Owner answer (verbatim): "Yes — approved, execute" — plan.md (18 tasks / 10
stages, owner-gate protocol) committed eb86949. Execution via
subagent-driven-development, ultracode workflow loop (implementer → reviewer →
fix cap 2 per task), Tasks 1–5 first (no owner gates); Tasks 6+ pause at each
OWNER GATE per the plan's execution protocol.
Task 1 implemented (commits 9023e93..295fc3e; ruff 42 errors -> 0, make lint green, make test-unit 314 passed/1 skipped, make test-e2e 25 passed/1 skipped, golden prompt tests 4 passed)
Task 1 review: approved (9023e93..41ac6eb)
Task 2 implemented (commits f5c26fc..3aa9c7e; combined tests/unit + tests/e2e 341 passed/2 skipped, was 3 failed/1 skipped before fix; make lint green)
Task 2 review: approved (f5c26fc..4c16ebc)
Task 3 implemented (commits 67da5ee..6921bda; make test = 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e), no integration output; make lint clean; make test-live invokes pytest tests/integration tests/live — tests/live collects 0 items cleanly, tests/integration pre-existing ModuleNotFoundError: pandas/google-adk[eval] unrelated to this task, out of scope, Task 4+ owns it)
Task 3 review: approved (67da5ee..a65f3ad)
Task 4 implemented (commits 12ebc02..1381958; tests/integration/test_live_env_smoke.py 2 passed; make test 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e); combined tests/unit+e2e+smoke 343 passed/2 skipped; make lint clean on touched files)
Task 4 review: approved (12ebc02..f3ed7d3)
Task 5 implemented (commits a02141f..cad2c54; tests/integration 7 passed/5 xfailed in 168.54s — evals genuinely run live (was vacuous ~5s), guard+smoke 7 passed; make test 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e); make lint green; installed google-adk[eval]==2.5.0 extras into worktree .venv — resolves Task 3's carried pandas ModuleNotFoundError)
