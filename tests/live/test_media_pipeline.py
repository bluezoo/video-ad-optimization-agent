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

"""Live media-generation pipeline tests (Phase 16 Task 12, stage 5).

Runs the REAL two-stage pipeline (Gemini image → Veo 3.1 animation) once per
archetype path — wearable (fashion, human model) and non-wearable
(consumable-hero, product-centric) — by calling the tool function directly
(agent routing is stage 3-4's job). Asserts the tool CONTRACT, not 200s:

- ``status == "success"``, video lands under ``LOCAL_ASSETS_DIR/generated/``
  and is >100KB;
- the ``campaign_videos`` row carries the success status (``generated``);
- ``reference_image_used`` is honest per whether the product image actually
  exists locally;
- local-first URL policy (open item 2): no ``storage.googleapis.com``
  anywhere in the serialized result (assertion shape from
  tests/unit/test_url_policy.py);
- actual image resolution + video duration/fps/size are printed to the test
  log AND merged into ``calibration/media-metadata.json`` (Q14/Q15 evidence,
  open item 5).

Each test registers its outputs in the session-scoped ``generated_media``
registry so Task 14's judge tests reuse the media instead of regenerating.
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import app.config as config
from app.database.db import get_db_cursor
from app.tools.video_tools import generate_video_from_product

pytestmark = [pytest.mark.live, pytest.mark.slow, pytest.mark.veo]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Committed Q14/Q15 evidence file (media resolution / duration / fps).
CALIBRATION_FILE = (
    REPO_ROOT
    / ".docs"
    / "version2-plan"
    / "working-docs"
    / "16-live-api-testing"
    / "calibration"
    / "media-metadata.json"
)

# Veo accepts 4/6/8s; 4s keeps the live tier's per-run wall time and cost down.
REQUESTED_DURATION = 4


# ---------------------------------------------------------------------------
# Media introspection helpers (evidence, not assertions)
# ---------------------------------------------------------------------------


def _repo_relative(path: str) -> str:
    """Repo-relative path for the committed evidence file (checkout-portable)."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path


def _probe_video(path: str) -> dict:
    """Actual video properties via ffprobe (present on the live-tier machine).

    Falls back to size-only if ffprobe is unavailable — the evidence file
    then says so instead of inventing numbers.
    """
    props: dict = {"path": _repo_relative(path), "bytes": os.path.getsize(path)}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        props["note"] = "ffprobe unavailable — resolution/duration/fps not recorded"
        return props
    out = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    num, den = stream["avg_frame_rate"].split("/")
    props.update(
        {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "fps": round(int(num) / int(den), 3) if int(den) else None,
            "frames": int(stream["nb_frames"]) if stream.get("nb_frames") else None,
            "duration_seconds": round(float(data["format"]["duration"]), 3),
        }
    )
    return props


def _image_size(path: str) -> dict:
    """Actual image resolution (PIL if present, PNG header fallback)."""
    props: dict = {"path": _repo_relative(path), "bytes": os.path.getsize(path)}
    try:
        from PIL import Image

        with Image.open(path) as im:
            props.update({"width": im.width, "height": im.height, "format": im.format})
        return props
    except ImportError:
        pass
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        props.update(
            {
                "width": int.from_bytes(head[16:20], "big"),
                "height": int.from_bytes(head[20:24], "big"),
                "format": "PNG",
            }
        )
    else:
        props["note"] = "PIL unavailable and not a PNG — resolution not recorded"
    return props


def _record_media_metadata(key: str, entry: dict) -> None:
    """Merge one pipeline's evidence into the committed calibration file."""
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(CALIBRATION_FILE.read_text()) if CALIBRATION_FILE.exists() else {}
    data[key] = entry
    CALIBRATION_FILE.write_text(json.dumps(data, indent=2) + "\n")
    # Also into the test log — the committed file is the durable evidence,
    # the log is where a human watching the run sees it.
    print(f"\n[media-metadata:{key}] {json.dumps(entry, indent=2)}")


def _assert_pipeline_contract(result: dict, *, product_image_filename: str) -> dict:
    """Shared tool-contract assertions; returns the video sub-dict."""
    assert result["status"] == "success", f"pipeline failed: {result}"

    # Local-first URL policy (open item 2) — same shape as tests/unit/test_url_policy.py.
    assert "storage.googleapis.com" not in json.dumps(result)

    video = result["video"]
    video_path = video["video_path"]
    assert Path(video_path).parent == Path(config.GENERATED_DIR), (
        f"video not under LOCAL_ASSETS_DIR/generated/: {video_path}"
    )
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 100_000, (
        f"video suspiciously small: {os.path.getsize(video_path)} bytes"
    )

    # reference_image_used must be HONEST per local reality (independent check,
    # not routed through the same storage helper the tool used).
    reference_exists = os.path.exists(
        os.path.join(config.PRODUCT_IMAGES_DIR, product_image_filename)
    )
    assert result["reference_image_used"] is reference_exists
    if not reference_exists:
        assert "warning" in result  # tool must disclose text-only generation

    # DB row updated to the pipeline's success status ('generated' — metrics
    # and 'active' only happen at HITL activation, by design).
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM campaign_videos WHERE id = ?", (video["id"],))
        row = cursor.fetchone()
    assert row is not None
    assert row["status"] == "generated"
    assert row["video_filename"] == video["video_filename"]

    return video


