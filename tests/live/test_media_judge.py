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

"""Gemini judge tests over the live-tier generated media (Phase 16 Task 14).

Two families:

1. ``test_generated_media_obey_rubric`` — judges every entry the pipeline
   tests (Task 12) and the from-scratch onboarding test (Task 13) registered
   in the session-scoped ``generated_media`` registry. A hard-check failure
   fails the test; a warn-check failure only emits a ``warnings.warn`` + a
   report line. When the registry is empty (this file collected/run before the
   generators, or run standalone), it falls back to the media already on disk
   from a previous live run — and skips with a reason if none is present.

2. ``test_rpi_chart_obeys_inverted_rubric`` — renders one deterministic RPI
   comparison chart via the REAL chart tool (ws07's
   ``generate_creative_comparison_chart``) over the seeded campaign and judges
   it with the INVERTED rubric: chart text is REQUIRED and legible, and the
   bar count must equal the seeded activated-creative count.
"""

import warnings
from pathlib import Path

import pytest

import app.config as config
from tests.live.judge import judge_chart, judge_media_entry

pytestmark = [pytest.mark.live, pytest.mark.slow]


# Request contexts mirror what the Task 12/13 generators register, so a
# standalone (registry-empty) disk run judges the media against the same
# rubric context the in-session run would use.
_WEARABLE_CONTEXT = (
    "Fashion video ad for the blue-floral-maxi-dress: human model wearing "
    "the dress; elegant mood, studio setting, cinematic style (default-elegant)."
)
_NON_WEARABLE_CONTEXT = (
    "Product-hero video ad for the aurora-cold-brew-330ml canned coffee: "
    "product is the hero, NO humans; vibrant mood, cafe setting."
)
_ONBOARDING_CONTEXT = (
    "Catalog reference photo generated during from-scratch onboarding of a "
    "non-fashion product (Artisan Coffee Beans, a 340g bag of medium-roast "
    "Ethiopian coffee): clean neutral studio background, soft even lighting, "
    "product centered and fully visible, no people, no text overlays."
)

# label -> (kind, archetype, directory, glob, request_context). Directories are
# resolved at call time (config is reloaded under the live env before use).
_DISK_SPECS = [
    ("wearable_scene_image", "image", "wearable", "GENERATED_DIR",
     "blue-floral-maxi-dress-*-thumbnail.png", _WEARABLE_CONTEXT),
    ("wearable_video", "video", "wearable", "GENERATED_DIR",
     "blue-floral-maxi-dress-*.mp4", _WEARABLE_CONTEXT),
    ("non_wearable_scene_image", "image", "consumable-hero", "GENERATED_DIR",
     "aurora-cold-brew-330ml-*-thumbnail.png", _NON_WEARABLE_CONTEXT),
    ("non_wearable_video", "video", "consumable-hero", "GENERATED_DIR",
     "aurora-cold-brew-330ml-*.mp4", _NON_WEARABLE_CONTEXT),
    ("onboarding_product_image", "image", "onboarding-product-reference",
     "PRODUCT_IMAGES_DIR", "artisan-coffee-beans.png", _ONBOARDING_CONTEXT),
]


def _resolve_media(registry: dict) -> dict:
    """Prefer the in-session registry; fall back to media already on disk.

    Order-independent: in a full ``make test-live`` run the generators may run
    before or after this file, and a standalone run has no generators at all.
    Either way we judge whatever media is available and skip if there is none.
    """
    if registry:
        return dict(registry)

    entries: dict = {}
    for label, kind, archetype, dir_attr, glob, context in _DISK_SPECS:
        directory = Path(getattr(config, dir_attr))
        matches = sorted(directory.glob(glob))
        if matches:
            entries[label] = {
                "kind": kind,
                "path": str(matches[-1]),  # newest by timestamped filename
                "archetype": archetype,
                "request_context": context,
            }
    return entries


class TestMediaJudge:
    def test_generated_media_obey_rubric(self, generated_media):
        """Every generated media item passes its hard rubric checks."""
        entries = _resolve_media(generated_media)
        if not entries:
            pytest.skip(
                "no generated media in the registry or on disk — run the "
                "pipeline/onboarding tests (Tasks 12-13) first"
            )

        hard_failures: list[str] = []
        report: list[str] = []
        for label, entry in sorted(entries.items()):
            verdict = judge_media_entry(entry)
            report.append(f"\n[{label}] {entry['path']}")
            for check, res in verdict.items():
                line = (
                    f"  {check}: {res['verdict']} [{res['severity']}] "
                    f"— {res['evidence']}"
                )
                report.append(line)
                if res["verdict"] == "fail":
                    if res["severity"] == "hard":
                        hard_failures.append(f"{label}/{check}: {res['evidence']}")
                    else:
                        warnings.warn(
                            f"warn-check failed — {label}/{check}: {res['evidence']}",
                            stacklevel=2,
                        )
        print("\n[media-judge report]" + "".join(report))
        assert not hard_failures, "hard-check failures:\n" + "\n".join(hard_failures)

    async def test_rpi_chart_obeys_inverted_rubric(self, isolated_live_db, tmp_path):
        """The deterministic RPI chart passes the inverted (text-required) rubric."""
        from unittest.mock import AsyncMock, MagicMock

        from app.tools.metrics_tools import generate_creative_comparison_chart

        # Seeded campaign 1 has 3 activated creatives with metrics — a stable,
        # deterministic bar count for the correct_creative_count check.
        campaign_id = 1
        ctx = MagicMock()
        ctx.save_artifact = AsyncMock(return_value=1)
        result = await generate_creative_comparison_chart(campaign_id, tool_context=ctx)
        assert result["status"] == "success", f"chart tool failed: {result}"

        comparison = result["comparison"]
        expected_count = comparison["creatives_compared"]
        campaign_name = comparison["campaign_name"]

        png_bytes = ctx.save_artifact.await_args.kwargs["artifact"].inline_data.data
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        chart_path = tmp_path / result["chart"]["filename"]
        chart_path.write_bytes(png_bytes)

        verdict = judge_chart(
            str(chart_path),
            expected_creative_count=expected_count,
            campaign_name=campaign_name,
            request_context=(
                "RPI-per-creative comparison bar chart rendered by matplotlib "
                f"for {expected_count} activated creatives; bar heights are the "
                "exact revenue-per-impression values."
            ),
        )

        report = [f"\n[rpi-chart] {chart_path} (expected {expected_count} bars)"]
        hard_failures: list[str] = []
        for check, res in verdict.items():
            report.append(
                f"  {check}: {res['verdict']} [{res['severity']}] — {res['evidence']}"
            )
            if res["verdict"] == "fail" and res["severity"] == "hard":
                hard_failures.append(f"{check}: {res['evidence']}")
        print("\n[chart-judge report]" + "".join(report))
        assert not hard_failures, "chart hard-check failures:\n" + "\n".join(hard_failures)
