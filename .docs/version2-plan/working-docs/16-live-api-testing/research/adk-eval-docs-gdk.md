# ADK Evaluation — Current (July 2026) Documentation Findings

**Source method:** `mcp__google-dev-knowledge__search_documents` + `mcp__google-dev-knowledge__get_documents` (full-document pulls), against the indexed `adk.dev` corpus. No `answer_query` call was needed — search/get already surfaced complete page text for the three most relevant pages, pulled in full below. All facts in this report are sourced from these fetched documents; nothing here relies on pre-2026 training-data memory of ADK eval behavior. Every claim below is tagged with its source URL.

**Pages fetched in full (`get_documents`):**
- `https://adk.dev/evaluate/` (why/how to evaluate, file formats, criteria summary, 4 run methods)
- `https://adk.dev/evaluate/criteria/` (full per-criterion reference: semantics, config, thresholds)
- `https://adk.dev/api-reference/cli/` (full CLI reference: `eval`, `eval_set`, `conformance`, `test`, `migrate`, etc.)

**Page fetched via search snippets only (high-confidence, multiple overlapping chunks retrieved, not a single `get_documents` call):**
- `https://adk.dev/evaluate/user-sim/` (User Simulation / ConversationScenario / personas)

---

## 1. The four documented ways to run ADK evaluation

Per `https://adk.dev/evaluate/` ("How to run evaluation with ADK"), ADK now documents **four** run modes, not three:

1. **Web-based UI** (`adk web`) — interactive: create a session, save it into an eval set via the Eval tab, edit cases, run with slider-configured thresholds for `tool_trajectory_avg_score` / `response_match_score`, inspect results in a Pass/Fail view with Actual-vs-Expected diffs, and use the "Trace" tab (Event / Request / Response / Graph sub-tabs) to inspect execution flow for any session, not just eval runs.
2. **Programmatic (`pytest`)** — via `google.adk.evaluation.agent_evaluator.AgentEvaluator.evaluate(...)`, documented for CI/CD integration.
3. **CLI (`adk eval`)** — "runs the same evaluation that runs on the UI"; intended for build/verification pipelines.
4. **Conformance testing (`adk conformance`)** — **this is new/likely post-dates older ADK eval mental models**: a *deterministic replay-diff* regression harness, separate in kind from the probabilistic trajectory/LLM-judge evaluators used by the other three modes. See §6 — flagged explicitly because it changes what "ADK evaluation" means as an umbrella term.

Source: `https://adk.dev/evaluate/` (chunk "How to run evaluation with ADK").

## 2. File formats

### 2.1 Test files (`*.test.json`) — unit-test-shaped, single session

- One session per file, may have multiple turns.
- Framework only checks the `.test.json` suffix; filename prefix is free.
- Backed by a **formal Pydantic schema**: `EvalSet` (`google/adk-python/src/google/adk/evaluation/eval_set.py`) and `EvalCase` (`.../eval_case.py`).
- Each turn (`conversation[]` entry) has: `invocation_id`, `user_content` (role `user`), `final_response` (reference/golden response, role `model`), `intermediate_data.tool_uses[]` (chronological expected tool calls: `name` + `args`), `intermediate_data.intermediate_responses[]` (see §4 below — **directly relevant to multi-agent trajectory expectations**).
- Each file has a top-level `session_input` (`app_name`, `user_id`, `state`).
- A folder of test files can optionally include a `test_config.json` that specifies evaluation criteria (auto-discovered by folder convention).
- **Migration**: `AgentEvaluator.migrate_eval_data_to_new_schema` converts pre-Pydantic `*.test.json` (+ optional initial-session file) into the new single-file Pydantic format.

Source: `https://adk.dev/evaluate/` §"Evaluate with test files".

### 2.2 Eval set files (`*.evalset.json`) — integration-test-shaped, multi-session

- Same schema (`EvalSet`/`EvalCase`) but can contain **many** `eval_cases`, each a full multi-turn session, each independently identified by `eval_id`.
- Alternative to a fixed conversation: an eval case can instead define a **`ConversationScenario`** for dynamic user-turn simulation (see §5).
- If eval-set data predates the Pydantic schema: ADK-UI-maintained data needs no migration; manually-maintained data used with the CLI is still supported in the old format, with "a migration tool ... in the works" (not yet shipped as of this doc snapshot).

