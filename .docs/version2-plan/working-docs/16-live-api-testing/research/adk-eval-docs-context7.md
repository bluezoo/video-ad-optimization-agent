# ADK Evaluation — Current (July 2026) Documentation Research

**Purpose:** kickoff research for workstream 16 (live-API test tier). Answers: what does the eval-set file format, `AgentEvaluator` API, and multi-agent trajectory matching actually look like *right now* upstream, and how does that compare to this repo's existing eval sets (written ~May 2026, which pin direct tool calls)?

**Binding constraint honored:** every claim below is sourced from a fetched doc/source snippet quoted verbatim, not from model memory. Where memory and fetched docs would have disagreed, the docs are what's reported.

## Sources and attribution

| # | Tool | Query / target | Source URL |
|---|------|-----------------|------------|
| 1 | `mcp__context7__resolve-library-id` | "Google Agent Development Kit (ADK) Python" | context7 registry |
| 2 | `mcp__context7__query-docs` (call 1/3) | eval set / criteria schema | `/google/adk-docs` → `docs/evaluate/criteria.md` |
| 3 | `mcp__context7__query-docs` (call 2/3) | `AgentEvaluator`, CLI, pytest | `/google/adk-docs` → `docs/evaluate/index.md`, `docs/api-reference/python/genindex.html`, `docs/api-reference/cli/index.html` |
| 4 | `mcp__context7__query-docs` (call 3/3) | `.evalset.json` schema, `final_response_match_v2`, multi-agent transfer | `/google/adk-docs` → `docs/optimize/index.md`, `docs/evaluate/criteria.md`, `docs/agents/custom-agents.md` |
| 5 | `WebFetch` (supplemental, not counted against the 3-call context7 cap) | full page text | `raw.githubusercontent.com/google/adk-docs/main/docs/evaluate/criteria.md` |
| 6 | `WebFetch` (supplemental) | full page text | `raw.githubusercontent.com/google/adk-docs/main/docs/evaluate/index.md` |
| 7 | `WebFetch` (supplemental) | source code | `raw.githubusercontent.com/google/adk-python/main/src/google/adk/evaluation/agent_evaluator.py` |
| 8 | `WebFetch` (supplemental) | source code | `raw.githubusercontent.com/google/adk-python/main/src/google/adk/evaluation/local_eval_service.py` |
| 9 | `mcp__github__search_code` + `mcp__github__get_file_contents` (supplemental) | real multi-agent eval fixture | `google/adk-python` @ `tests/integration/fixture/trip_planner_agent/trip_inquiry_multi_turn.test.json` |

**Resolved context7 library ID used:** `/google/adk-docs` (chosen over `/google/adk-python`, `/websites/adk_dev_api-reference_python`, and the two `llmstxt` mirrors — `adk-docs` had the freshest, highest-snippet-count coverage of `docs/evaluate/*`, which is the ground truth for the file-format/CLI/criteria docs; source code claims were cross-checked directly against `google/adk-python` `main` via WebFetch/GitHub, not just docs prose).

Other library-ID candidates seen during resolution (not used, listed for provenance): `/google/adk-python` (v1.0.0 … v2.0.0a1, 1642 snippets), `/llmstxt/raw_githubusercontent_google_adk-python_...` (1 snippet), `/websites/adk_dev_api-reference_python` (2119 snippets, Medium reputation), `/llmstxt/adk_dev_llms_txt` (4778 snippets, Medium reputation).

---

## 1. Eval set file format

### 1.1 `.test.json` vs `.evalset.json`

Both share **identical schema** (`EvalSet` → list of `EvalCase`). The suffix is purely a convention for how `AgentEvaluator.evaluate()` discovers files:

- `.test.json`: one session per file, meant for fast unit-style pytest checks; `AgentEvaluator.evaluate(eval_dataset_file_path_or_dir=...)` recursively scans a directory for files with this suffix.
- `.evalset.json`: can hold **multiple** `eval_cases` (multiple sessions), meant for "integration tests" that simulate longer/complex multi-turn conversations, run less frequently. Used directly with the `adk eval` CLI or `evaluate_eval_set()`.

Verbatim (docs/evaluate/index.md, via context7 + WebFetch):