# ---------------------------------------------------------------------------
# Tests — one real run per archetype path
# ---------------------------------------------------------------------------


class TestLiveMediaPipeline:
    async def test_wearable_two_stage_pipeline(self, generated_media):
        """Seeded fashion product → wearable archetype, fashion-style filename."""
        # blue-floral-maxi-dress (product 4, category 'dress' → wearable) on
        # its own seeded campaign 1. Default variation keeps the fashion-era
        # 'default-elegant' name — the wearable path does NOT rename it.
        result = await generate_video_from_product(
            campaign_id=1,
            product_id=4,
            variation=None,
            duration_seconds=REQUESTED_DURATION,
        )
        video = _assert_pipeline_contract(
            result, product_image_filename="blue-floral-maxi-dress.png"
        )

        # Fashion-style filename: product name + date + wearable variation name.
        assert video["video_filename"].startswith("blue-floral-maxi-dress-")
        assert video["video_filename"].endswith("-default-elegant.mp4")
        assert video["variation"] == "default-elegant"

        # Wearable archetype KEEPS model-only fields in stored variation params.
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT variation_params FROM campaign_videos WHERE id = ?", (video["id"],)
            )
            params = json.loads(cursor.fetchone()["variation_params"])
        assert "model_ethnicity" in params

        thumbnail_path = video["thumbnail_path"]
        assert os.path.exists(thumbnail_path)
        _record_media_metadata(
            "wearable_pipeline",
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "product": "blue-floral-maxi-dress",
                "product_id": 4,
                "campaign_id": 1,
                "archetype": "wearable",
                "models": {"image": config.IMAGE_GENERATION, "video": config.VIDEO_GEN_MODEL},
                "requested_duration_seconds": REQUESTED_DURATION,
                "generation_time_seconds": video["generation_time_seconds"],
                "reference_image_used": result["reference_image_used"],
                "scene_image": _image_size(thumbnail_path),
                "video": _probe_video(video["video_path"]),
            },
        )

        context = (
            "Fashion video ad for the blue-floral-maxi-dress: human model wearing "
            "the dress; elegant mood, studio setting, cinematic style (default-elegant)."
        )
        generated_media["wearable_video"] = {
            "kind": "video",
            "path": video["video_path"],
            "archetype": "wearable",
            "request_context": context,
        }
        generated_media["wearable_scene_image"] = {
            "kind": "image",
            "path": thumbnail_path,
            "archetype": "wearable",
            "request_context": context,
        }

    async def test_non_wearable_two_stage_pipeline(self, generated_media):
        """Retail-core product (cold brew) → product-centric path, no human model."""
        # aurora-cold-brew-330ml (product 23, category 'beverage' →
        # consumable-hero). An ethnicity-led variation name exercises the
        # product-centric rename: '{category}-{setting}-{mood}'.
        result = await generate_video_from_product(
            campaign_id=4,
            product_id=23,
            variation={
                "name": "diverse-cafe-vibrant",
                "model_ethnicity": "diverse",
                "setting": "cafe",
                "mood": "vibrant",
            },
            duration_seconds=REQUESTED_DURATION,
        )
        video = _assert_pipeline_contract(
            result, product_image_filename="aurora-cold-brew-330ml.png"
        )

        # Product-centric filename: category-led variation name, no ethnicity.
        assert video["variation"] == "beverage-cafe-vibrant"
        assert video["video_filename"].startswith("aurora-cold-brew-330ml-")
        assert video["video_filename"].endswith("-beverage-cafe-vibrant.mp4")

        # Non-wearable archetypes DROP model-only fields from stored params
        # (ws16 Task 11 contract).
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT variation_params FROM campaign_videos WHERE id = ?", (video["id"],)
            )
            params = json.loads(cursor.fetchone()["variation_params"])
        assert "model_ethnicity" not in params
        assert "activity" not in params

        thumbnail_path = video["thumbnail_path"]
        assert os.path.exists(thumbnail_path)
        _record_media_metadata(
            "non_wearable_pipeline",
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "product": "aurora-cold-brew-330ml",
                "product_id": 23,
                "campaign_id": 4,
                "archetype": "consumable-hero",
                "models": {"image": config.IMAGE_GENERATION, "video": config.VIDEO_GEN_MODEL},
                "requested_duration_seconds": REQUESTED_DURATION,
                "generation_time_seconds": video["generation_time_seconds"],
                "reference_image_used": result["reference_image_used"],
                "scene_image": _image_size(thumbnail_path),
                "video": _probe_video(video["video_path"]),
            },
        )

        context = (
            "Product-hero video ad for the aurora-cold-brew-330ml canned coffee: "
            "product is the hero, NO humans; vibrant mood, cafe setting."
        )
        generated_media["non_wearable_video"] = {
            "kind": "video",
            "path": video["video_path"],
            "archetype": "consumable-hero",
            "request_context": context,
        }
        generated_media["non_wearable_scene_image"] = {
            "kind": "image",
            "path": thumbnail_path,
            "archetype": "consumable-hero",
            "request_context": context,
        }
