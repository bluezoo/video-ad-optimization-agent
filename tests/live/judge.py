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

"""Gemini multimodal judge for generated media (Phase 16 Task 14, stage 6).

A rubric reviewer, NOT a generator. Given a generated image/video and the
archetype + request context it was made for, it asks ``config.MODEL``
(gemini-3.6-flash on Vertex, global endpoint) whether the media obeys the
repo's ad-style policy, and returns a structured per-check verdict.

The rubric is derived from the code that produces the media, so judge and
generator can never silently drift:

- subject expectation from the archetype registry
  (``app/tools/prompt_archetypes.py``): the ``wearable`` archetype must show
  a human model wearing the garment; every other archetype is product-centric
  (the product is the hero, no humans);
- the no-rendered-text policy from ``app/tools/prompt_builders.py``'s
  ``_NO_TEXT_BLOCK`` / ``_AUDIO_BLOCK`` (owner directive, ws09): all ads are
  music-only with a clean frame — no rendered text/graphics beyond text that
  is physically part of the product's own packaging.

Honesty bounds (no over-claiming): the judge reviews **pixels only**. For
videos it checks visible frames for burned-in captions; it does NOT verify
audio (music-only / no-voiceover is enforced by the prompt policy, not
observed here). The rubric text says so explicitly.

Verdict shape (``JudgeVerdict``): a dict keyed by check name, each value
``{"verdict": "pass"|"fail", "severity": "hard"|"warn", "evidence": str}``.
The model returns verdict + one-line evidence per check; severity is pinned
by this module (the generator's policy decides what blocks vs warns), not by
the model.

The chart judge (``judge_chart``) applies the INVERTED rubric: an RPI
comparison chart is a data visualization, so legible axis/label/value text is
REQUIRED and the bar count must match the seeded creative count.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

import app.config as config
from app.tools.prompt_archetypes import WEARABLE
from app.tools.prompt_builders import _AUDIO_BLOCK, _NO_TEXT_BLOCK

# A verdict is a mapping check-name -> {verdict, severity, evidence}.
JudgeVerdict = dict[str, dict[str, str]]


# ---------------------------------------------------------------------------
# Structured-output schemas (what the model returns per media type)
# ---------------------------------------------------------------------------


class _Check(BaseModel):
    """One rubric check as the model reports it (severity is added by us)."""

    verdict: Literal["pass", "fail"]
    evidence: str


class _ImageJudgment(BaseModel):
    subject_matches_archetype: _Check
    no_rendered_text: _Check
    setting_mood_plausible: _Check


class _VideoJudgment(BaseModel):
    subject_matches_archetype: _Check
    no_rendered_text: _Check
    setting_mood_plausible: _Check
    no_captions_any_frame: _Check


class _ChartJudgment(BaseModel):
    axes_and_labels_legible: _Check
    correct_creative_count: _Check


# Severity is a policy decision owned by this module (phase-doc open question 1
# default; the owner ratifies the split at the Task 14 gate). "hard" fails a
# test; "warn" only surfaces a warning.
_IMAGE_SEVERITY = {
    "subject_matches_archetype": "hard",
    "no_rendered_text": "hard",
    "setting_mood_plausible": "warn",
}
_VIDEO_SEVERITY = {**_IMAGE_SEVERITY, "no_captions_any_frame": "hard"}
_CHART_SEVERITY = {
    "axes_and_labels_legible": "hard",
    "correct_creative_count": "hard",
}


# ---------------------------------------------------------------------------
# Rubric text (derived from the generator's own source)
# ---------------------------------------------------------------------------


def _subject_rule(archetype: str) -> str:
    """The subject expectation the archetype implies (prompt_archetypes.py)."""
    if archetype == WEARABLE:
        return (
            "A human model is clearly wearing and presenting the garment. The "
            "model and the worn product together are the subject of the shot."
        )
    return (
        "The product itself is the sole hero of the frame. There are NO humans "
        "anywhere — no models, no faces, no hands, no people in the background."
    )


_JSON_INSTRUCTION = (
    "Return ONLY a JSON object matching the provided schema. For every check, "
    "set verdict to \"pass\" or \"fail\" and give a single concrete sentence of "
    "visual evidence for that verdict (name what you actually see)."
)


def _ad_rubric(archetype: str, request_context: str, *, is_video: bool) -> str:
    """Prompt text for judging an ad image or video against the ad policy."""
    caption_check = ""
    if is_video:
        caption_check = (
            "\n- no_captions_any_frame: Scan EVERY visible frame. Fail if ANY "
            "frame shows burned-in captions, subtitles, titles, lower-thirds, "
            "badges, or graphic text overlays (product-packaging text is still "
            "the only allowed exception). Judge the frames only; you are NOT "
            "verifying audio."
        )
    medium = "video ad" if is_video else "scene image (first frame of a video ad)"
    return f"""You are a strict quality reviewer for AI-generated retail {medium}s.

The ad was generated for this request context:
"{request_context}"

The generator follows this fixed ad-style policy:

{_NO_TEXT_BLOCK}

{_AUDIO_BLOCK}

Evaluate these checks against what is actually visible in the media:

- subject_matches_archetype: {_subject_rule(archetype)}
- no_rendered_text: No rendered text, words, numbers, labels, badges, captions,
  watermarks, or graphic overlays anywhere in the frame. The ONLY allowed text
  is text that is physically part of the product's own packaging or label.