> "Evalsets can contain multiple, potentially lengthy sessions, making them ideal for simulating complex, multi-turn conversations. Due to their ability to represent complex sessions, evalsets are well-suited for integration tests, which are typically run less frequently than unit tests."

### 1.2 Top-level `EvalSet` JSON shape (verbatim, from `docs/optimize/index.md` via context7, and confirmed byte-for-byte against a real upstream fixture — see §3.3)

```json
{
  "eval_set_id": "train_eval_set",
  "name": "train_eval_set",
  "eval_cases": [
    {
      "eval_id": "simple",
      "conversation": [
        {
          "invocation_id": "inv1",
          "user_content": {
            "parts": [ {"text": "Is 7 prime?"} ],
            "role": "user"
          },
          "final_response": {
            "parts": [ {"text": "7 is a prime number."} ],
            "role": "model"
          }
        }
      ],
      "session_input": {
        "app_name": "hello_world",
        "user_id": "user"
      }
    }
  ]
}
```

Real upstream fixtures (`google/adk-python` `main`, e.g. `tests/integration/fixture/trip_planner_agent/trip_inquiry_multi_turn.test.json`) additionally carry: top-level `description` (nullable) and `creation_timestamp` on the `EvalSet`; per-`EvalCase` `creation_timestamp`; and per-`Invocation` an `intermediate_data` block plus `creation_timestamp`. `user_content`/`final_response` `Content.parts[]` entries are full `Part` objects (every field present, most `null`: `video_metadata`, `thought`, `inline_data`, `file_data`, `thought_signature`, `code_execution_result`, `executable_code`, `function_call`, `function_response`, `text`) — i.e. these are serialized `google.genai.types.Content`/`Part`, not a hand-rolled minimal schema.

### 1.3 `EvalCase` / `Invocation` fields (as documented + confirmed from source fixture)

Per-`EvalCase`:
- `eval_id` (string)
- `conversation`: list of `Invocation`
- `session_input`: `{"app_name": ..., "user_id": ..., "state": {...}}` (`state` optional, used to seed session state needed by the eval, e.g. the trip-planner fixture seeds `origin`, `interests`, `range`, `cities`)
- `rubrics` (optional, new — see §1.4): list attached at the case level

Per-`Invocation` (a single turn):
- `invocation_id` (string)
- `user_content`: `Content` (role `"user"`)
- `final_response`: `Content` (role `"model"`) — the expected/reference final response text used by `response_match_score` / `final_response_match_v2`
- `intermediate_data`:
  - `tool_uses`: ordered list of tool calls the agent is expected to have made during this invocation. Each entry: `{"id": <str|null>, "args": {...}, "name": "<tool_or_transfer_name>"}`
  - `intermediate_responses`: list of natural-language sub-agent responses (see §3 — this is the field the docs single out as "usually an artifact of a multi-agent system").
- `creation_timestamp` (float, in real fixtures)

### 1.4 `test_config.json` / `EvalConfig` criteria schema

Default filename `AgentEvaluator.evaluate()`/CLI looks for: **`test_config.json`** (confirmed directly from `agent_evaluator.py` source — method `find_config_for_test_file()`). If no config file is found, `docs/evaluate/index.md` documents the fallback defaults as: **exact-match tool trajectory** and **0.8 ROUGE-1** response-match threshold. (Caveat: I could not get the WebFetch pass over `agent_evaluator.py` to show the literal default-constant assignment in code — it found the *lookup* method but not the exact default values inline; treat "1.0 / EXACT" + "0.8 ROUGE-1" as docs-stated defaults, source-corroborated only indirectly.)

Top-level shape:
```json
{
  "criteria": {
    "<metric_name>": <threshold_float> | <criterion_object>
  }
}
```

**Simple (float) form** — implies default match/behavior for that metric:
```json
{ "criteria": { "tool_trajectory_avg_score": 1.0 } }
```
```json
{ "criteria": { "response_match_score": 0.8 } }
```

**`tool_trajectory_avg_score`, object form with explicit `match_type`** (this is the mechanism that answers the multi-agent question in §3):
```json
{
  "criteria": {
    "tool_trajectory_avg_score": {
      "threshold": 1.0,
      "match_type": "EXACT"
    }
  }
}
```
Three `match_type` values, verbatim from `docs/evaluate/criteria.md`:
- `"EXACT"` — default when only a float threshold is given. Full trajectory must match exactly (order + content).
- `"IN_ORDER"` — expected tool calls must appear in order but other calls are permitted in between.
- `"ANY_ORDER"` — expected tool calls must all be present, order doesn't matter, other calls permitted in between.

