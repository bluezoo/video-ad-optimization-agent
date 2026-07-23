# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Live eval harness: single-inference, 3-dimension scoring, vacuity guard.

Why not AgentEvaluator.evaluate(): its pytest aggregation only compares mean
metric scores and never inspects per-case final_eval_status — when every
inference fails there are no scores and the assert passes VACUOUSLY (Q19,
confirmed from source; see research/adk-eval-docs-context7.md). This harness
drives the same underlying eval stack but asserts inference status per case.

Installed API surface (verified against google-adk 2.5.0 source in
.venv/lib/python3.14/site-packages/google/adk/evaluation/, Phase 16
directive 4 — findings, with file paths):

(a) Eval set loading: ``load_eval_set_from_file(path, eval_set_id)`` in
    ``local_eval_sets_manager.py:176`` — validates the new ``EvalSet`` schema
    first, falls back to old-format conversion. All five eval sets under
    ``tests/integration/eval_sets/`` are already in the new schema.
(b) Inference: ``LocalEvalService.perform_inference(inference_request)``
    (``local_eval_service.py:143``) yields one ``InferenceResult`` per eval
    case with per-case ``status`` (``InferenceStatus.SUCCESS/FAILURE``) and
    ``error_message`` (``base_eval_service.py:137-172``) — inference
    exceptions are swallowed into FAILURE results by design
    (``local_eval_service.py:551-562``), which is exactly the behavior the
    vacuity guard exists to surface.
(c) Metric evaluation over existing inference results:
    ``LocalEvalService.evaluate(EvaluateRequest(inference_results=...,
    evaluate_config=EvaluateConfig(eval_metrics=...)))``
    (``local_eval_service.py:194``) — no re-inference; metrics come from
    ``get_eval_metrics_from_config(EvalConfig...)`` (``eval_config.py:229``).
    ``EvalConfig.criteria`` values parse as ``BaseCriterion`` with
    ``extra="allow"`` (``eval_metrics.py:109``); each evaluator re-validates
    into its own criterion type, e.g. ``ToolTrajectoryCriterion`` with
    string-coerced ``match_type`` (``trajectory_evaluator.py:78-96``,
    ``eval_metrics.py:252-261``).
(d) ``final_response_match_v2`` exists in installed 2.5.0
    (``eval_metrics.py:52`` PrebuiltMetrics, ``final_response_match_v2.py:130``
    ``FinalResponseMatchV2Evaluator`` with ``LlmAsAJudgeCriterion``), as does
    ``rubric_based_final_response_quality_v1`` (``eval_metrics.py:54``).
"""

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

try:
    from google.adk.evaluation.base_eval_service import (
        EvaluateConfig,
        EvaluateRequest,
        InferenceConfig,
        InferenceRequest,
        InferenceStatus,
    )
    from google.adk.evaluation.eval_case import Invocation, get_all_tool_calls
    from google.adk.evaluation.eval_config import (
        EvalConfig,
        get_eval_metrics_from_config,
    )
    from google.adk.evaluation.eval_metrics import EvalMetric
    from google.adk.evaluation.evaluator import EvalStatus
    from google.adk.evaluation.in_memory_eval_sets_manager import (
        InMemoryEvalSetsManager,
    )
    from google.adk.evaluation.local_eval_service import LocalEvalService
    from google.adk.evaluation.local_eval_sets_manager import (
        load_eval_set_from_file,
    )
except ImportError as e:
    # Fail loudly (ws01 lesson): a silent skip once hid a missing eval extra
    # behind "6 skipped". The ADK eval stack needs the [eval] extra deps
    # (pandas, tabulate, rouge-score, ...).
    raise ImportError(
        "google.adk.evaluation stack is unavailable. Install the eval extra:"
        " pip install 'google-adk[eval]' — see SETUP_INSTRUCTIONS.md (Tests)."
    ) from e

_APP_NAME = "live_eval"

EVAL_SETS_DIR = Path(__file__).parent / "eval_sets"
LIVE_EVAL_CONFIG_PATH = EVAL_SETS_DIR / "live_eval_config.json"


def get_eval_set_path(filename: str) -> str:
    """Absolute path to an eval_set JSON file under tests/integration/eval_sets."""
    return str(EVAL_SETS_DIR / filename)


@dataclass
class DimensionOutcome:
    score: float | None
    threshold: float
    passed: bool


@dataclass
class CaseOutcome:
    eval_id: str
    inference_ok: bool
    error_message: str | None
    actual_tool_calls: list[dict]
    final_response_text: str
    dimensions: dict[str, DimensionOutcome] = field(default_factory=dict)


_INFRA_MARKERS = (
    "credential", "permission denied", "permission_denied", "403", "quota",
    "resource_exhausted", "429", "unavailable", "503", "deadline",
    "connection", "getaddrinfo",
)  # kept from the old test_agents.py — infra breakage may xfail, never PASS


def load_dimension_metrics(
    config_path: str | Path = LIVE_EVAL_CONFIG_PATH,
) -> dict[str, list[EvalMetric]]:
    """Parse live_eval_config.json into per-dimension ADK EvalMetric lists.

    The file keeps each dimension's payload in NATIVE ADK ``EvalConfig``
    shape (``{"criteria": {...}}``); only the outer "dimensions" wrapper is
    ours (orchestration ours, formats native).
    """
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return {
        name: get_eval_metrics_from_config(EvalConfig.model_validate(dim))
        for name, dim in payload["dimensions"].items()
    }


def _load_root_agent():
    """Import the app's root agent (same convention as AgentEvaluator)."""
    return importlib.import_module("app.agent").root_agent


