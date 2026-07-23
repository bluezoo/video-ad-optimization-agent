# Workstream 16: live-api-testing

**Branch:** version_2_live-api-testing (off version_2 @ f8df319)
**Phase doc:** .docs/version2-plan/16-live-api-testing.md
**Binding process law:** the phase doc's "Execution directives (owner, 2026-07-23)" — output-validated coverage of ws01–ws15, 3-dimension evals, agents-cli as eval toolchain, July-2026-current doc sources only, incremental green commits, ask-don't-assume on expected behavior, continuous WORK_LOG.

## Research findings

Full reports in `research/` (committed d5da4a0): `agents-cli-architecture.md`,
`adk-eval-docs-context7.md`, `adk-eval-docs-gdk.md`, `repo-claim-verification.md`.
All 13 concrete phase-doc claims re-verified against current code — **all
CONFIRMED, none stale.** Load-bearing facts:

1. **agents-cli 1.1.0 is the latest** (PyPI checked; `uv tool upgrade` refreshed
   deps only). `agents-cli setup --workspace` installed its 7 ADK skills into
   this branch's `.claude/skills/` (adk-code, deploy, **eval**, observability,
   publish, scaffold, workflow — committed 3fd4879, flag for the gate below).
2. **What agents-cli can create/do (directive 3 report):** core
   `eval generate` (runs the real agent over a dataset, emits Vertex
   EvaluationDataset trace JSON) / `grade` (server-side Vertex eval service;
   writes `results_<ts>.json` + **HTML report** — the human-review artifact) /
   `run` / `compare` / `metric`, plus experimental `dataset synthesize`,
   `analyze`, `optimize` (GEPA), `submit`/`results` (cloud runs). 17 built-in
   LLM-judged metrics with **separate tool-use / trajectory / task-success /
   final-response dimensions** (matches directive 2), judge model fixed for
   built-ins, configurable for custom `LLMMetric` (multimodal-capable per its
   skill) and local `CodeExecutionMetric`.
3. **agents-cli's inference harness cannot run this repo today:**
   `eval generate` requires `agents-cli-manifest.yaml` + `uv sync --dev
   --extra eval` (repo has no manifest/pyproject/uv.lock), has a hard 600s
   whole-dataset timeout (a single Veo job can take ~11 min), and offers no
   DB isolation (would mutate the real `campaigns.db`). **`eval grade` works
   project-free** (`--traces --output --config`) — usable as a grading layer
   over traces we produce ourselves.
4. **Current ADK eval API (July 2026, docs+source):**
   - `tool_trajectory_avg_score` now takes `{threshold, match_type:
     EXACT|IN_ORDER|ANY_ORDER}`; bare-dict `criteria` is **deprecated** in
     favor of `eval_config=EvalConfig`; config file discovery =
     `test_config.json` next to the eval set.
   - New judge-metric family exists: `final_response_match_v2`,
     `rubric_based_{final_response,tool_use,multi_turn_trajectory}_quality_v1`,
     `hallucinations_v1`, `safety_v1` (+ per-case additive rubrics). Must
     verify availability in installed google-adk 2.5.0 before depending on
     each (plan task).
   - **transfer_to_agent is an ordinary `tool_uses` entry**
     (`{"name": "transfer_to_agent", "args": {"agent_name": …}}`) — confirmed
     from a current upstream multi-agent fixture. This is exactly how our
     eval sets must represent coordinator routing.
   - **Vacuity mechanism refined from source:** `LocalEvalService` does NOT
     swallow failures — it marks `InferenceStatus.FAILURE` and
     `final_eval_status=FAILED` per case. The gap is `AgentEvaluator`'s
     pytest aggregation, which only compares mean metric scores (empty when
     all inference failed) and never inspects `final_eval_status`. So the
     vacuity guard should **assert on `final_eval_status`/per-case results**,
     not capture loggers (supersedes the phase doc step-1 sketch — cleaner
     and deterministic). CLAUDE.md's gotcha gets this refinement in the
     docs-cleanup stage (open item 4).
5. **Repo state:** no `tests/integration/conftest.py`, no `test_config.json`,
   no `test-live` target. The 5 eval sets pin direct tool calls with mostly
   empty reference responses. `make test` still includes integration (phase
   doc step 6 moves it out). **Existing `slow`/`veo` tests mock Veo — no
   genuinely-live media test exists anywhere today.** Open item 6's GCS leak
   reproduced live (1 failed, real 403). Judge rubric sources:
   `app/tools/prompt_archetypes.py:16-24` (archetypes),
   `app/tools/prompt_builders.py:32-40` (no-text/audio policy). `make lint`:
   **42 errors, 30 auto-fixable** (ws10 item 4). ws14's two candidate eval
   cases verbatim at `working-docs/14-model-upgrades/WORK_LOG.md:147-151`.
   Worktree: Python 3.14 venv, google-adk 2.5.0, real ADC, `app/.env` copied
   from main checkout (gitignored).

