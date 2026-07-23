# agents-cli eval toolchain — architecture research (workstream 16 kickoff)

**Date:** 2026-07-22
**Tool version studied:** `google-agents-cli 1.1.0` (installed at `/Users/lavi/.local/share/uv/tools/google-agents-cli/`)
**Sources:** live `--help` output of every eval subcommand; the installed skill suite at `.claude/skills/google-agents-cli-eval/` (SKILL.md + 5 reference files, version 1.1.0); CLI source under `.../site-packages/google/agents/cli/` (esp. `eval/`, `_project.py`) and the vendored Vertex eval SDK (`.../site-packages/vertexai/_genai/`). No memory of older ADK behavior was used; everything below was verified against the installed 1.1.0 code on 2026-07-22.

---

## 1. Command surface (a, e)

Top-level: `agents-cli {create, deploy, eval, info, infra, install, lint, login, playground, publish, run, scaffold, setup, update}` (plus removed `data-ingestion`).

### 1.1 Core eval commands

| Command | Consumes | Produces |
|---|---|---|
| `eval generate` | JSON `EvaluationDataset` of *inference-input* cases (each case: top-level `prompt` Content, OR `agent_data` whose turns end with a user message — "N+1" continuation). Default dataset: `tests/eval/datasets/basic-dataset.json` | *Populated traces* file `artifacts/traces/traces_<YYYYMMDD_HHMMSS>.json` — same `EvaluationDataset` container, now with `agent_data.turns` filled with agent events (`function_call`/`function_response` parts, text), the SDK-introspected `agents` map (tool declarations, sub-agents), and `responses[0].response` set to the final **text** response |
| `eval grade` | Traces file or directory (`--traces`, default `artifacts/traces/*.json`, all files merged) + metric selection (`--metrics name1,name2` or `--config` YAML/JSON; default config `tests/eval/eval_config.yaml`) | `artifacts/grade_results/results_<ts>.json` (full `EvaluationResult` dump + `metadata.dataset` rows) **and** `results_<ts>.html` (browser report via the SDK's `_evals_visualization`), plus a plain-text per-metric summary printed to console (deliberately LLM-parse-friendly, no box drawing) |
| `eval run` | Same flags as generate+grade (`--dataset`, `--output`, `--metrics`, `--config`, `--project`, `--region`) | Chains the two through the default `artifacts/traces/` dir. Thin alias only |
| `eval compare BASELINE CANDIDATE` | Two `results_*.json` files | In-process recursive diff (dotted key paths, numeric deltas like `+0.07`), emitted to stdout via the CLI's `emit()` — no file written, no LLM calls |
| `eval metric list` | — | Table of built-in metric names (see §4) |

### 1.2 Experimental eval commands (e)

| Command | What it does |
|---|---|
| `eval dataset synthesize` | Generates user *scenarios* server-side (Vertex eval service `generate_conversation_scenarios`, reading the agent's instructions + tool declarations), then plays each scenario against the local agent with an ADK `LlmBackedUserSimulator`. Output = graded-ready traces (skip `generate`). Flags: `-n/--count` (default 3), `--instruction`, `--environment-context`, `--model` (scenario-gen model only), `--max-turns` (default 5), `-o`. Each case carries `eval_case_id` (UUID), the generated `user_scenario` `{starting_prompt, conversation_plan}`, and full `agent_data.turns`. Simulator internals are hardcoded (`gemini-2.5-flash` user voice per the skill; only `max_turns` → `LlmBackedUserSimulatorConfig.max_allowed_invocations` is passed through — confirmed in `_synthesize_runner.py`). No seed flag — every run gives fresh scenarios |
| `eval analyze` | LLM-based failure clustering over a `results_*.json` (`--eval-result`, required). Only two metrics supported: `multi_turn_task_success`, `multi_turn_tool_use_quality` (regex-enforced in `cmd_analyze.py`). Output json/html to `artifacts/`. Requires project root (chdir) and GCP project; global-region only |
| `eval optimize` | Runs ADK GEPA prompt optimization ("`adk optimize` under the hood"). Input: `EvaluationDataset` JSON + `--target-metric`, or `tests/eval/optimization_config.json` (`eval_config` = ADK EvalConfig, `train_dataset`, `validation_dataset`, `optimizer_config` = `GEPARootAgentPromptOptimizerConfig`, `log_level`, `print_detailed_results`). It converts the dataset to ADK evalsets and stages temp config under `<agent_dir>/.tmp/`. Optimized prompt appears in command output only. Skill warns: long-running/expensive, run once at the end, never loop |
| `eval submit` | Cloud-side E2E run on the Vertex AI Eval Service: `--dataset` (trace JSON) + `--dest gs://bucket` (required) + metrics/config. With `--resource-name projects/.../reasoningEngines/...` it also runs inference server-side against a deployed Agent Engine (managed generate+grade); without it, managed grade of an existing trace. Returns a run resource name |
| `eval results` | Polls/downloads a submitted run by `--run-id`; writes the same `results_*.{json,html}` artifacts into `artifacts/grade_results/` (or `--output`) |

### 1.3 Adjacent commands

- **`agents-cli run "MESSAGE"`** — one-shot non-interactive agent query. Local mode boots a throwaway ADK SSE server from the project's `agent_directory` (or reuses a `--start-server` background server; 30-min idle shutdown); `--url` + `--mode a2a|adk` queries a deployed agent. `--file` gives multimodal input; `--session-id` continuity; binary artifacts returned by the agent are saved to `.google-agents-cli/artifacts/` and listed in an `Artifacts:` footer. Useful as a live-API smoke primitive independent of the eval pipeline.
- **`agents-cli info [--json]`** — CLI version, install path, installed skills, and project config. Run inside this repo today it prints "No agent project found in the current directory or any parent" (verified).
- **`agents-cli lint`** — runs `uv run ruff check`, `ruff format --check`, `codespell`, `ty` (opt-out), `mypy` (opt-in). uv-project-shaped; overlaps/conflicts with this repo's own `make lint` conventions — not useful here.

---

## 2. File formats and schemas (a, detail)

All four artifact kinds share one container type, `vertexai.types.EvaluationDataset` / `EvaluationResult` (canonical defs: `vertexai/_genai/types/evals.py` + `types/common.py` in google-cloud-aiplatform), but populated fields differ by stage (`eval/_paths.py` documents the stage contract):

- **Stage 1 — inference input** (`tests/eval/datasets/*.json`): `{"eval_cases": [{"eval_case_id", "prompt": Content}]}` or the `agent_data`-continuation shape. `reference` (`ResponseCandidate` wrapper, i.e. `{"response": Content}`) and per-case `rubric_groups` are optional. `role` is `"model"`, never `"assistant"`.
- **Stage 2 — populated traces** (`artifacts/traces/traces_<ts>.json`): `agent_data = {agents: {id: AgentConfig}, turns: [{turn_index, events: [{author: "user"|<agent_id>|"tool", content: Content}]}]}`. Tool activity is `function_call` / `function_response` parts. `eval generate` strips Gemini `thought_signature` fields, rewrites `author: "model"` to the root agent's name, and appends only the *new* agent events to the last turn.
- **Stage 3 — graded results** (`artifacts/grade_results/results_<ts>.json`): `EvaluationResult.model_dump()` with `summary_metrics` (per-metric aggregate), per-case metric results with judge rationales/rubric verdicts, and `metadata.dataset` (extracted rows for the HTML view). The `.html` sibling is the human-review artifact.
- **Eval config** (`tests/eval/eval_config.yaml` or any `--config` YAML/JSON): two keys — `metrics_to_run` (selection list; names resolve built-in first, then `custom_metrics`) and `custom_metrics` (definition pool). `--metrics` on the CLI overrides `metrics_to_run` for that invocation. Custom entry dispatch: `custom_function`/`custom_function_file` present → `CodeExecutionMetric` (Python `def evaluate(instance):` returning score or `{'score','explanation'}`; `execution: local` default = in-process, no GCP; `execution: remote` = Vertex sandbox); otherwise `LLMMetric` (`prompt_template` with `{prompt}`, `{response}`, `{agent_data}`, plus `{reference}`/`{context}` when populated; optional `judge_model`, `judge_model_sampling_count` 1–32, `judge_model_system_instruction`, `judge_model_generation_config`, `rubric_group_name`). `custom_function_file` resolves relative to the config file's directory (verified in `eval_utils._resolve_custom_function_file`) — this is the hook for keeping metrics as real lintable modules.

---

## 3. Intended end-to-end workflow and the human's place (b)

The skill frames it as the **Quality Flywheel** (5 stages, iterate 5–10+ times per case — "this is normal"):

1. **Prepare data** — hand-edit `tests/eval/datasets/*.json` (start with 1–2 cases), or opt-in `eval dataset synthesize` for multi-turn simulated data (skips stage 2).
2. **Run inference** — `eval generate` → traces.
3. **Grade (always)** — `eval grade` → `results_<ts>.{json,html}`.
4. **Analyze failures** — default: human/agent reads the HTML/JSON rubric verdicts against a fix table in SKILL.md; opt-in `eval analyze` for LLM clustering at 10+ failures.
5. **Optimize & code fix** — default: edit prompts/tool descriptions/instructions; opt-in `eval optimize` (GEPA) for prompt-only failures, run once.

Then `eval compare prev.json new.json` after every fix to confirm improvement without regressions. `eval submit`/`results` is the managed cloud path for scale/CI.

**Where the human/owner fits:** the HTML report (`results_<ts>.html`) is the designed review surface; SKILL.md's "Proving Your Work" section demands pasting score tables, before/after comparisons, and a final all-cases-pass `grade` run as the gate before deploy. There is no built-in approval/HITL step in the pipeline itself — review is a convention (read the artifacts, gate on the numbers), which maps cleanly onto this repo's owner-approval checkpoints.

---

## 4. Metrics: what ships, what's LLM-judged, which model (d)

`agents-cli eval metric list` (live output) — 17 built-ins:
`FINAL_RESPONSE_MATCH, FINAL_RESPONSE_QUALITY, FINAL_RESPONSE_REFERENCE_FREE, GECKO_TEXT2IMAGE, GECKO_TEXT2VIDEO, GENERAL_QUALITY, GROUNDING, HALLUCINATION, INSTRUCTION_FOLLOWING, MULTI_TURN_GENERAL_QUALITY, MULTI_TURN_TASK_SUCCESS, MULTI_TURN_TEXT_QUALITY, MULTI_TURN_TOOL_USE_QUALITY, MULTI_TURN_TRAJECTORY_QUALITY, SAFETY, TEXT_QUALITY, TOOL_USE_QUALITY`.

These resolve to Vertex predefined metrics (`SUPPORTED_PREDEFINED_METRICS` in `vertexai/_genai/_evals_constant.py`, versioned ids like `multi_turn_task_success_v1`, `final_response_match_v2`, `gecko_text2image_v1`). **All built-ins are graded server-side by the Vertex AI Eval Service** (`PredefinedMetricHandler`); the judge model for predefined metrics is **server-controlled and NOT configurable** — the SDK comment is explicit: "autorater_config is intentionally not passed for predefined metrics. The server uses its own model configuration." Judge config (`judge_model` etc.) applies only to your own `LLMMetric` custom metrics (docs use `gemini-2.5-flash` / `gemini-flash-latest` as examples). Grading defaults to the `global` eval region regardless of manifest region (`DEFAULT_EVAL_REGION = "global"` in `eval_utils.py`); `--region` overrides, unsupported regions get a 400.

**Separate dimensions — yes.** The three axes phase 16 cares about are covered by distinct metrics:

- **Tool calls made:** `tool_use_quality` (single-turn) / `multi_turn_tool_use_quality` — technical + semantic correctness of tool selection, parameters, sequence; adaptive rubric, no hand-authored expected trajectory needed.
- **Trajectory/routing correctness:** `multi_turn_trajectory_quality` — sequential logic, efficiency, error recovery; plus `multi_turn_task_success` as the goal-level catch-all.
- **Final-answer quality:** `final_response_quality` (reference-free, adaptive rubric), `final_response_match` (needs golden `reference`), `final_response_reference_free` (needs custom rubrics), plus `hallucination` (claims vs tool output) and `safety`.

The skill explicitly recommends adaptive-rubric tool metrics **instead of hardcoded expected tool sequences** ("strict sequence matching is fragile") — directly relevant to why this repo's pre-existing ADK eval sets fail as authored (they expect direct tool calls vs actual `transfer_to_agent`-wrapped trajectories, see Q19). The LLM-judge metrics sidestep that class of failure.

**Multimodal surprise:** `GECKO_TEXT2IMAGE` / `GECKO_TEXT2VIDEO` are shipped predefined server-side metrics for text→image / text→video alignment — nominally exactly what judging Veo ad output against its prompt needs. Caveats: the eval skill's own `multimodal-eval.md` doesn't mention them (it prescribes custom vision-judge `LLMMetric`s instead), they're single-turn `prompt`+`responses`-shaped, and `eval generate` never puts media parts into `responses` (see §6/§7) — so using them requires hand-authored or post-processed cases pointing at `file_data` GCS URIs. Treat as promising-but-unproven for this repo; needs a spike.

Built-in-tools caveat (`builtin-tools-eval.md`): model-internal tools (`google_search`, `BuiltInCodeExecutor`, `VertexAiSearchTool`, `url_context`) never appear as `function_call` events, so tool-use metrics can't see them (and an agent whose *only* tool is google_search reliably fails `multi_turn_tool_use_quality` with `UNEXPECTED_TOOL_CALL`). This repo's agents use function tools, so mostly moot — but relevant if a future agent adds grounding.

---

## 5. Pointing at an existing ADK app (c)

**Project discovery** (`_project.py`): every agent-touching command walks up from cwd looking for **`agents-cli-manifest.yaml`**; legacy fallback is a `pyproject.toml` with a `[tool.agents-cli]` table (emits an "upgrade" warning). No manifest and no such pyproject → `find_project_root()` returns `None` and `eval generate` / `synthesize` / `optimize` / `analyze` / `run` refuse to start. Manifest keys → `ProjectConfig`: `name`, **`agent_directory` (default `"app"`)**, `region` (default `us-east1`, *not* used by eval grading), `base_template`, `acli_version` (version-mismatch warnings), `language`, `create_params.{deployment_target, is_a2a, session_type, cicd_runner, agent_guidance_filename}`.

**How the agent is loaded** (`eval/_inference_runner.py`, staged into `<project>/.agents-cli-scripts/` and executed via `uv run python` inside the *user's* venv): it uses ADK's own `AgentLoader(agents_dir=<parent of agent_directory>)` and `load_agent(<dirname>)` — i.e. exactly the `adk web`-style convention this repo already satisfies (`app/agent.py` exposing `root_agent`; ADK `App` wrappers are unwrapped via `App.root_agent`). Fresh agent load per eval case (cache purged) with a new `InMemorySessionService` session each time — so no cross-case or cross-session state; DB and other side effects are the real ones, not test-fixture copies.

**Env/config:** the runner loads the nearest `.env` at/above the agent dir — the **whole file** (`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT/LOCATION`, `GEMINI_API_KEY`, app vars), pre-existing OS env winning — before importing the agent module. This matches this repo's `app/.env` convention, including the `GOOGLE_CLOUD_LOCATION=global` requirement for Gemini 3.x. `eval grade` likewise loads the nearest `.env` (for local model-calling metrics) and resolves GCP project as `--project` > `GOOGLE_CLOUD_PROJECT` > ADC.

**Hard dependency on uv:** before inference, `eval generate` runs `uv sync --dev --extra eval` at the project root — expecting a uv-managed `pyproject.toml` with an `eval` optional-dependency group (the scaffold template defines it as `google-adk[eval]>=2.0.0,<3.0.0` + `google-cloud-aiplatform[evaluation]>=1.156.0`; this worktree's `.venv` already has google-adk 2.5.0 and aiplatform 1.162.0, so the *packages* are satisfiable). The subprocess has a **hard 600 s timeout for the entire dataset's inference**.

**What this repo is missing today (verified):** no `agents-cli-manifest.yaml`, no `pyproject.toml`, no `uv.lock` — the repo is Makefile + `app/requirements.txt` + `.venv`. `agents-cli info` confirms: "No agent project found." So adopting the local generate/synthesize path needs, at minimum: (1) an `agents-cli-manifest.yaml` with `agent_directory: app`, and (2) a uv-compatible `pyproject.toml` declaring an `eval` extra (plus accepting `uv sync` creating/managing an env). Alternative: skip `eval generate` entirely — **`eval grade` can run project-free** when `--traces`, `--output`, **and** `--config` are all supplied explicitly (code checks all three, despite the error text saying "both --traces and --output"), which means this repo could produce traces its own way (pytest harness around the ADK Runner) and still use agents-cli only as the grading/compare front-end.

---

## 6. What the skills tell a coding agent to do (f)

`google-agents-cli-eval` SKILL.md (the owner's "ADK development skill" for eval; v1.1.0, matching the CLI):

**When creating evals:** start from 1–2 hand-written single-turn cases in `tests/eval/datasets/`; use `synthesize` only when fixed prompts are impractical, and use hand-recorded `agent_data.turns` for deterministic regression coverage (synthesize has no seed). Pick metrics from a goal table (task success / trajectory / tool use / response quality / hallucination / safety), write custom `LLMMetric` or `CodeExecutionMetric` when no built-in fits, prefer YAML config. Prefer rubric-based tool metrics over hardcoded sequences. Only expand case count after existing cases pass.

**When diagnosing failures:** read the latest `results_<ts>.html`/`.json` rubric verdicts; a metric→fix mapping table (e.g. `multi_turn_tool_use_quality` low → fix tool descriptions/parameter docstrings/selection instructions; `hallucination` low → tighten grounding instructions and verify the tool actually returned the claimed data). Rerun generate+grade, then `compare` prev vs new. Explicit anti-shortcut table: never lower thresholds, never delete flaky cases (fix nondeterminism with `temperature=0`/rubrics instead), never fix only the dataset. "Proving Your Work": paste score output, show before/after, final full pass before deploy.

**Notable gotchas it documents:** ADK `App` name must match the directory name; **cross-session memory cannot be eval-tested** (fresh in-memory session per case — "validate cross-session continuity with pytest integration tests instead", i.e. the skill itself delegates that to pytest); eval-region rules (grade/submit default `global`, don't inherit manifest region; analyze is global-only; generate/synthesize honor the agent's `.env`); thinking models may skip tools (`tool_config mode="ANY"`); add mock modes for external APIs so evals run without credentials; the LLM judge ignores image/audio because `get_text_from_content()` skips non-text parts → custom vision-judge metric required.

`google-agents-cli-adk-code` SKILL.md (skimmed): quick ADK API reference gated on a scaffolded project existing ("Do NOT write agent code until a project is scaffolded" — a convention this repo ignores by design); defers deep API questions to `references/adk-python.md`, `adk.dev/llms.txt`, and the installed package source. Eval-relevant only via its cross-link to the eval skill.

---

## 7. Honest gaps vs phase-16 needs (g)

1. **No pytest integration.** The toolchain is CLI-first; artifacts are JSON/HTML files, not test outcomes. Nothing marks pass/fail thresholds machine-readably for CI gating out of the box — a phase-16 tier would need a thin wrapper (invoke CLI or call `vertexai Client.evals.evaluate` directly, assert on `summary_metrics`) or keep pytest and agents-cli as parallel tracks. Notably the skill itself punts cross-session behavior to "pytest integration tests".
2. **Repo shape mismatch.** `eval generate`/`synthesize`/`optimize`/`analyze`/`run` all require `agents-cli-manifest.yaml` (or legacy pyproject) and `eval generate` shells out to `uv sync --dev --extra eval` + `uv run` — this repo has none of pyproject/uv.lock/manifest. Either adopt those files (client-visible footprint in the repo root) or restrict usage to the project-free `eval grade --traces --output --config` path with self-produced traces.
3. **600 s hard timeout on the whole `eval generate` inference subprocess** (`_INFERENCE_TIMEOUT` in `cmd_generate.py`). Any eval case that triggers real Veo 3.1 generation (minutes/video) or several long tool chains can blow the budget for the entire dataset. Not configurable by flag.
4. **No test isolation for side effects.** Inference runs the real agent from the project root: real `campaigns.db` writes, real GCS uploads, real HITL review rows — unlike this repo's `tests/conftest.py` DB-copy fixtures. Demo-mode (`APP_MODE=demo`) or env-injected DB redirection would be needed per run.
5. **Multimodal judging is not first-class for agent traces.** Built-in adaptive metrics judge text parts only; `eval generate` copies only *text* into `responses` (media `inline_data`/`file_data` parts are dropped from `{response}`). Judging generated images/videos requires hand-authored cases or post-processing traces to insert `file_data` URIs, then either a custom vision-judge `LLMMetric` (skill's prescribed pattern) or the unproven `gecko_text2image`/`gecko_text2video` predefined metrics. For this repo (Veo videos land in GCS), a trace post-processor that lifts the video GCS URI into `responses` is a plausible bridge — but it's custom work agents-cli doesn't do.
6. **Judge model for built-ins is server-controlled** — no way to pin/version the judge for predefined metrics (reproducibility across months is at the eval service's mercy). Only custom `LLMMetric`s let you pin `judge_model` + sampling + temperature.
7. **GCP coupling for grading.** All built-in metrics require the Vertex eval service (project + `global` region reachable); fully offline grading exists only via local `custom_function` metrics (which may themselves call an LLM). AI-Studio-only environments can generate traces but not use managed metrics.
8. **Nondeterminism.** `synthesize` has no seed; LLM-judge scores fluctuate (mitigation: `judge_model_sampling_count`, temperature 0 on the agent). `eval compare` diffs numbers but has no noise-band/threshold concept.
9. **`eval analyze` covers only 2 metrics** (`multi_turn_task_success`, `multi_turn_tool_use_quality`) and is global-region-only.
10. **Session/memory limits.** One fresh in-memory session per case; can't exercise Memory Bank / cross-session flows, `--session-id`-style continuity, or this repo's HITL review flow that spans conversations.
11. **Version tension to watch:** scaffold's eval extra pins `google-adk[eval]>=2.0.0,<3.0.0`; this worktree already runs google-adk 2.5.0 + aiplatform 1.162.0, so compatible today — but `app/requirements.txt` says `google-adk>=1.21.0`, so the floor should be raised if agents-cli eval becomes a supported path.
12. **Known SDK bug worked around, not fixed:** both runners monkey-patch `AgentConfig._get_tool_declarations_from_agent` to survive ADK toolsets / tool-less workflow agents (googleapis/python-aiplatform#6865) — this repo's `SequentialAgent`-style constructs and any MCP toolsets are exactly the shapes that crash the unpatched SDK; the patch skips their declarations in eval *metadata* (calls still appear in traces).

## 8. Bottom line for phase 16

agents-cli 1.1.0 gives phase 16 a real, current, LLM-judged grading stack with exactly the three separated dimensions we want (tool use, trajectory, final response), plus compare/analyze/optimize tooling and a documented methodology skill. What it does **not** give: pytest/CI integration, side-effect isolation, first-class media judging of generated Veo/image artifacts, a configurable/pinnable judge for built-ins, or tolerance for this repo's non-uv layout. The lowest-friction adoption path is a hybrid: keep trace *generation* in our own pytest/live-API harness (full control of DB fixtures, timeouts, media capture), emit Stage-2 `EvaluationDataset` traces, and use `agents-cli eval grade/compare` (project-free mode) plus custom vision-judge `LLMMetric`s — with a spike on the GECKO metrics — as the grading layer. Full-pipeline adoption (`generate`/`run`) requires adding manifest + uv pyproject and accepting the 600 s inference budget.