def _extract_actuals(
    invocations: list[Invocation],
) -> tuple[list[dict], str]:
    """Ordered actual tool calls (incl. transfer_to_agent) + final answer text."""
    tool_calls: list[dict] = []
    final_text = ""
    for invocation in invocations:
        for call in get_all_tool_calls(invocation.intermediate_data):
            tool_calls.append({"name": call.name, "args": dict(call.args or {})})
        if invocation.final_response and invocation.final_response.parts:
            texts = [p.text for p in invocation.final_response.parts if p.text]
            if texts:
                final_text = "\n".join(texts)
    return tool_calls, final_text


def _record_outcomes(
    outcomes: list[CaseOutcome], queries: dict[str, str], record_to: str
) -> None:
    """Dump actual trajectories + answers for calibration / trace export."""
    payload = [
        {
            "eval_id": o.eval_id,
            "query": queries.get(o.eval_id, ""),
            "inference_ok": o.inference_ok,
            "error_message": o.error_message,
            "actual_tool_calls": o.actual_tool_calls,
            "final_response_text": o.final_response_text,
            "dimensions": {
                name: {"score": d.score, "threshold": d.threshold, "passed": d.passed}
                for name, d in o.dimensions.items()
            },
        }
        for o in outcomes
    ]
    out_path = Path(record_to)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


async def run_eval_set(
    eval_set_path: str, *, record_to: str | None = None
) -> list[CaseOutcome]:
    """Run inference ONCE per case, then score all three dimensions.

    Inference results are reused across the per-dimension metric passes —
    only the judge metric makes additional (judge-model) LLM calls.
    """
    eval_set = load_eval_set_from_file(eval_set_path, Path(eval_set_path).stem)

    eval_sets_manager = InMemoryEvalSetsManager()
    eval_sets_manager.create_eval_set(
        app_name=_APP_NAME, eval_set_id=eval_set.eval_set_id
    )
    for eval_case in eval_set.eval_cases:
        eval_sets_manager.add_eval_case(
            app_name=_APP_NAME,
            eval_set_id=eval_set.eval_set_id,
            eval_case=eval_case,
        )

    eval_service = LocalEvalService(
        root_agent=_load_root_agent(), eval_sets_manager=eval_sets_manager
    )

    # 1. Inference — ONCE per case.
    inference_results = []
    inference_request = InferenceRequest(
        app_name=_APP_NAME,
        eval_set_id=eval_set.eval_set_id,
        inference_config=InferenceConfig(),
    )
    async for inference_result in eval_service.perform_inference(
        inference_request=inference_request
    ):
        inference_results.append(inference_result)

    outcomes_by_id: dict[str, CaseOutcome] = {}
    for result in inference_results:
        tool_calls, final_text = _extract_actuals(result.inferences or [])
        outcomes_by_id[result.eval_case_id] = CaseOutcome(
            eval_id=result.eval_case_id,
            inference_ok=result.status == InferenceStatus.SUCCESS,
            error_message=result.error_message,
            actual_tool_calls=tool_calls,
            final_response_text=final_text,
        )

    # 2. Metric passes — one per dimension, over the SAME inference results.
    successful = [
        r for r in inference_results if r.status == InferenceStatus.SUCCESS
    ]
    if successful:
        for name, metrics in load_dimension_metrics().items():
            evaluate_request = EvaluateRequest(
                inference_results=successful,
                evaluate_config=EvaluateConfig(eval_metrics=metrics),
            )
            async for case_result in eval_service.evaluate(
                evaluate_request=evaluate_request
            ):
                metric_results = case_result.overall_eval_metric_results
                metric_result = metric_results[0] if metric_results else None
                outcomes_by_id[case_result.eval_id].dimensions[name] = (
                    DimensionOutcome(
                        score=metric_result.score if metric_result else None,
                        threshold=(
                            metric_result.threshold
                            if metric_result and metric_result.threshold is not None
                            else (metrics[0].threshold or 0.0)
                        ),
                        passed=bool(
                            metric_result
                            and metric_result.eval_status == EvalStatus.PASSED
                        ),
                    )
                )

    # Stable order: as authored in the eval set.
    outcomes = [
        outcomes_by_id[c.eval_id]
        for c in eval_set.eval_cases
        if c.eval_id in outcomes_by_id
    ]

    if record_to:
        queries = {
            c.eval_id: (
                c.conversation[0].user_content.parts[0].text or ""
                if c.conversation and c.conversation[0].user_content.parts
                else ""
            )
            for c in eval_set.eval_cases
        }
        _record_outcomes(outcomes, queries, record_to)

    return outcomes


def assert_eval_outcomes(
    outcomes: list[CaseOutcome], *, expect_cases: int
) -> None:
    """Vacuity guard + per-dimension gate (Q19).

    Zero or partial inference runs must never PASS; infra breakage may
    xfail, never PASS; any failed dimension fails the test.
    """
    import pytest

    if len(outcomes) != expect_cases:
        pytest.fail(
            f"expected {expect_cases} eval cases, only {len(outcomes)} produced"
            " results — partial/zero runs must not pass"
        )
    failed_inference = [o for o in outcomes if not o.inference_ok]
    if failed_inference:
        msgs = "; ".join(
            f"{o.eval_id}: {o.error_message}" for o in failed_inference
        )
        if all(
            any(m in (o.error_message or "").lower() for m in _INFRA_MARKERS)
            for o in failed_inference
        ):
            pytest.xfail(f"integration infrastructure unavailable: {msgs}")
        pytest.fail(f"inference failed (NOT infra): {msgs}")
    dim_failures = [
        f"{o.eval_id}[{name}]: score={d.score} < {d.threshold}"
        for o in outcomes
        for name, d in o.dimensions.items()
        if not d.passed
    ]
    if dim_failures:
        pytest.fail("eval dimension failures:\n  " + "\n  ".join(dim_failures))
