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
from tests.live.judge import (
    judge_chart,
    judge_image,
    judge_media_entry,
    judge_with_hard_retry,
)

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


def _make_text_overlay(src_path: str, dst_path: Path, text: str) -> None:
    """Paint a large rendered-text banner onto a copy of ``src_path``.

    Built on the fly for the negative-control test (no corrupted binary is
    committed). The banner is deliberately large and high-contrast so a
    correctly-working judge cannot miss it.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(src_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font_size = max(48, img.width // 8)
    font = ImageFont.load_default(size=font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (img.width - tw) // 2
    y = (img.height - th) // 2
    pad = font_size // 3
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0))
    draw.text((x - bbox[0], y - bbox[1]), text, fill=(255, 255, 0), font=font)
    img.save(dst_path)


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
            verdict = judge_with_hard_retry(label, judge_media_entry, entry)
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

        verdict = judge_with_hard_retry(
            "rpi_comparison_chart",
            judge_chart,
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


class TestJudgeNegativeControls:
    """Deliberately-violating controls: the judge MUST fail them (ws16 OWNER GATE 2).

    Proves the judge catches violations, not merely that it passes conformant
    media. Controls are built on the fly under ``tmp_path`` or evaluated against
    a mismatched archetype — no corrupted media binary is committed.
    """

    def test_rendered_text_overlay_is_caught(self, generated_media, tmp_path):
        """A big rendered-text banner must trip no_rendered_text (hard)."""
        entries = _resolve_media(generated_media)
        source = entries.get("wearable_scene_image") or next(
            (e for e in entries.values() if e["kind"] == "image"), None
        )
        if source is None:
            pytest.skip("no source image on disk/registry to build the text-overlay control")
        overlay_path = tmp_path / "rendered_text_control.png"
        _make_text_overlay(source["path"], overlay_path, "MEGA SALE - 50% OFF TODAY")

        # Route through the GATE-4 retry: a real violation must hard-fail BOTH
        # the initial judge and the re-judge (fails twice), proving the retry
        # does not let genuine violations slip through.
        verdict = judge_with_hard_retry(
            "neg-control:rendered_text_overlay",
            judge_image,
            str(overlay_path),
            archetype=source["archetype"],
            request_context=source["request_context"],
        )
        check = verdict["no_rendered_text"]
        print(f"\n[neg-control rendered_text] {check}")
        assert check["verdict"] == "fail", (
            f"judge missed a rendered text banner: {check['evidence']}"
        )
        assert check["severity"] == "hard"

    def test_wrong_subject_is_caught(self, generated_media):
        """A human-model image judged as product_only must trip subject (hard)."""
        entries = _resolve_media(generated_media)
        source = entries.get("wearable_scene_image")
        if source is None:
            pytest.skip("wearable scene image (with human model) not available")

        # Judge the human-model image as if it were a product_only shot (no
        # humans allowed) — the human presence must fail subject_matches_archetype.
        # Through the GATE-4 retry: a real mismatch must hard-fail twice.
        verdict = judge_with_hard_retry(
            "neg-control:wrong_subject",
            judge_image,
            source["path"],
            archetype="product_only",
            request_context=(
                "Product-only hero shot (NO humans) — deliberately mismatched "
                "against a wearable image that contains a human model."
            ),
        )
        check = verdict["subject_matches_archetype"]
        print(f"\n[neg-control wrong_subject] {check}")
        assert check["verdict"] == "fail", (
            f"judge missed a human in a product-only shot: {check['evidence']}"
        )
        assert check["severity"] == "hard"