Source: `https://adk.dev/evaluate/` §"Evaluate with an Evalset File".

### 2.3 Config files (`test_config.json` / arbitrary name passed via `--config_file_path`)

- Schema: `{"criteria": {...}}`, matching the `EvalConfig` Pydantic model (`google/adk-python/src/google/adk/evaluation/eval_config.py`).
- **Undocumented-by-name convention nuance found in the docs themselves**: the "Evaluate with test files" section calls this file `test_config.json` and says it is auto-discovered per test folder; the User Simulation walkthrough instead creates a file literally named `eval_config.json` and passes it explicitly via `adk eval --config_file_path=...`. Both are the same `EvalConfig` JSON shape — the filename `test_config.json` only matters for the pytest/folder-auto-discovery convention, not for `adk eval` CLI invocations (which take any path via `--config_file_path`).
- Default criteria when no config is supplied: `tool_trajectory_avg_score: 1.0` (exact match required), `response_match_score: 0.8`. This matches long-standing ADK defaults and is **not** a change.

Source: `https://adk.dev/evaluate/` §"Evaluation criteria"; `https://adk.dev/evaluate/user-sim/` §"Example: Evaluate the hello_world agent with conversation scenarios".

## 3. The full documented metric/criterion set

`https://adk.dev/evaluate/criteria/` is the authoritative current table. **Exact names, semantics, and config shapes as of this fetch:**

| Criterion | Reference-based? | Requires rubrics? | LLM-as-judge? | Supports User Simulation? |
|---|---|---|---|---|
| `tool_trajectory_avg_score` | Yes | No | No | No |
| `response_match_score` | Yes | No | No | No |
| `final_response_match_v2` | Yes | No | Yes | No |
| `rubric_based_final_response_quality_v1` | No | Yes | Yes | Yes |
| `rubric_based_tool_use_quality_v1` | No | Yes | Yes | Yes |
| `rubric_based_multi_turn_trajectory_quality_v1` | No | Yes | Yes | Yes |
| `hallucinations_v1` | No | No | Yes | Yes |
| `safety_v1` | No | No | Yes | Yes |
| `per_turn_user_simulator_quality_v1` | No | No | Yes | Yes |
| `multi_turn_task_success_v1` | No | No | Yes | Yes |
| `multi_turn_trajectory_quality_v1` | No | No | Yes | Yes |
| `multi_turn_tool_use_quality_v1` | No | No | Yes | Yes |

**⚠️ Documented internal inconsistency worth flagging**: the prose summary list on the `/evaluate/` overview page ("Here is a summary of all the available criteria") lists only **11** criteria and **omits `rubric_based_multi_turn_trajectory_quality_v1`**, while the dedicated `/evaluate/criteria/` reference page's table has **12** and includes it with a full worked example. The overview page is stale relative to the criteria reference page as of this fetch — trust `/evaluate/criteria/` as authoritative for the full list.

### Per-criterion detail (all from `https://adk.dev/evaluate/criteria/`, full text pulled)