Scoring mechanics (verbatim, `criteria.md`):
> "For each invocation, this criterion compares the list of tool calls produced by the agent against the list of expected tool calls using one of three match types. If the tool calls match, a score of 1.0 is awarded, otherwise the score is 0.0. The final value is the average of these scores across all invocations in the eval case."

**`response_match_score`** — ROUGE-1 based text-similarity threshold (float 0.0–1.0):
```json
{ "criteria": { "response_match_score": 0.8 } }
```

**`final_response_match_v2`** — LLM-as-judge, binary valid/invalid with majority vote over N samples (this is the "newer" semantic-match criterion the task asked about):
```json
{
  "criteria": {
    "final_response_match_v2": {
      "threshold": 0.8,
      "judge_model_options": {
        "judge_model": "gemini-flash-latest",
        "num_samples": 5
      }
    }
  }
}
```
Verbatim mechanics:
> "The 'final_response_match_v2' criterion uses an LLM to rate the agent's response as 'valid' or 'invalid' compared to a reference. For robustness, this process is repeated multiple times (configurable via 'num_samples'), with a majority vote determining the invocation's score (1.0 for valid, 0.0 for invalid). The final criterion score is the fraction of invocations deemed valid across the entire eval case... configured using 'LlmAsAJudgeCriterion' to set the threshold, judge model, and number of samples."

