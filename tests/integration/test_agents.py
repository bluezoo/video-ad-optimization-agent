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

"""Live integration tests: 3-dimension eval scoring via the local harness.

Each test runs its EvalSet through tests.integration.eval_harness —
inference ONCE per case against the real agent (Task 4's conftest supplies
the real Vertex env + isolated DB), then tools / trajectory / answer
dimensions scored from live_eval_config.json. assert_eval_outcomes is the
vacuity guard (Q19): zero or partial inference runs can never PASS.

The xfail markers below are honest: the five eval sets were authored before
the transfer_to_agent-wrapped trajectories ws09 discovered, so they now
genuinely run and genuinely fail. Each stage-4 repair task (Tasks 6-10)
removes its marker.
"""

import pytest

from tests.integration.eval_harness import (
    assert_eval_outcomes,
    get_eval_set_path,
    run_eval_set,
)

pytestmark = pytest.mark.integration

_AUTHORED_PRE_TRANSFER = pytest.mark.xfail(
    reason=(
        "eval set authored pre-transfer_to_agent (ws09 discovery) — repaired"
        " in Phase 16 stage 4"
    ),
    strict=False,
)


class TestCoordinatorAgentRouting:
    """Test that the coordinator routes queries to correct sub-agents."""

    async def test_coordinator_routes_to_campaign_agent(self):
        """Coordinator should route queries to the right sub-agent + tool."""
        outcomes = await run_eval_set(get_eval_set_path("coordinator.test.json"))
        assert_eval_outcomes(outcomes, expect_cases=4)


class TestCampaignAgent:
    """Test Campaign Agent tool execution."""

    @_AUTHORED_PRE_TRANSFER
    async def test_campaign_agent_tools(self):
        """Campaign agent should correctly execute campaign tools."""
        outcomes = await run_eval_set(
            get_eval_set_path("campaign_agent.test.json")
        )
        assert_eval_outcomes(outcomes, expect_cases=4)


class TestMediaAgent:
    """Test Media Agent tool execution."""

    @_AUTHORED_PRE_TRANSFER
    async def test_media_agent_tools(self):
        """Media agent should correctly execute media tools."""
        outcomes = await run_eval_set(get_eval_set_path("media_agent.test.json"))
        assert_eval_outcomes(outcomes, expect_cases=5)


class TestReviewAgent:
    """Test Review Agent tool execution."""

    @_AUTHORED_PRE_TRANSFER
    async def test_review_agent_tools(self):
        """Review agent should correctly execute review tools."""
        outcomes = await run_eval_set(get_eval_set_path("review_agent.test.json"))
        assert_eval_outcomes(outcomes, expect_cases=3)


class TestAnalyticsAgent:
    """Test Analytics Agent tool execution."""

    @_AUTHORED_PRE_TRANSFER
    async def test_analytics_agent_tools(self):
        """Analytics agent should correctly execute analytics tools."""
        outcomes = await run_eval_set(
            get_eval_set_path("analytics_agent.test.json")
        )
        assert_eval_outcomes(outcomes, expect_cases=4)