- **`tool_trajectory_avg_score`** — compares actual vs. expected tool-call list per invocation, with 3 selectable `match_type` values: `EXACT` (default; zero tolerance for extra/missing/reordered calls), `IN_ORDER` (expected calls must appear as a subsequence, other calls may interleave), `ANY_ORDER` (expected calls must all appear, any order, other calls may interleave). Config shape supports either a bare float threshold (implies `EXACT`) or `{"threshold": ..., "match_type": "EXACT"|"IN_ORDER"|"ANY_ORDER"}`. Score = fraction of invocations with a full trajectory match under the chosen match type; 1.0 = perfect. **This explicit, configurable `match_type` (`IN_ORDER`/`ANY_ORDER`) is worth flagging** — if you recall this metric as purely exact-match with no configurability, that's outdated; the current implementation gives 3 modes.
- **`response_match_score`** — ROUGE-1 unigram-overlap score [0,1] vs. reference; default threshold 0.8. Purely lexical, no LLM call.
- **`final_response_match_v2`** — LLM-as-judge semantic equivalence to reference. Judge samples multiple times per invocation (`judge_model_options.num_samples`, e.g. 5) with majority vote → per-invocation binary valid/invalid → case score = fraction valid. Config: `{"threshold": ..., "judge_model_options": {"judge_model": "gemini-flash-latest", "num_samples": 5}}`.
- **`rubric_based_final_response_quality_v1`** — LLM-judge against caller-defined rubrics (list of `{rubric_id, rubric_content: {text_property: "..."}}`), yes/no per rubric per invocation (majority-vote sampled), invocation score = avg over rubrics, case score = avg over invocations. Rubrics can be criterion-level (`EvalConfig.criteria[...].rubrics`, must be non-empty — `RubricBasedEvaluator` asserts this at init) and/or per-case (`EvalCase.rubrics`, filtered to `type == "FINAL_RESPONSE_QUALITY"`, **additive** to criterion-level, never a replacement).
- **`rubric_based_tool_use_quality_v1`** — same rubric mechanics, but judging tool-call correctness/order instead of the final text response. Per-case rubrics filtered to `type == "TOOL_USE_QUALITY"`.
- **`rubric_based_multi_turn_trajectory_quality_v1`** — same rubric mechanics but judges the **entire multi-turn dialogue** (all user/agent/tool turns accumulated) in one shot per rubric; the first N-1 turns are marked `NOT_EVALUATED` and only the final turn carries the aggregate score. Per-case rubrics filtered to `type == "TRAJECTORY_QUALITY"`. Docs explicitly distinguish this from `multi_turn_trajectory_quality_v1` (below): this rubric variant is domain-customizable via yes/no rubrics; the non-rubric variant delegates to the Agent Platform Eval SDK and judges along fixed generic axes.
- **`hallucinations_v1`** — two-step LLM judge: (1) segment final response into sentences, (2) label each sentence `supported`/`unsupported`/`contradictory`/`disputed`/`not_applicable` against context (dev instructions, user prompt, tool defs, tool invocations+results). Score = % `supported`+`not_applicable`. By default only the *final* response is checked; `evaluate_intermediate_nl_responses: true` extends checking to intermediate sub-agent NL responses too. **Explicitly stated as native to ADK** (does not delegate to Vertex Gen AI Eval SDK), unlike `safety_v1` and the `multi_turn_*` (non-rubric) criteria below.
- **`safety_v1`** — harmlessness score; **delegates to the Agent Platform (Vertex Gen AI) Eval SDK**, requiring a real Google Cloud project (`GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`, ADC) — a `GOOGLE_API_KEY`-only (AI Studio) setup is not documented as sufficient for this criterion.
- **`per_turn_user_simulator_quality_v1`** — validates the *user simulator's* fidelity to a `ConversationScenario` (starting-prompt match on turn 1, LLM-judge adherence to `conversation_plan`/`user_persona` on subsequent turns, via `violation_rubrics`). Config supports `stop_signal` (e.g. `"</finished>"`) to tell the judge the conversation is complete.
- **`multi_turn_task_success_v1`** — did the agent achieve the conversation's goal(s), reference-free, ignores *how*. **Delegates to Agent Platform Eval SDK — requires GCP project + location.**
- **`multi_turn_trajectory_quality_v1`** — reference-free judgment of trajectory efficiency/effectiveness/logic across turns. **Delegates to Agent Platform Eval SDK — requires GCP project + location.**
- **`multi_turn_tool_use_quality_v1`** — reference-free judgment of function-call quality/relevance/correctness across turns, no golden trajectory needed. **Delegates to "Vertex AI General AI Eval SDK" — requires GCP project + location.**

### Cross-cutting note on auth/backend (important for a dual-path repo like this one)

