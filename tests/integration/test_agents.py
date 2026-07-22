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

"""Integration tests for agents using ADK's AgentEvaluator.

These tests use EvalSet JSON files to validate agent behavior with real LLM calls.
Tests are marked with @pytest.mark.integration to allow selective execution.

Run with: pytest tests/integration -v -m "not slow"
"""

from pathlib import Path

import pytest

try:
    from google.adk.evaluation import AgentEvaluator
except ImportError as e:
    # Fail loudly. A broad per-test `except ImportError: pytest.skip` used to
    # swallow this, silently reporting the whole suite as 6 skips when the
    # eval extra was missing (discovered in workstream 01).
    raise ImportError(
        "google.adk.evaluation is unavailable. Install the eval extra: "
        "pip install 'google-adk[eval]' — see SETUP_INSTRUCTIONS.md (Tests)."
    ) from e

# Skip these tests if not configured for integration testing
pytestmark = pytest.mark.integration


def get_eval_set_path(filename: str) -> str:
    """Get the absolute path to an eval_set JSON file."""
    return str(Path(__file__).parent / "eval_sets" / filename)


def eval_sets_exist() -> bool:
    """Check if eval_sets directory has JSON files."""
    eval_dir = Path(__file__).parent / "eval_sets"
    if not eval_dir.exists():
        return False
    json_files = list(eval_dir.glob("*.test.json"))
    return len(json_files) > 0


# Skip all tests if eval_sets don't exist
if not eval_sets_exist():
    pytestmark = [pytest.mark.integration, pytest.mark.skip(reason="No eval_sets found")]


_INFRA_MARKERS = (
    "credential", "permission denied", "permission_denied", "403", "quota",
    "resource_exhausted", "429",
    "unavailable", "503", "deadline", "connection", "getaddrinfo",
)


def _xfail_if_infrastructure(e: Exception):
    """xfail ONLY on infrastructure errors; real eval failures must fail the test."""
    msg = str(e).lower()
    if isinstance(e, (ConnectionError, TimeoutError)) or any(m in msg for m in _INFRA_MARKERS):
        pytest.xfail(f"Integration infrastructure unavailable: {e}")
    raise e


class TestCoordinatorAgentRouting:
    """Test that the coordinator routes queries to correct sub-agents."""

    @pytest.mark.asyncio
    async def test_coordinator_routes_to_campaign_agent(self):
        """Coordinator should route campaign queries to campaign_agent."""
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("coordinator.test.json"),
                num_runs=1,  # Single run for faster tests
            )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)


class TestCampaignAgent:
    """Test Campaign Agent tool execution."""

    @pytest.mark.asyncio
    async def test_campaign_agent_tools(self):
        """Campaign agent should correctly execute campaign tools."""
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("campaign_agent.test.json"),
                num_runs=1,
            )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)


class TestMediaAgent:
    """Test Media Agent tool execution."""

    @pytest.mark.asyncio
    async def test_media_agent_tools(self):
        """Media agent should correctly execute media tools."""
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("media_agent.test.json"),
                num_runs=1,
            )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)


class TestReviewAgent:
    """Test Review Agent tool execution."""

    @pytest.mark.asyncio
    async def test_review_agent_tools(self):
        """Review agent should correctly execute review tools."""
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("review_agent.test.json"),
                num_runs=1,
            )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)


class TestAnalyticsAgent:
    """Test Analytics Agent tool execution."""

    @pytest.mark.asyncio
    async def test_analytics_agent_tools(self):
        """Analytics agent should correctly execute analytics tools."""
        try:
            await AgentEvaluator.evaluate(
                agent_module="app.agent",
                eval_dataset_file_path_or_dir=get_eval_set_path("analytics_agent.test.json"),
                num_runs=1,
            )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)


class TestAllEvalSets:
    """Run all eval sets in the eval_sets directory."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_all_eval_sets_multi_run(self):
        """Run all eval sets with multiple runs for variance testing."""
        try:
            eval_dir = Path(__file__).parent / "eval_sets"
            for eval_file in eval_dir.glob("*.test.json"):
                await AgentEvaluator.evaluate(
                    agent_module="app.agent",
                    eval_dataset_file_path_or_dir=str(eval_file),
                    num_runs=2,  # Multiple runs for variance
                )
        except AssertionError:
            raise
        except Exception as e:
            _xfail_if_infrastructure(e)