**Rubric-based criteria — this is new/notable relative to older ADK and directly relevant to workstream 16.** Full family found on `docs/evaluate/criteria.md` (via supplemental WebFetch, since context7's 3-call budget was already spent by this point):

- `rubric_based_final_response_quality_v1` — rubric list scored against final response text.
- `rubric_based_tool_use_quality_v1` — rubric list scored against the tool-call trajectory (this is a judge-model alternative to strict `tool_trajectory_avg_score` matching — directly useful for multi-agent trajectories that are semantically-but-not-literally correct).
- `rubric_based_multi_turn_trajectory_quality_v1` — rubric list scored across a whole multi-turn conversation.
- `hallucinations_v1` — LLM-judged hallucination score, with an `evaluate_intermediate_nl_responses: true/false` flag (i.e. it can also judge the `intermediate_responses` sub-agent NL outputs, not just the final response).
- `safety_v1` — simple float threshold, e.g. `{"criteria": {"safety_v1": 0.8}}`.
- `per_turn_user_simulator_quality_v1` — has a `"stop_signal"` string field (e.g. `"</finished>"`), implying this ties into an LLM-simulated-user eval mode.
- `multi_turn_task_success_v1`, `multi_turn_trajectory_quality_v1`, `multi_turn_tool_use_quality_v1` — simple float-threshold multi-turn variants.

All rubric-based criteria share this shape:
```json
{
  "criteria": {
    "rubric_based_tool_use_quality_v1": {
      "threshold": 1.0,
      "judge_model_options": {
        "judge_model": "gemini-flash-latest",
        "num_samples": 5
      },
      "rubrics": [
        {
          "rubric_id": "geocoding_called",
          "rubric_content": {
            "text_property": "The agent calls the GeoCoding tool before calling the GetWeather tool."
          }
        },
        {
          "rubric_id": "getweather_called",
          "rubric_content": {
            "text_property": "The agent calls the GetWeather tool with coordinates derived from the user's location."
          }
        }
      ]
    }
  }
}
```

Rubrics can also be attached **per-`EvalCase`** (not just globally in `test_config.json`), and only ones typed `TRAJECTORY_QUALITY` get merged in:
```json
{
  "eval_id": "case_01",
  "conversation": [ "..." ],
  "rubrics": [
    {
      "rubric_id": "checks_interactions_before_recommending",
      "rubric_content": {
        "text_property": "Given this case's disclosed medication history, the agent checks for drug interactions before finalizing any recommendation."
      },
      "type": "TRAJECTORY_QUALITY"
    }
  ]
}
```

**Implication for this repo's `tool_use_quality`/`rubric_based_tool_use_quality_v1`-style needs (multi-agent, judge-based, less brittle than exact trajectory matching):** these rubric criteria are the direct current-ADK answer to "how do I evaluate a Coordinator→sub-agent handoff without pinning the exact `transfer_to_agent` sequence" — see §3.

---

## 2. Programmatic evaluation: `AgentEvaluator`, `LocalEvalService`, CLI

### 2.1 `AgentEvaluator.evaluate()` — exact current signature (from `agent_evaluator.py`, `google/adk-python` `main`)

```python
@staticmethod
async def evaluate(
    agent_module: str,
    eval_dataset_file_path_or_dir: str,
    num_runs: int = NUM_RUNS,
    agent_name: Optional[str] = None,
    initial_session_file: Optional[str] = None,
    print_detailed_results: bool = True,
) -> None:
  """Evaluates an Agent given eval data.

  Args:
    agent_module: The path to python module that contains the definition of
      the agent. There is convention in place here, where the code is going to
      look for 'root_agent' or 'get_agent_async' in the loaded module.
    eval_dataset_file_path_or_dir: The eval data set. This can be either a
      string representing full path to the file containing eval dataset, or a
      directory that is recursively explored for all files that have a
      `.test.json` suffix.
    num_runs: Number of times all entries in the eval dataset should be
      assessed.
    agent_name: The name of the agent.
    initial_session_file: File that contains initial session state that is
      needed by all the evals in the eval dataset.
    print_detailed_results: Whether to print detailed results for each metric
      evaluation.
  """
```

### 2.2 `AgentEvaluator.evaluate_eval_set()` — exact current signature

```python
@staticmethod
async def evaluate_eval_set(
    agent_module: str,
    eval_set: EvalSet,
    criteria: Optional[dict[str, float]] = None,
    eval_config: Optional[EvalConfig] = None,
    num_runs: int = NUM_RUNS,
    agent_name: Optional[str] = None,
    print_detailed_results: bool = True,
) -> None:
  """Evaluates an agent using the given EvalSet.

  Args:
    agent_module: ...
    eval_set: The eval set.
    criteria: Evaluation criteria, a dictionary of metric names to their
      respective thresholds. This field is deprecated.
    eval_config: The evaluation config.
    num_runs: Number of times all entries in the eval dataset should be
      assessed.
    agent_name: The name of the agent, if trying to evaluate something other
      than root agent. If left empty or none, then root agent is evaluated.
    print_detailed_results: Whether to print detailed results for each metric
      evaluation.
  """
```

**Change note:** `criteria: Optional[dict[str, float]]` is explicitly marked **deprecated** in the current docstring in favor of `eval_config: Optional[EvalConfig]`. Any repo code/plan that still constructs a raw `{"tool_trajectory_avg_score": 1.0, ...}` dict and passes it as `criteria=` is using the deprecated path — should migrate to building an `EvalConfig` (which is what accepts the richer `match_type` / rubric / judge-model shapes documented in §1.4).

### 2.3 How inference errors are surfaced — CONFIRMED FROM SOURCE, refines/updates the repo's existing gotcha

Fetched directly from `local_eval_service.py` (`google/adk-python` `main`):

```python
try:
  with client_label_context(EVAL_CLIENT_LABEL):
    if use_live:
      inferences = await EvaluationGenerator._generate_inferences_from_root_agent_live(
          root_agent=root_agent, ...)
    else:
      inferences = await EvaluationGenerator._generate_inferences_from_root_agent(
          root_agent=root_agent, ...)
  inference_result.inferences = inferences
  inference_result.status = InferenceStatus.SUCCESS
  return inference_result
except Exception as e:
  logger.error(
      "Inference failed for eval case `%s` with error %s.",
      eval_case.eval_id,
      e,
      exc_info=True,
  )
  inference_result.status = InferenceStatus.FAILURE
  inference_result.error_message = str(e)
  return inference_result
```

And when the caller later sees `inference_result.inferences is None`:
```python
if inference_result.inferences is None:
  session_details = None
  if inference_result.session_id is not None:
    session_details = await self._session_service.get_session(...)
  return (
      inference_result,
      EvalCaseResult(...final_eval_status=EvalStatus.FAILED...),
  )
```

So `LocalEvalService` itself does **not** silently swallow the exception into a false pass — it explicitly records `InferenceStatus.FAILURE`, an `error_message`, and produces an `EvalCaseResult` with `final_eval_status=EvalStatus.FAILED` for that case, and per-case metric evaluation is skipped (not run "anyway with empty responses").

**Where the actual "vacuous pass" risk lives (confirmed from `agent_evaluator.py` source):** the pytest-facing assertion path (`_process_metrics_and_get_failures` → `evaluate_eval_set`) does **not** inspect `EvalCaseResult.final_eval_status` or `InferenceStatus` at all. It only aggregates **per-metric scores that exist** and compares an `overall_score` to `threshold`:
```python
overall_eval_status = (
    EvalStatus.PASSED
    if overall_score >= threshold
    else EvalStatus.FAILED
)
...
if overall_eval_status != EvalStatus.PASSED:
    failures.append(
        f"{metric_name} for {agent_module} Failed. Expected {threshold},"
        f" but got {overall_score}."
    )
...
assert not failures, failure_message
```
Because cases whose inference failed never contribute a metric score (they were skipped upstream), if **every** case in a run 403s on inference, the metric-score list the aggregation walks is empty/vacuous — there's nothing to average below threshold, so `failures` stays empty and `assert not failures` passes. **This precisely reproduces and technically explains** this repo's documented gotcha ("the integration eval suite passes vacuously under pytest... `AgentEvaluator.evaluate_eval_set` counts failures only from metric results (empty when inference failed)"). The refinement for the repo's notes: it is not that `LocalEvalService` "swallows" the error — it correctly flags `FAILURE`/`EvalStatus.FAILED` at the case level — it's that `AgentEvaluator`'s own pass/fail aggregation layer on top never looks at that per-case status, only at metric-score means. A workstream-16 fix targeting genuine live-API assertions should check `EvalCaseResult.final_eval_status` / `InferenceStatus` directly (e.g. via `LocalEvalService` at a lower level) rather than relying on `AgentEvaluator.evaluate()`/`evaluate_eval_set()`'s built-in assertion, if it wants inference failures to hard-fail the test.

*(Caveat: exact line numbers "349-378" / "233-247" were reported by the fetch tool from the live file at fetch time; I did not independently re-verify line numbers, only the quoted code blocks, which the tool asserts are verbatim from the file.)*

### 2.4 `adk eval` CLI usage

Verbatim example (`docs/evaluate/index.md` via context7):
```shell
adk eval \
    samples_for_testing/hello_world \
    samples_for_testing/hello_world/hello_world_eval_set_001.evalset.json
```

General form (from `docs/api-reference/cli/index.html` + `docs/evaluate/index.md`):
```shell
adk eval <AGENT_MODULE_FILE_PATH> <EVAL_SET_FILE_PATH> \
    [--config_file_path=<PATH>] \
    [--print_detailed_results]
```
- Requires the path to the agent module file, and either eval-set file path(s) or eval-set IDs.
- To run a subset of cases within a file: colon-delimited syntax `file.json:eval_1,eval_2`.
- `--config_file_path` overrides the default `test_config.json` lookup.

I was not able to retrieve a literal `adk eval --help` flag dump (the supplemental WebFetch pass over `docs/evaluate/index.md` explicitly reported it could not find one in that page) — treat the flag list above as what's documented in prose, not a verified exhaustive `--help` output. This is a gap worth closing by running `adk eval --help` directly against the installed CLI in this repo's `.venv` rather than relying further on docs for the flag list.

### 2.5 Pytest integration pattern

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
This is exactly the shape this repo's existing `tests/integration/` eval-set-based tests already use — consistent with `make test-integration` in `CLAUDE.md`.

---

## 3. Evaluating multi-agent apps: `transfer_to_agent`, trajectory-matching modes, judge/rubric metrics

### 3.1 How sub-agent routing appears in tool trajectories

ADK's LLM-driven agent transfer (`AutoFlow`) is implemented as a **function call named `transfer_to_agent`** with an `agent_name` argument, emitted by the coordinator's underlying model — this is not a special eval-only construct, it's the actual runtime mechanism (`docs/agents/custom-agents.md`, via context7):

> "If coordinator receives 'Book a flight', its LLM should generate: `FunctionCall(name='transfer_to_agent', args={'agent_name': 'Booker'})`. ADK framework then routes execution to booking_agent."

Because `tool_trajectory_avg_score` (and the trajectory rubric metrics) simply diff the *actual* list of tool/function calls the agent produced against the *expected* `intermediate_data.tool_uses` list, `transfer_to_agent` shows up as an ordinary entry in that list — **there is no separate/special "sub-agent routing" schema**; it's represented exactly like any other tool call.

**Confirmed against a real, current upstream fixture** (`google/adk-python` `main`, `tests/integration/fixture/trip_planner_agent/trip_inquiry_multi_turn.test.json`, fetched directly, not paraphrased):
```json
"intermediate_data": {
  "tool_uses": [
    {
      "id": null,
      "args": {
        "agent_name": "identify_agent"
      },
      "name": "transfer_to_agent"
    }
  ],
  "intermediate_responses": []
}
```
Note `"id": null` is legal/expected (unlike ordinary tool calls which typically carry a real function-call `id`), and `args` is exactly `{"agent_name": "<target_sub_agent_name>"}`. Other same-repo fixtures with identical shape: `contributing/samples/multi_agent/hello_world_ma/tests/roll_die_and_check_prime.json`, `contributing/samples/multi_agent/sub_agents/tests/check_status.json`, `contributing/samples/multi_agent/sub_agents/tests/check_and_close.json` (all confirmed to contain `"name": "transfer_to_agent"` entries via GitHub code search — not independently fetched in full, but search snippets show the same `{"id": "fc-1", "name": "transfer_to_agent", ...}` shape, i.e. some fixtures do populate a real `id` like `"fc-1"` rather than `null` — both forms appear to be accepted).

**Direct implication for this repo:** the phase doc's premise ("the repo currently has adk eval sets written ~May 2026 that pin direct tool calls") is testable/comparable directly against this shape — if this repo's multi-agent eval cases (Coordinator → Campaign/Media/Analytics Agent) don't include `transfer_to_agent` entries in `intermediate_data.tool_uses` wherever a sub-agent handoff happens, `tool_trajectory_avg_score` under `EXACT`/`IN_ORDER`/`ANY_ORDER` will never match live-model trajectories, regardless of match_type, because the expected list is missing the hop itself. This is very likely the actual root cause of the pre-existing "eval sets FAIL as authored (expected direct tool calls vs actual `transfer_to_agent`-wrapped trajectories)" gotcha already recorded in this repo's `CLAUDE.md`.

### 3.2 Trajectory-matching modes — current guidance

No dedicated "multi-agent trajectory matching" doc section exists (confirmed by supplemental WebFetch explicitly searching `docs/evaluate/index.md` for this and coming up empty beyond one line: *"These natural language responses are usually an artifact of a multi-agent system, where your root agent depends on sub-agents to achieve a goal"* — referring to the `intermediate_responses` field). The three generic `match_type` values (`EXACT`, `IN_ORDER`, `ANY_ORDER` — §1.4) are the only first-party mechanism for trajectory leniency, and they are agent-topology-agnostic: they don't know or care whether an entry in the tool list is `transfer_to_agent` vs. a real tool. Practical reading for workstream 16:
- `EXACT` (the default when a bare float threshold is given) is almost certainly too brittle for any multi-agent flow where a live LLM decides routing — a single extra clarifying tool call, or a different-but-equally-valid sub-agent path, fails the whole invocation's score.
- `IN_ORDER` is the natural middle ground for coordinator→sub-agent flows: it still enforces that `transfer_to_agent(agent_name=X)` happens before `X`'s tool calls, but tolerates the model doing extra/different things around it.
- `ANY_ORDER` is likely too loose for verifying a specific handoff actually happened before a specific tool ran.
- The **rubric-based alternative**, `rubric_based_tool_use_quality_v1` (§1.4), is the more robust current-ADK answer for judging "did the right handoff/tool-use pattern happen" semantically via an LLM judge instead of literal list-diffing — its own worked example in the docs is exactly a multi-step-tool-order case ("The agent calls the GeoCoding tool before calling the GetWeather tool").

### 3.3 Judge-model / rubric-based metrics — config recap (see §1.4 for full JSON)

- `final_response_match_v2`: LLM judge, valid/invalid + majority vote, config = `{threshold, judge_model_options: {judge_model, num_samples}}`.
- `rubric_based_final_response_quality_v1` / `rubric_based_tool_use_quality_v1` / `rubric_based_multi_turn_trajectory_quality_v1`: LLM judge scored against a list of natural-language `rubrics` (`rubric_id` + `rubric_content.text_property`), same `judge_model_options` shape.
- `hallucinations_v1`: LLM judge with an `evaluate_intermediate_nl_responses` boolean — can also judge sub-agent NL hand-off text, not just the final answer, which is directly relevant to a multi-agent Coordinator pattern.
- `safety_v1`, `multi_turn_task_success_v1`, `multi_turn_trajectory_quality_v1`, `multi_turn_tool_use_quality_v1`: simple float-threshold LLM-judged multi-turn variants (no worked example of their internals was returned — only the threshold-only config shape).
- All of the above default `judge_model_options.judge_model` in the doc examples to `"gemini-flash-latest"` — this repo would need to decide whether to pin this to a specific Gemini 3.x model consistent with the `GOOGLE_CLOUD_LOCATION=global` gotcha already in `CLAUDE.md`, since `"gemini-flash-latest"` is a moving alias.

---

## What changed vs. older ADK (as far as this research could determine)

1. **`criteria: dict[str, float]` on `evaluate_eval_set()` is now explicitly deprecated** in favor of `eval_config: EvalConfig` — confirms this repo should write new eval-config code against `EvalConfig`/`test_config.json`, not the bare dict form, if it wants match-type or judge/rubric criteria at all (the deprecated dict form can't express those).
2. **`tool_trajectory_avg_score` now supports `match_type` (`EXACT`/`IN_ORDER`/`ANY_ORDER`)** via the object config form — a bare float threshold silently means `EXACT`. If this repo's May-2026 eval sets configure `tool_trajectory_avg_score` as a bare float (or omit config entirely, hitting the doc-stated exact-match default), that alone — independent of the `transfer_to_agent` gap in §3.1 — would make multi-agent trajectories brittle against a live model.
3. **A whole family of rubric-based / LLM-judge criteria exists** (`rubric_based_*_v1`, `final_response_match_v2`, `hallucinations_v1`, `safety_v1`, `per_turn_user_simulator_quality_v1`, `multi_turn_*_v1`) that provide semantic/judge-based alternatives to literal trajectory/text diffing — the `_v1`/`_v2` suffixes and the `LlmAsAJudgeCriterion` naming strongly suggest these are a newer generation of metrics layered on top of the original `tool_trajectory_avg_score` + `response_match_score` pair; the docs don't date them, so treat "newer" as inferred from naming/structure rather than confirmed via changelog.
4. **`LocalEvalService` does correctly detect and flag inference failures** (`InferenceStatus.FAILURE`, `EvalCaseResult.final_eval_status=EvalStatus.FAILED`) at the service layer — the vacuous-pass problem this repo already documented is real, but lives specifically in `AgentEvaluator`'s pytest-assertion aggregation (`_process_metrics_and_get_failures`), which never inspects that per-case failure status, only mean metric scores. This is a more precise mechanism than "LocalEvalService swallows inference exceptions by design" as currently phrased in `CLAUDE.md` — worth a `DISCOVERY`-style amendment if workstream 16 changes this codepath, per this repo's discoveries process.
5. Both `.test.json` and `.evalset.json` are literally the same `EvalSet` Pydantic schema; the difference is purely file-suffix-driven directory discovery + single- vs multi-case intent — nothing in the schema itself distinguishes them.

## Gaps / things not independently confirmed

- No literal `adk eval --help` output was retrieved from docs; the flag list in §2.4 is prose-derived. Recommend running the installed CLI directly (`adk eval --help`) in this repo's venv for the authoritative current flag set, since that's local tooling, not something requiring "memory of older ADK" and is trivially checkable.
- The exact default numeric values baked into code for "no config file found" (vs. the docs' stated 1.0-EXACT / 0.8-ROUGE-1) were not located as a literal code constant in the fetched excerpt of `agent_evaluator.py` — only the config-file-lookup method (`find_config_for_test_file`, default filename `test_config.json`) was confirmed directly from source.
- Whether `rubric_based_*` / `final_response_match_v2` / `hallucinations_v1` etc. require a specific minimum ADK version was not determinable from the docs fetched (no version-gating notes were surfaced) — if workstream 16 depends on these, pin/verify against this repo's actual installed `google-adk` version (check `app/requirements.txt` / `pip show google-adk`) before relying on them being available.