The overview page states: "Some criteria (such as response quality, safety, and multi-turn quality) require the Vertex Gen AI Evaluation Service API. To use them, authenticate by setting a `GOOGLE_API_KEY` environment variable, **or** by using Google Cloud project credentials (`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` with Application Default Credentials)." But reading the *per-criterion* pages closely, only `safety_v1`, `multi_turn_task_success_v1`, `multi_turn_trajectory_quality_v1`, and `multi_turn_tool_use_quality_v1` state the Agent-Platform-SDK / GCP-project-and-location requirement explicitly — the rubric-based criteria and `final_response_match_v2`/`hallucinations_v1` only need a `judge_model` (any Gemini model reachable by the existing genai client config) and make no explicit GCP-project claim. **Practical implication for this repo's dual AI-Studio/Vertex config**: the 4 "Agent Platform SDK" criteria likely need `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` set for eval purposes even if the agent itself runs in AI-Studio mode (`GOOGLE_GENAI_USE_VERTEXAI=FALSE`) — this should be verified empirically against the installed ADK version before being relied on, since the two overview-vs-detail statements aren't perfectly reconciled in the docs as fetched.

Source for this whole section: `https://adk.dev/evaluate/criteria/` (full document), cross-referenced against `https://adk.dev/evaluate/` §"Evaluation criteria".

## 4. Multi-agent trajectory / sub-agent transfer — documented schema and semantics

This is the section most directly relevant to ws16 and to the pre-existing repo Gotcha about `transfer_to_agent`-wrapped trajectories.

- `intermediate_data.intermediate_responses` is explicitly documented as: *"These are the natural language responses that the agent (or sub-agents) generates as it moves towards generating a final answer. These natural language responses are usually an artifact of a multi-agent system, where your root agent depends on sub-agents to achieve a goal ... for a developer/owner of the system, [these] are of critical importance, as they give you confidence that the agent went through the right path to generate the final response."* (`https://adk.dev/evaluate/`, "Evaluate with test files" section.)
- The worked multi-session example shows the exact wire shape for a sub-agent contribution:
  ```json
  "intermediate_responses": [
    [
      "data_processing_agent",
      [ { "text": "I have rolled a 10 sided die twice. The first roll is 5 and the second roll is 3.\n" } ]
    ]
  ]
  ```
  i.e. a list of `[sub_agent_name, [Part, ...]]` tuples — **not** part of `tool_uses`. The docs do not show `transfer_to_agent` itself appearing as a named entry in `tool_uses` in this particular sample (the sample's tool calls are `roll_die`/`check_prime`, issued directly against a flat `tool_uses` trajectory alongside a separate `intermediate_responses` entry naming the sub-agent). The docs do **not** explicitly state whether ADK's own `transfer_to_agent` routing function call is itself recorded as a `tool_uses` entry in the flat trajectory for `tool_trajectory_avg_score` purposes — this remains something to confirm against actual eval output/trace for this repo's Coordinator → Campaign/Media/Analytics Agent routing, not something the fetched docs settle definitively.
- `rubric_based_tool_use_quality_v1` and `rubric_based_multi_turn_trajectory_quality_v1` are the two criteria explicitly pitched as suited to multi-agent/multi-step workflows where "multiple tool-use paths could lead to a similar final answer but only one path is considered correct" — i.e., these are the documented fallback when `tool_trajectory_avg_score`'s exact/in-order/any-order matching is too brittle for a sub-agent-routed system (which matches this repo's own `transfer_to_agent`-wrapped-trajectory Gotcha).
- No dedicated "multi-agent" documentation page was found in this pass — sub-agent trajectory guidance is folded into the general test-file/evalset schema docs plus the rubric-based criteria pitch above.

Sources: `https://adk.dev/evaluate/` (test-file schema + worked multi-session example); `https://adk.dev/evaluate/criteria/` (rubric_based_tool_use_quality_v1 / rubric_based_multi_turn_trajectory_quality_v1 "When To Use" sections).

## 5. User simulation (`ConversationScenario`) — dynamic multi-turn eval

Full detail from `https://adk.dev/evaluate/user-sim/` (via overlapping search-chunk retrieval, not `get_documents`):