## Implementation approach

### Architecture decision: hybrid (pytest-live harness + agents-cli as grading/authoring layer)

Options considered:

- **A — Pure ADK-native pytest** (phase doc steps 1–2 as written): repair eval
  sets + `test_config.json`, integration conftest with real env, vacuity
  guard, everything runs under `make test-live` via AgentEvaluator. Fully
  fits the repo; but uses agents-cli only as documentation — weak against
  directive 3 ("prefer its native formats/harness wherever they fit").
- **B — Pure agents-cli harness**: adopt `agents-cli-manifest.yaml` + uv,
  drive everything through `eval generate`/`grade`. Rejected: requires a
  parallel uv/pyproject dependency universe the repo deliberately doesn't
  have, hard 600s dataset timeout breaks Veo cases, no DB isolation (real
  `campaigns.db` side effects), no pytest/CI integration for `make test-live`.
- **C — Hybrid (chosen):** pytest owns inference and isolation (integration
  conftest, DB fixtures, per-case timeouts); ADK's own eval stack scores the
  three directive-2 dimensions from `test_config.json`; **agents-cli** is
  used (a) via its `google-agents-cli-eval` skill as the authoring/diagnosis
  methodology (Quality Flywheel: small hand-built cases → run → read report →
  fix the agent, never the thresholds), (b) as a project-free
  `eval grade`/`compare` layer over traces our harness emits — giving the
  owner its HTML review reports and run-over-run comparison, and (c) as the
  template for the media judge's rubric-metric shape. If a stage shows
  `eval grade` adds no value over ADK-native scoring for a given dimension,
  we record that in the WORK_LOG and keep the ADK-native path (directive 3
  says prefer where they FIT).

### The three eval dimensions (directive 2), independently failable

Per eval case, three separate criteria in `test_config.json` (exact criterion
availability verified against google-adk 2.5.0 in an early plan task):

- **(a) proper tool calls:** `tool_trajectory_avg_score` with
  `match_type: ANY_ORDER` over the business tools the case must call.
- **(b) trajectory/routing:** a second, stricter trajectory criterion —
  `IN_ORDER`/`EXACT` including the `transfer_to_agent` entries (and/or
  `rubric_based_multi_turn_trajectory_quality_v1` where exact pinning is too
  brittle) — so wrong routing fails even when the right tools eventually ran.
- **(c) expected answer:** judge-based response scoring
  (`final_response_match_v2` or `rubric_based_final_response_quality_v1`)
  against owner-approved expected answers; plain ROUGE `response_match_score`
  only where a deterministic phrase is genuinely expected. **Expected answers
  come from the owner** (directive 6): for each case we show the real live
  answer and ask what it must contain before pinning.

### Coverage matrix (directive 1) — every ws01–ws15 change, output-validated

| Merged change | Live-tier validation (output, not 200s) |
|---|---|
| ws01/14 model defaults (3.6-flash, Veo 3.1, pro-image) | whole live tier runs on defaults; step-3 no-op re-verification; Q14/Q15 evidence logged |
| ws03/04 metrics glossary + centralized RPI | analytics eval case: RPI/impressions answer checked against deterministic DB ground truth (ws05 data makes expected values computable) |
| ws05 deterministic demo data | ground truth for all answer checks; seeded-state assertions |
| ws06 APP_MODE | live tier pinned demo mode; config smoke stays fast-tier |
| ws07 RPI chart | live chart generation + judge review of the chart image (rubric variant: text EXPECTED here — axes/labels legible, correct creative count) |
| ws08 product schema generalization | eval + media cases across verticals (non-fashion product incl. from-scratch onboarding) |
| ws09 archetype prompts + ad-style policy | media judge rubric: wearable → model wearing garment; non-wearable → product hero, no humans; **no rendered text/badges** anywhere |
| ws10 playout attribution | analytics eval case: attribution answer vs seeded playout data |
| ws11a provider seam | live tier exercises demo provider path; fail-closed connected-mode stays fast-tier |
| ws15 onboarding + local-first storage | from-scratch onboarding live case (create_product → generate_product_image → judge); URL policy assertion (no storage.googleapis.com in any tool response); open items 1–3 |
| ws14 WORK_LOG candidates | two new eval cases: cold-start "create campaign for <product>" must resolve the seeded product, not create_product a duplicate; saved variation JSON free of legacy fields (code-check assertion) |

### Media judge (phase doc step 5)

`tests/live/judge.py`: sends each generated image/video (frames + video file
where the API accepts it) to `gemini-3.6-flash` multimodal with a structured
rubric derived from `prompt_archetypes.py` + `prompt_builders.py`'s no-text
policy; returns per-check JSON verdicts tests assert on. Default severity per
the phase doc's open question 1: **hard-fail** on rendered-text and
wrong-subject/archetype checks, **warn-only** on mood/setting — thresholds
calibrated WITH the owner on real outputs before being pinned (directive 6).
Audio: prompt-policy + judge frame review only; limitation stated in the
rubric (no over-claiming). Optional zero-risk spike: agents-cli
`GECKO_TEXT2VIDEO` on one Veo output, results to WORK_LOG only.