- setting_mood_plausible: The setting, styling, and mood plausibly match the
  request context above.{caption_check}

{_JSON_INSTRUCTION}"""


def _chart_rubric(expected_creative_count: int, campaign_name: str, request_context: str) -> str:
    """Inverted rubric: a data chart REQUIRES legible text."""
    return f"""You are reviewing a data-visualization chart (a matplotlib bar
chart), NOT an ad. Unlike ad creatives, a chart MUST contain clear, legible
text — this is the opposite of the ad no-text rule.

The chart is an RPI (revenue-per-impression) comparison across the activated
creatives of campaign "{campaign_name}". Context: {request_context}

Evaluate these checks against what is actually visible:

- axes_and_labels_legible: The chart has legible text — a title, a labeled Y
  axis for revenue per impression (dollars), readable X-axis creative labels,
  and a value label on each bar. Fail if any of these are missing or
  unreadable.
- correct_creative_count: The chart shows exactly {expected_creative_count}
  bars (one per activated creative). Fail if the number of bars differs.

{_JSON_INSTRUCTION}"""


# ---------------------------------------------------------------------------
# genai plumbing
# ---------------------------------------------------------------------------


def _generate(schema: type[BaseModel], parts: list) -> BaseModel:
    """One structured multimodal call to config.MODEL; parse into ``schema``."""
    client = genai.Client()
    response = client.models.generate_content(
        model=config.MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return schema.model_validate_json(response.text)


def _assemble(judgment: BaseModel, severity: dict[str, str]) -> JudgeVerdict:
    """Attach the module-owned severity to each model-reported check."""
    verdict: JudgeVerdict = {}
    for name, sev in severity.items():
        check: _Check = getattr(judgment, name)
        verdict[name] = {
            "verdict": check.verdict,
            "severity": sev,
            "evidence": check.evidence,
        }
    return verdict


def _sample_frames(path: str, count: int = 4) -> list[bytes]:
    """Evenly-spaced PNG frames via ffmpeg — the video-input fallback path.

    Only used if the direct-mp4 input is refused by the API (size/format).
    Requires ffmpeg (present on the live-tier machine, same as ffprobe in
    tests/live/test_media_pipeline.py).
    """
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg/ffprobe unavailable — cannot sample frames")

    duration = float(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )

    frames: list[bytes] = []
    # Sample at the midpoints of ``count`` equal slices (avoids the black
    # first/last frame). e.g. count=4 -> 12.5%, 37.5%, 62.5%, 87.5%.
    for i in range(count):
        ts = duration * (i + 0.5) / count
        out = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", f"{ts:.3f}", "-i", path,
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
            capture_output=True, check=True,
        )
        frames.append(out.stdout)
    return frames


# ---------------------------------------------------------------------------
# Public judge API
# ---------------------------------------------------------------------------


def judge_image(path: str, *, archetype: str, request_context: str) -> JudgeVerdict:
    """Judge a generated scene/product image against the ad rubric."""
    image_bytes = Path(path).read_bytes()
    part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    prompt = _ad_rubric(archetype, request_context, is_video=False)
    judgment = _generate(_ImageJudgment, [part, prompt])
    return _assemble(judgment, _IMAGE_SEVERITY)


def judge_video(path: str, *, archetype: str, request_context: str) -> JudgeVerdict:
    """Judge a generated video against the ad rubric.

    Tries direct mp4-bytes input first (proven in app/tools/video_tools.py's
    analyze_video); if the API refuses on size/format, falls back to judging
    4 evenly-spaced sampled frames. Prints which input mode was used.
    """
    prompt = _ad_rubric(archetype, request_context, is_video=True)
    video_bytes = Path(path).read_bytes()
    try:
        part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
        judgment = _generate(_VideoJudgment, [part, prompt])
        print(f"[judge] video input mode: direct-mp4 ({path})")
    except genai.errors.APIError as exc:
        print(f"[judge] direct-mp4 refused ({exc}); falling back to sampled frames")
        frame_parts = [
            types.Part.from_bytes(data=frame, mime_type="image/png")
            for frame in _sample_frames(path, 4)
        ]
        frame_note = (
            "\n\nThe following are 4 evenly-spaced sampled frames from the "
            "video (in order). Judge no_captions_any_frame across all of them."
        )
        judgment = _generate(_VideoJudgment, [*frame_parts, prompt + frame_note])
        print(f"[judge] video input mode: sampled-frames ({path})")
    return _assemble(judgment, _VIDEO_SEVERITY)


def judge_chart(
    path: str,
    *,
    expected_creative_count: int,
    campaign_name: str,
    request_context: str,
) -> JudgeVerdict:
    """Judge an RPI comparison chart against the INVERTED (text-required) rubric."""
    image_bytes = Path(path).read_bytes()
    part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    prompt = _chart_rubric(expected_creative_count, campaign_name, request_context)
    judgment = _generate(_ChartJudgment, [part, prompt])
    return _assemble(judgment, _CHART_SEVERITY)


def judge_media_entry(entry: dict) -> JudgeVerdict:
    """Dispatch a ``generated_media`` registry entry to the right judge."""
    if entry["kind"] == "video":
        return judge_video(
            entry["path"],
            archetype=entry["archetype"],
            request_context=entry["request_context"],
        )
    return judge_image(
        entry["path"],
        archetype=entry["archetype"],
        request_context=entry["request_context"],
    )