- **`ConversationScenario`** (schema at `google/adk-python/src/google/adk/evaluation/conversation_scenarios.py`): `starting_prompt` (fixed first user turn), `conversation_plan` (natural-language goal description an LLM user-simulator pursues), optional `user_persona` (either a pre-built id or a fully custom object).
- **Pre-built personas**: `EXPERT`, `NOVICE`, `EVALUATOR` — differ along Advance (detail- vs goal-oriented), Answer (relevant-only vs answer-all), Correct Agent Inaccuracies (yes/no/no), Troubleshoot Agent Errors (once/never/never), Tone (professional/conversational/conversational).
- **Custom personas**: `UserPersona{id, description, behaviors: [{name, description, behavior_instructions[], violation_rubrics[]}]}` — `violation_rubrics` are what `per_turn_user_simulator_quality_v1` uses to catch persona drift.
- **`user_simulator_config`** (top-level `EvalConfig` key): `model` (default `gemini-flash-latest`), `model_configuration` (a `GenerateContentConfig`, e.g. `thinking_config.thinking_budget`), `max_allowed_invocations` (hard cap on user↔agent turns before forced termination — "should be set greater than the longest reasonable interaction"), and `custom_instructions` (Jinja-templated override with `{{ stop_signal }}`, `{{ conversation_plan }}`, `{{ conversation_history }}`, `{{ persona }}` placeholders).
- **Critical compatibility constraint, stated explicitly**: *"criteria which require information on expected agent tool use and/or responses are not supported in combination with User Simulation. Currently, only the `hallucinations_v1` and `safety_v1` criteria support such evals."* — i.e. **you cannot pair `tool_trajectory_avg_score`, `response_match_score`, `final_response_match_v2`, or the rubric-based criteria with dynamically-generated (scenario-driven) user turns**, at least as of this fetch; only `hallucinations_v1`/`safety_v1` are cleared for that combination. (The `criteria/` table's "Supports User Simulation" column marks several more criteria "Yes" — e.g. all the rubric-based ones, `per_turn_user_simulator_quality_v1`, and the `multi_turn_*` family — so read that column as "this criterion is meaningful in a user-sim context" while the `/evaluate/` overview page's prose is the stricter, more operational statement about what's *currently supported*. This is another spot where the two pages don't perfectly agree and should be spot-checked against the installed ADK version's actual behavior rather than assumed.)
- **CLI workflow for adding scenario-based eval cases**: `adk eval_set create` → author a `conversation_scenarios.json` (`{"scenarios": [...]}`) + `session_input.json` → `adk eval_set add_eval_case <agent_path> <eval_set_id> --scenarios_file ... --session_input_file ...` → `adk eval <agent_path> --config_file_path <eval_config.json> <eval_set_id> --print_detailed_results`.
- **Auto-generating scenarios**: `adk eval_set generate_eval_cases <agent_module_file_path> <eval_set_id> --user_simulation_config_file=<config.json>` uses the Vertex Gen AI Eval SDK to synthesize diverse `ConversationScenario`s from a `ConversationGenerationConfig` (`count`, `generation_instruction`, `environment_context`, `model_name`) — **requires GCP project + ADC**, same caveat as the Agent-Platform-SDK-backed criteria above.

## 6. Conformance testing (`adk conformance`) — flagged as a distinct, likely newer capability

This is structurally different from every other eval mode above: it's a **deterministic replay-diff** mechanism, not a probabilistic/LLM-judged one.

- **Directory contract**: `tests/<category>/<test_case_name>/{spec.yaml, generated-recordings.yaml, generated-session.yaml}` (plus `-sse` variants for Server-Sent-Events agents).
- **`spec.yaml`**: declares `name`, `description`, `user_prompts`, `expected_tools`.
- **Baseline capture workflow**: start `adk web -v --extra_plugins=google.adk.cli.plugins.recordings_plugin.RecordingsPlugin <agents_dir>`, then in a second terminal `adk conformance create tests/<category>/<test_name>` (auto-runs the scenario and writes the recording/session baseline files) or `adk conformance record [PATHS...] {none|sse|bidi}` (CLI-reference lists this as a distinct, explicitly work-in-progress subcommand that reads `input.yaml`/`TestCaseInput` specs and emits `test.yaml`).
- **Run modes**: `adk conformance test [PATHS...] [--mode replay|live] [--generate_report] [--report_dir DIR] [--streaming-mode none|sse|bidi]`. `replay` (default) diffs live LLM requests/responses and tool calls/results against the recorded baseline exactly; `live` ("runs evaluation-based verification against active environments") is explicitly called out as **not yet implemented / work in progress** in both `/evaluate/` and the CLI reference.
- **CI/CD framing**: docs explicitly pitch this for PR-gating regression checks — "fails if things don't match ... highly useful for CI/CD pipelines."
- **Why this matters for ws16**: this is a fundamentally different testing philosophy from `AgentEvaluator`/`adk eval` (exact-replay of recorded model+tool I/O vs. score-against-threshold judgment of live model output). If ws16's "live-API test tier" concept maps onto "run real Gemini/Veo calls and check results," `adk conformance`'s replay mode is *not* that — it re-diffs against a **frozen recording**, so a live-API tier built on it would need `--mode=live` (documented as unimplemented) or would need to treat "conformance replay" and "live API eval" as two separate concerns.

Source: `https://adk.dev/evaluate/` §"Evaluate with conformance testing" + §"Run conformance tests"; `https://adk.dev/api-reference/cli/` §`conformance` (both `record` and `test` subcommands, full option/argument list).

## 7. `adk eval` CLI — full reference

From `https://adk.dev/api-reference/cli/` §`eval` (full text):

```
adk eval [OPTIONS] AGENT_MODULE_FILE_PATH [EVAL_SET_FILE_PATH_OR_ID]...
```

- `AGENT_MODULE_FILE_PATH` (required): path to the `__init__.py` containing an `agent` module with `root_agent`.
- `EVAL_SET_FILE_PATH_OR_ID` (0+ args): one or more eval-set file paths **or** eval-set IDs — **mixing file paths and IDs in the same invocation is disallowed**. Sub-selecting specific evals from a set: suffix with `:eval_1,eval_2,eval_3`.
- `--config_file_path <path>`: optional `EvalConfig` JSON.
- `--print_detailed_results` (default `False`): console detail dump.
- `--eval_storage_uri <gs://bucket>`: optional remote storage for eval artifacts.
- `--log_level {DEBUG|INFO|WARNING|ERROR|CRITICAL}`.
- `--enable_features` / `--disable_features <comma-list>`: **feature-flag toggles as CLI flags** (example given: `JSON_SCHEMA_FOR_FUNC_DECL`, `PROGRESSIVE_SSE_STREAMING`) — an alternative to environment variables for experimental-feature gating. This flag pair is worth flagging as a capability that likely postdates older CLI reference snapshots.

**`adk eval_set` subcommand group** (management, not execution):
- `adk eval_set create AGENT_MODULE_FILE_PATH EVAL_SET_ID [--eval_storage_uri] [--log_level]` — creates an empty `EvalSet`.
- `adk eval_set add_eval_case AGENT_MODULE_FILE_PATH EVAL_SET_ID --scenarios_file <path> --session_input_file <path> [...]` — **currently only supports adding a case via a conversation-scenarios file** (i.e., there's no documented CLI path to append a plain fixed-turn eval case; that's presumably still a manual JSON edit or a web-UI "Add current session" action). Idempotent: skips if the generated id already exists.
- `adk eval_set generate_eval_cases AGENT_MODULE_FILE_PATH EVAL_SET_ID --user_simulation_config_file <path> [...]` — Vertex-Gen-AI-Eval-SDK-backed synthetic scenario generation; auto-creates the eval set if missing.

**`adk test`** (distinct, simpler command — easy to conflate with `adk eval`): *"Runs pytest on agent test JSON files under the specified folder."* Usage: `adk test [OPTIONS] [FOLDER]`; single option `--rebuild` ("Rebuild test files by running the real agent with user messages"). This is the CLI's thin wrapper around the pytest/`AgentEvaluator` path for `*.test.json` files, separate from `adk eval`'s evalset-file/eval-set-ID execution path.

**`adk migrate session`**: unrelated to eval-schema migration — migrates a *session database* (SQLAlchemy URL to SQLAlchemy URL) to the latest schema, with an `--allow-unsafe-unpickling` escape hatch for trusted legacy DBs. (Distinct from `AgentEvaluator.migrate_eval_data_to_new_schema`, which migrates eval *test files*, not session databases — don't conflate the two "migrate" concepts.)

Source: `https://adk.dev/api-reference/cli/` (full document; `eval`, `eval_set`, `test`, `migrate` sections quoted verbatim above).

## 8. `pytest` integration — documented pattern

From `https://adk.dev/evaluate/` §"Run tests programmatically" (full text, verbatim):

```python
from google.adk.evaluation.agent_evaluator import AgentEvaluator
import pytest

@pytest.mark.asyncio
async def test_with_single_test_file():
    """Test the agent's basic ability via a session file."""
    await AgentEvaluator.evaluate(
        agent_module="home_automation_agent",
        eval_dataset_file_path_or_dir="tests/integration/fixture/home_automation_agent/simple_test.test.json",
    )
```

Documented facts:
- `AgentEvaluator.evaluate` is **async** (`await`, `pytest.mark.asyncio`).
- Only two kwargs are shown in the canonical example: `agent_module`, `eval_dataset_file_path_or_dir`. The docs do **not** enumerate the full kwarg surface of `AgentEvaluator.evaluate` (e.g., no documented `num_runs`, `initial_session_file`, or inline `eval_config` kwarg was found in this fetch) — the only stated mechanism for supplying criteria in the pytest path is the folder-level `test_config.json` auto-discovery convention, or presumably passing a dir containing one. **This is a documentation gap, not a confirmed absence of such kwargs** — if ws16 needs a specific kwarg (e.g. to point at a config file explicitly from pytest), that should be checked against the installed `google-adk` package's actual `AgentEvaluator.evaluate` signature (source), not assumed from this doc page alone.
- Recommended invocation: `pytest tests/integration/`.
- Initial session state: "If you want to specify the initial session state for your tests, you can do that by storing the session details in a file and passing that to `AgentEvaluator.evaluate` method" — again, no exact kwarg name is given in the fetched text.
- The doc explicitly frames `adk eval`, `pytest`, and web UI as running "the same evaluation" underneath — implying `AgentEvaluator.evaluate` and `adk eval`'s CLI path share one evaluation engine, not divergent implementations.

**Cross-reference to this repo's known Gotcha**: this repo's `CLAUDE.md` already documents that `tests/conftest.py`'s autouse fixture forces `GOOGLE_CLOUD_PROJECT=test-project`, causing every eval inference call to 403, and that ADK's `LocalEvalService` "swallows inference exceptions by design" such that `AgentEvaluator.evaluate_eval_set`'s failure count is computed only from *metric results* (which are empty when inference itself failed) — so pytest reports false "N passed" with zero real LLM calls. **Nothing in the fetched `adk.dev` docs describes this swallowing behavior explicitly** (it's an implementation detail of `LocalEvalService`, not covered on these public doc pages) — this repo's own empirical discovery remains the best source for that specific failure mode; the docs corroborate only the *outer* shape (`AgentEvaluator.evaluate`, async, pytest-integrated) and confirm evaluation genuinely requires live model/tool calls (nothing here describes an offline/mocked eval mode), which is consistent with why a live-API test tier (ws16) is needed at all.

## 9. Evaluation best practices (documented recommendations)

From `https://adk.dev/evaluate/` §"Why evaluate agents" and §"Recommendations on criteria" (full text):

- Rationale: LLM agents are probabilistic, so deterministic pass/fail assertions are "often unsuitable"; evaluation must assess both **trajectory** (steps/tool choices/efficiency) and **final response** (quality/relevance/correctness).
- Prep checklist before automating: define success, identify critical tasks, choose relevant metrics.
- Criterion-selection guidance (verbatim mapping):
  - CI/CD regression gating → `tool_trajectory_avg_score` + `response_match_score` ("fast, predictable, suitable for frequent automated checks").
  - Trusted reference responses, tolerant of phrasing differences → `final_response_match_v2`.
  - No trusted reference, but definable quality attributes → `rubric_based_final_response_quality_v1`.
  - Validate tool-use *reasoning* (not just final correctness) → `rubric_based_tool_use_quality_v1`.
  - Groundedness/anti-hallucination → `hallucinations_v1`.
  - Harm/safety → `safety_v1`.
  - Multi-turn goal completion → `multi_turn_task_success_v1`.
  - Multi-turn trajectory efficiency/logic → `multi_turn_trajectory_quality_v1`.
  - Multi-turn tool-use quality → `multi_turn_tool_use_quality_v1`.
- Explicit User-Simulation compatibility caveat repeated here too (only `hallucinations_v1`/`safety_v1` currently supported in combination with dynamically-simulated user turns).

## 10. Summary of things that could contradict or supersede pre-2026 ADK-eval mental models

Flagging explicitly per the task's instruction — these are the places where this fetch either (a) shows capability that an older mental model might not have, or (b) shows internal doc inconsistency worth not over-trusting at face value:

1. **`adk conformance`** as a fourth, structurally distinct (deterministic replay-diff, not LLM-judged) evaluation mode, with its own directory contract, recording plugin, and CI/CD story — separate from `AgentEvaluator`/`adk eval`/web-UI eval. Confirm before assuming "ADK evaluation" == trajectory+judge scoring only.
2. **`tool_trajectory_avg_score` has 3 selectable match types** (`EXACT` default, `IN_ORDER`, `ANY_ORDER`) via a `match_type` config key — not just binary exact-match.
3. **`rubric_based_*` criteria family** (3 of them: final-response quality, tool-use quality, multi-turn trajectory quality) — a fully custom, non-reference, LLM-judged rubric mechanism with `EvalCase.rubrics` (type-filtered, additive) alongside `EvalConfig`-level rubrics (must be non-empty). This is a materially different mechanism from plain `final_response_match_v2`/`tool_trajectory_avg_score`.
4. **User Simulation / `ConversationScenario`** (dynamic LLM-generated user turns, personas, `adk eval_set generate_eval_cases`) is a documented first-class feature — but is **only compatible with `hallucinations_v1`/`safety_v1`** per the overview page's explicit statement, even though the criteria table marks several more criteria "Supports User Simulation: Yes." Treat the criteria table's "Yes" column as aspirational/contextual and the overview page's prose as the operative constraint, pending empirical confirmation against the installed version.
5. **Doc self-inconsistency**: the `/evaluate/` overview page's bullet-point criteria summary omits `rubric_based_multi_turn_trajectory_quality_v1` (11 vs the criteria page's 12) — don't rely on the overview page alone for the complete metric list.
6. **`--enable_features`/`--disable_features` CLI flags on `adk eval`** (and likely other commands) as an alternative to env-var feature flags — a CLI ergonomics feature that may not have existed in earlier ADK CLI versions.
7. **GCP-project-vs-API-key nuance for LLM-judge criteria**: only `safety_v1` and the three non-rubric `multi_turn_*` criteria are documented as requiring the full Agent-Platform/Vertex-Gen-AI-Eval-SDK path (`GOOGLE_CLOUD_PROJECT`+`GOOGLE_CLOUD_LOCATION`+ADC); `final_response_match_v2`, `hallucinations_v1`, and the rubric-based criteria appear to only need a reachable `judge_model` — this distinction matters for a repo that supports both the AI Studio (`GOOGLE_API_KEY`) and Vertex paths, and should be spot-verified against actual behavior, not taken purely on the overview page's blanket "some criteria... require Vertex Gen AI Evaluation Service API" statement (which conflates both groups).
8. **`AgentEvaluator.evaluate`'s full kwarg surface is not documented on these pages** — only `agent_module` and `eval_dataset_file_path_or_dir` appear in the canonical example. Anything beyond that (explicit config path, num_runs, etc.) needs source-level confirmation from the installed `google-adk` package, not this doc set.

## Sources (all URLs cited above)

- https://adk.dev/evaluate/
- https://adk.dev/evaluate/criteria/
- https://adk.dev/evaluate/user-sim/
- https://adk.dev/api-reference/cli/
- https://github.com/google/adk-python/blob/main/src/google/adk/evaluation/eval_set.py (referenced by the docs as the `EvalSet` schema source)
- https://github.com/google/adk-python/blob/main/src/google/adk/evaluation/eval_case.py (referenced by the docs as the `EvalCase` schema source)
- https://github.com/google/adk-python/blob/main/src/google/adk/evaluation/eval_config.py (referenced by the docs as the `EvalConfig` schema source)
- https://github.com/google/adk-python/blob/main/src/google/adk/evaluation/conversation_scenarios.py (referenced by the docs as the `ConversationScenario` schema source)
- https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/evaluation (referenced for the Vertex Gen AI Evaluation Service API dependency of several criteria)