### Staging (directive 5) — each stage lands green and committed

0. **Lint cleanup (ws10 item 4, if approved at gate):** `ruff --fix` (30) +
   manual (12) → `make lint` green repo-wide; own commit(s), zero behavior
   change, PostToolUse hook keeps unit green.
1. **Fix open item 6** (combined-run GCS leak): scrubbed-env final reloads
   and/or session fixture pinning `app.config.GCS_BUCKET`; prove
   `pytest tests` + both split targets green.
2. **Tier split first** (phase doc step 6, pulled early so later stages can't
   hold `make test` hostage): `make test` = unit+e2e only; `make test-live`
   scaffold; `make test-all` = both.
3. **Integration conftest + vacuity guard** (step 1, refined): real env from
   `app/.env` loaded import-order-safely; guard asserts per-case
   `final_eval_status`/inference status so zero-inference ≠ pass. Existing
   eval sets marked expected-fail-as-authored at this stage (they genuinely
   run and genuinely fail — honestly labeled, tier stays green).
4. **Eval-set repair, one set per commit** (step 2): rewrite trajectories to
   the real transfer_to_agent shape, add `test_config.json` with the three
   dimensions, calibrate against live runs; owner consulted per case on
   expected answers (answers logged in WORK_LOG). Includes the two ws14
   candidate cases + deliberate-break check.
5. **Live media tests** (step 4 + items 2–3): two-stage pipeline for one
   wearable + one non-wearable; from-scratch onboarding case; local-first
   storage pinned; URL policy asserted; artifacts under `LOCAL_ASSETS_DIR`.
6. **Judge** (step 5): `tests/live/judge.py` + rubrics; owner calibration
   session with real media; wire into stage-5 tests; RPI-chart judge case.
7. **agents-cli grading layer:** emit traces from the live harness,
   `eval grade`/`compare` where it fits; HTML reports into a gitignored
   artifacts dir; verdict on fit recorded in WORK_LOG.
8. **Docs/targets cleanup** (step 6 + item 4): CLAUDE.md gotcha rewritten
   (refined mechanism + new tier map), `make help`, `reset-db` echo, cost
   profile note, SETUP_INSTRUCTIONS, DEMO_GUIDE "Workstream Testing
   Journeys" entries; Q14/Q15 evidence into WORK_LOG (item 5).
9. **Demo-asset bundle publish/live-verify** (item 1, owner-assisted): we
   build the zip; owner uploads to Drive + provides `DEMO_ASSETS_DRIVE_ID`;
   we verify download→sha256→install→no-op loop live.

Then: demo verification, whole-branch review, PR into version_2.

## Test plan

- **Fast tier:** `make test-unit` + `make test-e2e` green throughout (hook
  enforced); after stage 1, combined `pytest tests` also green.
- **Live tier:** `make test-live` green end-to-end on real Vertex (routing
  evals + media + judge). Deliberate-break checks: (i) corrupt an expected
  tool name → test-live FAILS, revert → passes; (ii) force zero inferences
  (bad project) → vacuity guard FAILS loudly.
- **Demo scenarios:** `docs/demo-scenarios/fashion.md` F1 regression via
  demo-scenario-verifier (agent behavior must be unchanged by test-infra
  work); the live tier itself is this workstream's primary behavioral
  evidence and its full output is attached to WORK_LOG.
- **Lint (if stage 0 approved):** `make lint` exits 0.

## Out of scope

- Phases 11b/12/13 (live BlueZoo/POS adapters, production hardening).
- CI pipeline/GitHub Actions setup — `make test-live` is CI-runnable but
  wiring a runner is not this workstream.
- Adopting uv/pyproject or `agents-cli-manifest.yaml` project conversion.
- Omni Flash revisit (ws14 NO-GO stands); model default changes.
- `README.md` and the client-facing demo script in DEMO_GUIDE.md.
- Cost optimization of the live tier (owner: "dont worry about the cost").

## Flags for the gate

1. **Lint fold-in (owner asked for a proposal):** recommend YES as stage 0 —
   42 errors, 30 auto-fixable, zero behavior change, and this workstream
   already touches test infra repo-wide; a green `make lint` completes the
   "CI-runnable" story. Alternative: leave for a later trivial workstream.
2. **agents-cli skills vendored on this branch** (`.claude/skills/
   google-agents-cli-*`, commit 3fd4879): consistent with the repo's
   skills-travel-with-branch convention and directive 3; ships to the client
   in the PR. Alternative: move to global (`~/.claude`) install and gitignore.
3. **Open item 1 needs an owner action** (Drive upload + link) at stage 9.
