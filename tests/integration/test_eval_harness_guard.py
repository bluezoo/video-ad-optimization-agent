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

"""Deliberate-break checks: zero/partial inference must never PASS (Q19)."""

import pytest
from _pytest.outcomes import Failed, XFailed

from tests.integration.eval_harness import (
    CaseOutcome,
    DimensionOutcome,
    assert_eval_outcomes,
)

pytestmark = pytest.mark.integration


def _case(eval_id="c1", ok=True, err=None):
    return CaseOutcome(
        eval_id=eval_id,
        inference_ok=ok,
        error_message=err,
        actual_tool_calls=[],
        final_response_text="",
    )


def test_all_inference_failed_never_passes():
    bad = [_case(ok=False, err="something exploded (not infra-shaped)")]
    with pytest.raises(Failed):
        assert_eval_outcomes(bad, expect_cases=1)


def test_infra_failure_xfails_not_passes():
    bad = [_case(ok=False, err="403 PERMISSION_DENIED on aiplatform")]
    with pytest.raises(XFailed):
        assert_eval_outcomes(bad, expect_cases=1)


def test_partial_results_never_pass():
    with pytest.raises(Failed):
        assert_eval_outcomes([_case()], expect_cases=4)


def test_failed_dimension_fails():
    good = _case()
    good.dimensions["tools"] = DimensionOutcome(
        score=0.0, threshold=1.0, passed=False
    )
    with pytest.raises(Failed, match=r"c1\[tools\]"):
        assert_eval_outcomes([good], expect_cases=1)


def test_all_green_passes():
    good = _case()
    good.dimensions["tools"] = DimensionOutcome(
        score=1.0, threshold=1.0, passed=True
    )
    assert_eval_outcomes([good], expect_cases=1)


def test_answer_retry_targets_only_the_answer_dimension():
    """GATE-3 bounded retry re-judges ONLY the answer dimension.

    Guards the retry constant against config drift: if the config's answer
    dimension were renamed, the retry would silently no-op. The deterministic
    tools/trajectory dimensions exist and are never retried. Pure (no live).
    """
    from tests.integration.eval_harness import (
        _ANSWER_DIMENSION,
        load_dimension_metrics,
    )

    dims = load_dimension_metrics()
    assert _ANSWER_DIMENSION == "answer"
    assert _ANSWER_DIMENSION in dims, "retry would no-op: no 'answer' dimension in config"
    assert {"tools", "trajectory"} <= set(dims)  # deterministic dims, not retried


def test_isolation_guard_refuses_root_db(monkeypatch):
    """The isolation guard must REFUSE to run against the root campaigns.db.

    [ws16 GATE-3 isolation fix] Regression guard for the eval-set DB leak:
    eval inference mutates the campaigns DB via real tools, so pointing it at
    the seeded root DB would accumulate eval-created campaigns across runs.
    Pure (no live inference) — just asserts the structural guard fires.
    """
    import app.config as config
    from tests.conftest import MAIN_DB_PATH
    from tests.integration.eval_harness import _assert_isolated_db

    monkeypatch.setattr(config, "DB_PATH", str(MAIN_DB_PATH))
    with pytest.raises(RuntimeError, match="root campaigns.db"):
        _assert_isolated_db()


def test_isolation_guard_allows_temp_db(monkeypatch, tmp_path):
    """The isolation guard passes when config.DB_PATH is an isolated copy."""
    import app.config as config
    from tests.integration.eval_harness import _assert_isolated_db

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "campaigns.db"))
    _assert_isolated_db()  # must not raise
