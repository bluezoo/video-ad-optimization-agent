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

"""API Gateway for the Video Ad Optimization Agent Web Application.

Provides a unified REST & programmatic API layer for a frontend UX to access:
- All 6 workflow steps depicted in `assets/use-case-poster.jpeg`:
  1. Discover Your AI Team (All Agents, campaigns, products, natural-language chat)
  2. Generate Creative at Scale (Media Agent, 15+ configurable video components:
     subjects/models, settings/environment, tone/mood/energy, lighting/visual style,
     camera movement/framing, props, audio, presets, live prompt preview, batch gen)
  3. You Stay in Control (Review Agent, HITL review table, pending queue, 1-click
     single & batch activation, pause, archive, extend metrics, Omni video edit)
  4. Measure What Matters (Analytics Agent, RPI, Dwell Time, Circulation,
     Impressions, Revenue, top performing ads, campaign insights, creative charts)
  5. See the Big Picture (Analytics Agent, Geographic Intelligence, heat maps,
     West Coast vs East Coast regional comparisons, Google Maps, demographics)
  6. Scale What Works (Media Agent, Winning Formula DNA extraction & cross-campaign
     application, e.g. applying video 5's formula to campaign 3)
- Dataset Explorer & Management:
  Browse, filter, search, and seed/reset all underlying datasets (`fashion_catalog`,
  `retail_core_catalog`, `products`, `campaigns`, `videos`, `video_metrics`,
  `video_attribution`, `ad_plays`, `audience_visits`, `demo_meta`, `legacy_ads`,
  and local/GCS `assets`).

Run locally with FastAPI/Uvicorn (if installed) or the built-in HTTP server:
    python -m app.api_gateway --port 8000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import random
import re
import sys
import types
from datetime import date, datetime, timedelta
from enum import Enum, IntEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field


def _ensure_numpy_fallback() -> None:
    """Provide a lightweight stdlib numpy shim if numpy is not installed."""
    try:
        import numpy  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    class _Array(list):
        def __mul__(self, other: float) -> _Array:
            return _Array(float(x) * float(other) for x in self)

        def __rmul__(self, other: float) -> _Array:
            return self.__mul__(other)

        def __truediv__(self, other: float) -> _Array:
            denom = float(other) if float(other) != 0.0 else 1.0
            return _Array(float(x) / denom for x in self)

        def sum(self) -> float:
            return float(sum(float(x) for x in self))

        def tolist(self) -> list[float]:
            return [float(x) for x in self]

    class _Generator:
        def __init__(self, seed: int) -> None:
            self._rng = random.Random(seed)

        def uniform(self, low: float = 0.0, high: float = 1.0) -> float:
            return self._rng.uniform(low, high)

        def choice(self, seq: Any) -> Any:
            return self._rng.choice(list(seq))

        def dirichlet(self, alpha: list[float]) -> _Array:
            samples = [self._rng.gammavariate(max(float(a), 0.001), 1.0) for a in alpha]
            total = sum(samples) or 1.0
            return _Array(s / total for s in samples)

    np_mod = types.ModuleType("numpy")
    rng_mod = types.ModuleType("numpy.random")
    rng_mod.Generator = _Generator  # type: ignore[attr-defined]
    rng_mod.default_rng = lambda seed=None: _Generator(int(seed or 0))  # type: ignore[attr-defined]
    np_mod.random = rng_mod  # type: ignore[attr-defined]
    np_mod.ndarray = _Array  # type: ignore[attr-defined]
    np_mod.zeros = lambda n: _Array(0.0 for _ in range(int(n)))  # type: ignore[attr-defined]
    np_mod.array = lambda seq: _Array(float(x) for x in seq)  # type: ignore[attr-defined]
    sys.modules["numpy"] = np_mod
    sys.modules["numpy.random"] = rng_mod


_ensure_numpy_fallback()

from app.config import (  # noqa: E402
    APP_MODE,
    DEMO_DATASET,
    ENABLE_OMNI_EDIT,
    GCS_BUCKET,
    IMAGE_GENERATION as IMAGE_GENERATION_MODEL,
    LOCAL_ASSETS_DIR,
    MODEL as AGENT_MODEL,
    OMNI_EDIT_MODEL,
    VIDEO_GEN_MODEL,
    DemoDataset,
)
from app.database.db import (  # noqa: E402
    get_db_cursor,
    init_database,
    insert_product,
    reset_database,
)
from app.database.mock_data import populate_mock_data, seed_demo_data  # noqa: E402
from app.database.products_data import PRODUCTS as PRODUCTS_DATA  # noqa: E402
from app.database.retail_products_data import RETAIL_TEST_PRODUCTS as RETAIL_PRODUCTS_DATA  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.variation import (  # noqa: E402
    CreativeVariation,
    PRESET_VARIATIONS as RAW_PRESET_VARIATIONS,
)
from app.models.video_properties import (  # noqa: E402
    MoodType,
    VideoProperties as CoreVideoProperties,
)
from app.storage import get_public_url  # noqa: E402
from app.tools.campaign_tools import (  # noqa: E402
    CAMPAIGN_CATEGORIES,
    create_campaign,
    get_campaign,
    list_campaigns,
    update_campaign,
)
from app.tools.metrics_tools import (  # noqa: E402
    compare_campaigns,
    compare_creatives_within_campaign,
    generate_creative_comparison_chart,
    get_campaign_insights,
    get_campaign_metrics,
    get_top_performing_ads,
)
from app.tools.review_tools import (  # noqa: E402
    activate_batch,
    activate_video,
    archive_video,
    generate_additional_metrics,
    get_activation_summary,
    get_video_details,
    get_video_review_table,
    get_video_status,
    list_pending_videos,
    pause_video,
)

# Storage bucket constants & helpers
BUCKET_PRODUCT_IMAGES = "product-images"
BUCKET_SELECTED = "selected"
BUCKET_GENERATED = "generated"


def resolve_asset_path(bucket: str, filename: str) -> Path:
    """Resolve local filesystem path for an asset in `bucket`."""
    return Path(LOCAL_ASSETS_DIR) / bucket / filename


def to_public_url(bucket: str, filename: str) -> str:
    """Return public URL (or `/assets/...` path) for a bucket and filename."""
    return get_public_url(f"{bucket}/{filename}")


# Product category & presentation mode constants
FASHION_CATEGORIES: tuple[str, ...] = (
    "fashion",
    "dress",
    "pants",
    "skirt",
    "top",
    "outerwear",
)

CATEGORY_DEFAULT_PRESENTATION: dict[str, str] = {
    "fashion": "model",
    "dress": "model",
    "pants": "model",
    "skirt": "model",
    "top": "model",
    "outerwear": "model",
    "footwear": "model",
    "beverage": "lifestyle",
    "qsr-menu-item": "lifestyle",
    "beauty": "lifestyle",
    "grocery": "lifestyle",
    "electronics": "product-hero",
    "automotive": "product-hero",
    "home-improvement": "product-hero",
    "homeware": "product-hero",
}

VALID_CATEGORIES: set[str] = set(CATEGORY_DEFAULT_PRESENTATION.keys())
VALID_PRESENTATION_MODES: tuple[str, ...] = ("model", "lifestyle", "product-hero")


# Configurable video component Enums & descriptions for UX controls
class ModelEthnicity(str, Enum):
    ASIAN = "asian"
    EUROPEAN = "european"
    LATINA = "latina"
    BLACK = "black"
    SOUTH_ASIAN = "south_asian"
    MIDDLE_EASTERN = "middle_eastern"
    DIVERSE = "diverse"


class Setting(str, Enum):
    BEACH = "beach"
    URBAN = "urban"
    CAFE = "cafe"
    ROOFTOP = "rooftop"
    STUDIO = "studio"
    PARK = "park"
    GARDEN = "garden"
    STREET = "street"
    BOUTIQUE = "boutique"


class TimeOfDay(str, Enum):
    GOLDEN_HOUR = "golden_hour"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    SUNSET = "sunset"
    BLUE_HOUR = "blue_hour"
    NIGHT = "night"


class Mood(str, Enum):
    ROMANTIC = "romantic"
    CONFIDENT = "confident"
    PLAYFUL = "playful"
    SERENE = "serene"
    ENERGETIC = "energetic"
    SOPHISTICATED = "sophisticated"
    MYSTERIOUS = "mysterious"
    JOYFUL = "joyful"


class Lighting(str, Enum):
    NATURAL_SOFT = "natural_soft"
    GOLDEN_BACKLIGHT = "golden_backlight"
    DRAMATIC_SIDE = "dramatic_side"
    BRIGHT_EVEN = "bright_even"
    DAPPLED = "dappled"
    NEON_AMBIENT = "neon_ambient"
    STUDIO_THREE_POINT = "studio_three_point"


class CameraMovement(str, Enum):
    ORBIT = "orbit"
    PAN = "pan"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACKING = "tracking"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    STATIC = "static"
    HANDHELD = "handheld"
    ZOOM = "zoom"


class Activity(str, Enum):
    WALKING = "walking"
    STANDING = "standing"
    SITTING = "sitting"
    DANCING = "dancing"
    SPINNING = "spinning"
    POSING = "posing"


class CameraAngle(str, Enum):
    EYE_LEVEL = "eye_level"
    LOW_ANGLE = "low_angle"
    HIGH_ANGLE = "high_angle"
    DUTCH_ANGLE = "dutch_angle"
    OVERHEAD = "overhead"


class AspectRatio(str, Enum):
    PORTRAIT_9_16 = "9:16"
    LANDSCAPE_16_9 = "16:9"
    SQUARE_1_1 = "1:1"


class SettingType(str, Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    STUDIO = "studio"
    URBAN = "urban"
    NATURE = "nature"
    BEACH = "beach"
    ARCHITECTURAL = "architectural"


class WeatherCondition(str, Enum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    OVERCAST = "overcast"
    RAINY = "rainy"
    WINDY = "windy"
    FOGGY = "foggy"


class SubjectCount(str, Enum):
    NONE = "none"
    SINGLE = "single"
    COUPLE = "couple"
    GROUP = "group"


class MovementAmount(str, Enum):
    STATIC = "static"
    MINIMAL = "minimal"
    MODERATE = "moderate"
    HIGH = "high"


class MoodIntensity(str, Enum):
    SUBTLE = "subtle"
    MODERATE = "moderate"
    INTENSE = "intense"


class ColorSaturation(str, Enum):
    MUTED = "muted"
    NATURAL = "natural"
    VIBRANT = "vibrant"
    HYPER_SATURATED = "hyper_saturated"


class EnergyLevel(str, Enum):
    CALM = "calm"
    MODERATE = "moderate"
    DYNAMIC = "dynamic"
    HIGH_ENERGY = "high_energy"


class LightingStyle(str, Enum):
    NATURAL = "natural"
    GOLDEN_HOUR = "golden_hour"
    DRAMATIC = "dramatic"
    SOFT_DIFFUSED = "soft_diffused"
    HIGH_KEY = "high_key"
    LOW_KEY = "low_key"
    BACKLIT = "backlit"
    NEON = "neon"


class ColorTemperature(str, Enum):
    WARM = "warm"
    NEUTRAL = "neutral"
    COOL = "cool"
    VIBRANT = "vibrant"
    DESATURATED = "desaturated"


class VisualStyle(str, Enum):
    CINEMATIC = "cinematic"
    EDITORIAL = "editorial"
    COMMERCIAL = "commercial"
    LIFESTYLE = "lifestyle"
    ARTISTIC = "artistic"
    DOCUMENTARY = "documentary"
    RETRO = "retro"


class AudioType(str, Enum):
    SILENT = "silent"
    MUSIC = "music"
    AMBIENT = "ambient"
    VOICEOVER = "voiceover"
    FULL_MIX = "full_mix"


class MusicTempo(str, Enum):
    SLOW = "slow"
    MEDIUM = "medium"
    UPBEAT = "upbeat"
    DYNAMIC = "dynamic"


ETHNICITY_DESCRIPTIONS: dict[ModelEthnicity, str] = {
    ModelEthnicity.ASIAN: "East Asian fashion model with poised editorial presence",
    ModelEthnicity.EUROPEAN: "European fashion model with classic continental styling",
    ModelEthnicity.LATINA: "Latina fashion model with vibrant, expressive presence",
    ModelEthnicity.BLACK: "Black fashion model with radiant, confident presence",
    ModelEthnicity.SOUTH_ASIAN: "South Asian fashion model with graceful elegance",
    ModelEthnicity.MIDDLE_EASTERN: "Middle Eastern fashion model with refined sophistication",
    ModelEthnicity.DIVERSE: "Diverse cast of contemporary models",
}

SETTING_DESCRIPTIONS: dict[Setting, str] = {
    Setting.BEACH: "sunlit coastal beach with gentle ocean waves and warm sand",
    Setting.URBAN: "modern metropolitan downtown street with architectural lines",
    Setting.CAFE: "sun-drenched artisan cafe with warm wood and marble tables",
    Setting.ROOFTOP: "elevated city rooftop terrace overlooking a skyline",
    Setting.STUDIO: "minimalist high-fashion photography studio with clean backdrop",
    Setting.PARK: "lush city park with tree-lined pathways and natural greenery",
    Setting.GARDEN: "blooming botanical garden with manicured florals",
    Setting.STREET: "vibrant boutique shopping avenue with cobblestone texture",
    Setting.BOUTIQUE: "upscale luxury retail boutique interior",
}

TIME_DESCRIPTIONS: dict[TimeOfDay, str] = {
    TimeOfDay.GOLDEN_HOUR: "warm golden hour sunlight just before sunset",
    TimeOfDay.MORNING: "crisp, fresh morning daylight",
    TimeOfDay.MIDDAY: "bright, clear midday sun",
    TimeOfDay.AFTERNOON: "warm late-afternoon light",
    TimeOfDay.SUNSET: "rich sunset glow with amber and magenta sky tones",
    TimeOfDay.BLUE_HOUR: "atmospheric twilight blue hour with city lights",
    TimeOfDay.NIGHT: "cinematic nighttime ambiance with illuminated city glow",
}

MOOD_DESCRIPTIONS: dict[Mood, str] = {
    Mood.ROMANTIC: "dreamy, romantic, soft and emotionally evocative",
    Mood.CONFIDENT: "bold, empowered, self-assured and commanding",
    Mood.PLAYFUL: "lighthearted, spontaneous, charming and fun",
    Mood.SERENE: "calm, peaceful, balanced and effortlessly tranquil",
    Mood.ENERGETIC: "dynamic, vibrant, high-energy and upbeat",
    Mood.SOPHISTICATED: "refined, luxurious, polished editorial elegance",
    Mood.MYSTERIOUS: "intriguing, moody, cinematic and alluring",
    Mood.JOYFUL: "radiant, celebratory, warm and uplifting",
}

LIGHTING_DESCRIPTIONS: dict[Lighting, str] = {
    Lighting.NATURAL_SOFT: "soft diffused natural daylight",
    Lighting.GOLDEN_BACKLIGHT: "warm golden rim backlighting with subtle lens flare",
    Lighting.DRAMATIC_SIDE: "high-contrast directional side lighting",
    Lighting.BRIGHT_EVEN: "clean, bright, even commercial illumination",
    Lighting.DAPPLED: "dappled sunlight filtering through foliage",
    Lighting.NEON_AMBIENT: "colorful neon and urban ambient reflections",
    Lighting.STUDIO_THREE_POINT: "precision three-point studio key, fill, and rim lighting",
}

CAMERA_DESCRIPTIONS: dict[CameraMovement, str] = {
    CameraMovement.ORBIT: "smooth 360-degree orbital camera movement around the subject",
    CameraMovement.PAN: "fluid horizontal camera pan across the scene",
    CameraMovement.DOLLY_IN: "slow cinematic dolly push-in toward the subject",
    CameraMovement.DOLLY_OUT: "gradual dolly pull-back revealing the full environment",
    CameraMovement.TRACKING: "dynamic tracking shot following the subject's motion",
    CameraMovement.CRANE_UP: "sweeping crane movement rising upward",
    CameraMovement.CRANE_DOWN: "graceful crane movement descending toward eye level",
    CameraMovement.STATIC: "locked-off static editorial framing",
    CameraMovement.HANDHELD: "subtle organic handheld motion",
    CameraMovement.ZOOM: "smooth optical zoom framing",
}

ACTIVITY_DESCRIPTIONS: dict[Activity, str] = {
    Activity.WALKING: "walking naturally with fluid movement",
    Activity.STANDING: "standing in a poised editorial stance",
    Activity.SITTING: "sitting relaxed and engaging with the scene",
    Activity.DANCING: "moving rhythmically with joyful motion",
    Activity.SPINNING: "gently turning to showcase the product's drape and movement",
    Activity.POSING: "transitioning smoothly between high-fashion poses",
}


class VideoVariation(BaseModel):
    """Structured video variation configuration for Stage 1 & Stage 2 prompt generation."""

    model_ethnicity: ModelEthnicity = ModelEthnicity.DIVERSE
    setting: Setting = Setting.STUDIO
    time_of_day: TimeOfDay = TimeOfDay.GOLDEN_HOUR
    mood: Mood = Mood.CONFIDENT
    lighting: Lighting = Lighting.NATURAL_SOFT
    camera_movement: CameraMovement = CameraMovement.DOLLY_IN
    activity: Activity = Activity.WALKING
    props: list[str] = Field(default_factory=list)
    color_grading: str = "warm"
    aspect_ratio: str = "9:16"
    duration_seconds: int = 8

    @property
    def variation_name(self) -> str:
        return f"{self.model_ethnicity.value}_{self.setting.value}_{self.mood.value}"

    def to_filename_suffix(self) -> str:
        return f"{self.model_ethnicity.value}-{self.setting.value}-{self.time_of_day.value}-{self.mood.value}".replace(
            "_", "-"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_ethnicity": self.model_ethnicity.value,
            "setting": self.setting.value,
            "time_of_day": self.time_of_day.value,
            "mood": self.mood.value,
            "lighting": self.lighting.value,
            "camera_movement": self.camera_movement.value,
            "activity": self.activity.value,
            "props": list(self.props),
            "color_grading": self.color_grading,
            "aspect_ratio": self.aspect_ratio,
            "duration_seconds": self.duration_seconds,
        }


class VideoProperties(BaseModel):
    """Extended video properties model for UX inspection and prompt modifiers."""

    subject_count: SubjectCount = SubjectCount.SINGLE
    model_ethnicity: str | None = "diverse"
    model_description: str | None = None
    garment_visibility: str = "full"
    has_multiple_outfits: bool = False
    setting_type: SettingType = SettingType.OUTDOOR
    location_detail: str | None = None
    time_of_day: str = "golden_hour"
    weather: WeatherCondition | None = WeatherCondition.SUNNY
    season: str | None = None
    background_complexity: str = "moderate"
    camera_movement: str = "dolly_in"
    camera_angle: CameraAngle = CameraAngle.EYE_LEVEL
    movement_amount: MovementAmount = MovementAmount.MODERATE
    energy_level: EnergyLevel = EnergyLevel.MODERATE
    lighting_style: LightingStyle = LightingStyle.NATURAL
    color_temperature: ColorTemperature = ColorTemperature.WARM
    color_saturation: ColorSaturation = ColorSaturation.NATURAL
    dominant_colors: list[str] = Field(default_factory=list)
    visual_style: VisualStyle = VisualStyle.CINEMATIC
    mood: str = "confident"
    mood_intensity: MoodIntensity = MoodIntensity.MODERATE
    has_warmth: bool = True
    audio_type: AudioType = AudioType.MUSIC
    music_tempo: MusicTempo | None = MusicTempo.MEDIUM
    audio_mood: str | None = "confident"
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    duration_seconds: int = 8
    has_text_overlays: bool = False
    has_brand_elements: bool = False
    style_tags: list[str] = Field(default_factory=list)
    notable_props: list[str] = Field(default_factory=list)

    def to_prompt_modifier(self) -> str:
        parts = [
            f"{self.visual_style.value} style",
            f"{self.mood} mood ({self.mood_intensity.value})",
            f"{self.lighting_style.value} lighting",
            f"{self.color_temperature.value} color temperature",
            f"{self.camera_movement} camera at {self.camera_angle.value}",
            f"{self.energy_level.value} energy",
        ]
        if self.notable_props:
            parts.append(f"props: {', '.join(self.notable_props)}")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


PRESET_VARIATIONS: dict[str, VideoVariation] = {
    "asian_beach_romantic": VideoVariation(
        model_ethnicity=ModelEthnicity.ASIAN,
        setting=Setting.BEACH,
        time_of_day=TimeOfDay.GOLDEN_HOUR,
        mood=Mood.ROMANTIC,
        lighting=Lighting.GOLDEN_BACKLIGHT,
        camera_movement=CameraMovement.TRACKING,
        activity=Activity.WALKING,
        props=["sunglasses"],
        color_grading="warm",
    ),
    "european_rooftop_sophisticated": VideoVariation(
        model_ethnicity=ModelEthnicity.EUROPEAN,
        setting=Setting.ROOFTOP,
        time_of_day=TimeOfDay.SUNSET,
        mood=Mood.SOPHISTICATED,
        lighting=Lighting.GOLDEN_BACKLIGHT,
        camera_movement=CameraMovement.DOLLY_IN,
        activity=Activity.STANDING,
        props=["champagne_flute"],
        color_grading="warm",
    ),
    "latina_urban_confident": VideoVariation(
        model_ethnicity=ModelEthnicity.LATINA,
        setting=Setting.URBAN,
        time_of_day=TimeOfDay.MORNING,
        mood=Mood.CONFIDENT,
        lighting=Lighting.NATURAL_SOFT,
        camera_movement=CameraMovement.TRACKING,
        activity=Activity.WALKING,
        props=["handbag", "sunglasses"],
        color_grading="vibrant",
    ),
    "black_cafe_warm": VideoVariation(
        model_ethnicity=ModelEthnicity.BLACK,
        setting=Setting.CAFE,
        time_of_day=TimeOfDay.AFTERNOON,
        mood=Mood.JOYFUL,
        lighting=Lighting.NATURAL_SOFT,
        camera_movement=CameraMovement.DOLLY_IN,
        activity=Activity.SITTING,
        props=["coffee_cup"],
        color_grading="warm",
    ),
    "south_asian_garden_serene": VideoVariation(
        model_ethnicity=ModelEthnicity.SOUTH_ASIAN,
        setting=Setting.GARDEN,
        time_of_day=TimeOfDay.GOLDEN_HOUR,
        mood=Mood.SERENE,
        lighting=Lighting.DAPPLED,
        camera_movement=CameraMovement.ORBIT,
        activity=Activity.SPINNING,
        props=["flowers"],
        color_grading="warm",
    ),
}


def build_stage1_image_prompt(variation: VideoVariation, product: dict[str, Any]) -> str:
    """Build Stage 1 (Gemini 3 Pro Image) customized scene prompt for fashion model mode."""
    eth_desc = ETHNICITY_DESCRIPTIONS.get(variation.model_ethnicity, variation.model_ethnicity.value)
    set_desc = SETTING_DESCRIPTIONS.get(variation.setting, variation.setting.value)
    time_desc = TIME_DESCRIPTIONS.get(variation.time_of_day, variation.time_of_day.value)
    light_desc = LIGHTING_DESCRIPTIONS.get(variation.lighting, variation.lighting.value)
    mood_desc = MOOD_DESCRIPTIONS.get(variation.mood, variation.mood.value)
    act_desc = ACTIVITY_DESCRIPTIONS.get(variation.activity, variation.activity.value)
    props_clause = f" Accented with {', '.join(variation.props)}." if variation.props else ""
    return (
        f"High-resolution commercial retail photography ({variation.aspect_ratio}): "
        f"{eth_desc} wearing {product.get('name', 'the featured garment')} "
        f"({product.get('color', '')} {product.get('material', '')} {product.get('style', '')}), "
        f"{act_desc} in a {set_desc} during {time_desc}. "
        f"Lighting: {light_desc}. Mood: {mood_desc}. Color grading: {variation.color_grading}.{props_clause} "
        "No text, watermarks, or logos."
    )


def build_stage2_video_prompt(variation: VideoVariation, product: dict[str, Any]) -> str:
    """Build Stage 2 (Veo 3.1) motion video prompt from the customized Stage 1 image."""
    cam_desc = CAMERA_DESCRIPTIONS.get(variation.camera_movement, variation.camera_movement.value)
    act_desc = ACTIVITY_DESCRIPTIONS.get(variation.activity, variation.activity.value)
    mood_desc = MOOD_DESCRIPTIONS.get(variation.mood, variation.mood.value)
    return (
        f"Cinematic {variation.duration_seconds}-second retail video ({variation.aspect_ratio}): "
        f"Camera executes a {cam_desc} while the subject is {act_desc}, showcasing the natural movement "
        f"and texture of {product.get('name', 'the product')}. "
        f"Atmosphere is {mood_desc} with {variation.color_grading} color grading. "
        "Smooth, realistic motion; no text overlays."
    )


def build_category_aware_prompts(
    variation: VideoVariation,
    product: dict[str, Any],
    presentation_mode: str = "model",
) -> tuple[str, str]:
    """Build Stage 1 and Stage 2 prompts adapted to `model`, `lifestyle`, or `product-hero` mode."""
    if presentation_mode == "model":
        return (
            build_stage1_image_prompt(variation, product),
            build_stage2_video_prompt(variation, product),
        )

    set_desc = SETTING_DESCRIPTIONS.get(variation.setting, variation.setting.value)
    time_desc = TIME_DESCRIPTIONS.get(variation.time_of_day, variation.time_of_day.value)
    light_desc = LIGHTING_DESCRIPTIONS.get(variation.lighting, variation.lighting.value)
    mood_desc = MOOD_DESCRIPTIONS.get(variation.mood, variation.mood.value)
    cam_desc = CAMERA_DESCRIPTIONS.get(variation.camera_movement, variation.camera_movement.value)
    props_clause = f" Styled with {', '.join(variation.props)}." if variation.props else ""

    if presentation_mode == "product-hero":
        stage1 = (
            f"Hero product commercial photography ({variation.aspect_ratio}): "
            f"Close-up showcase of {product.get('name', 'the product')} ({product.get('description', '')}) "
            f"set in a {set_desc} during {time_desc}. "
            f"Lighting: {light_desc}. Mood: {mood_desc}. Color grading: {variation.color_grading}.{props_clause} "
            "No human models, no text overlays."
        )
        stage2 = (
            f"Cinematic {variation.duration_seconds}-second product-hero video ({variation.aspect_ratio}): "
            f"{cam_desc} highlighting the craftsmanship, surface detail, and design of {product.get('name', 'the product')}. "
            f"Atmosphere is {mood_desc} with {variation.color_grading} tones."
        )
        return stage1, stage2

    # lifestyle mode
    eth_desc = ETHNICITY_DESCRIPTIONS.get(variation.model_ethnicity, variation.model_ethnicity.value)
    act_desc = ACTIVITY_DESCRIPTIONS.get(variation.activity, variation.activity.value)
    stage1 = (
        f"Lifestyle commercial photography ({variation.aspect_ratio}): "
        f"{eth_desc} naturally enjoying and interacting with {product.get('name', 'the product')} "
        f"({product.get('description', '')}) while {act_desc} in a {set_desc} during {time_desc}. "
        f"Lighting: {light_desc}. Mood: {mood_desc}.{props_clause} No text overlays."
    )
    stage2 = (
        f"Cinematic {variation.duration_seconds}-second lifestyle video ({variation.aspect_ratio}): "
        f"{cam_desc} capturing an authentic moment with {product.get('name', 'the product')} "
        f"in a {variation.setting.value} setting, {mood_desc} tone."
    )
    return stage1, stage2


# ============================================================================
# CONSTANTS & POSTER USE-CASE DEFINITIONS
# ============================================================================

GATEWAY_VERSION = "2.0.0"

REGION_BY_STATE: dict[str, str] = {
    "CA": "West Coast",
    "OR": "West Coast",
    "WA": "West Coast",
    "NV": "West Coast",
    "AZ": "West Coast",
    "NY": "East Coast",
    "NJ": "East Coast",
    "MA": "East Coast",
    "CT": "East Coast",
    "PA": "East Coast",
    "FL": "East Coast",
    "DC": "East Coast",
    "MD": "East Coast",
    "VA": "East Coast",
    "GA": "East Coast",
    "NC": "East Coast",
    "IL": "Midwest",
    "OH": "Midwest",
    "MI": "Midwest",
    "MN": "Midwest",
    "WI": "Midwest",
    "IN": "Midwest",
    "MO": "Midwest",
    "TX": "South",
    "TN": "South",
    "LA": "South",
    "CO": "Mountain",
    "UT": "Mountain",
}

CITY_COORDINATES: dict[tuple[str, str], tuple[float, float]] = {
    ("los angeles", "CA"): (34.0522, -118.2437),
    ("san francisco", "CA"): (37.7749, -122.4194),
    ("san diego", "CA"): (32.7157, -117.1611),
    ("new york", "NY"): (40.7128, -74.0060),
    ("chicago", "IL"): (41.8781, -87.6298),
    ("miami", "FL"): (25.7617, -80.1918),
    ("austin", "TX"): (30.2672, -97.7431),
    ("dallas", "TX"): (32.7767, -96.7970),
    ("seattle", "WA"): (47.6062, -122.3321),
    ("boston", "MA"): (42.3601, -71.0589),
    ("atlanta", "GA"): (33.7490, -84.3880),
}

CITY_DEMOGRAPHICS: dict[tuple[str, str], dict[str, Any]] = {
    ("los angeles", "CA"): {
        "population_estimate": "3.85M metro",
        "median_age": 36.2,
        "income_tier": "Upper-Middle to Affluent",
        "key_segments": ["Young Professionals", "Creative Industry", "Health & Lifestyle"],
        "recommended_creative_dna": {
            "setting": "beach",
            "time_of_day": "golden_hour",
            "mood": "romantic",
            "lighting": "golden_backlight",
        },
    },
    ("new york", "NY"): {
        "population_estimate": "8.34M metro",
        "median_age": 37.5,
        "income_tier": "Affluent Urban",
        "key_segments": ["Finance & Fashion Professionals", "Luxury Shoppers", "Urban Commuters"],
        "recommended_creative_dna": {
            "setting": "rooftop",
            "time_of_day": "sunset",
            "mood": "sophisticated",
            "lighting": "golden_backlight",
        },
    },
    ("chicago", "IL"): {
        "population_estimate": "2.66M metro",
        "median_age": 35.8,
        "income_tier": "Middle to Upper-Middle",
        "key_segments": ["Downtown Professionals", "Weekend Shoppers", "Suburban Visitors"],
        "recommended_creative_dna": {
            "setting": "urban",
            "time_of_day": "morning",
            "mood": "confident",
            "lighting": "natural_soft",
        },
    },
    ("miami", "FL"): {
        "population_estimate": "2.71M metro",
        "median_age": 40.1,
        "income_tier": "Affluent Resort & Urban",
        "key_segments": ["Resort & Beachgoers", "Nightlife & Dining", "International Tourists"],
        "recommended_creative_dna": {
            "setting": "beach",
            "time_of_day": "sunset",
            "mood": "energetic",
            "lighting": "golden_backlight",
        },
    },
}

SUGGESTED_PROPS: list[dict[str, str]] = [
    {"id": "sunglasses", "label": "Sunglasses", "description": "Designer eyewear accent"},
    {"id": "handbag", "label": "Leather Handbag", "description": "Structured luxury handbag"},
    {"id": "coffee_cup", "label": "Artisan Coffee Cup", "description": "Warm cafe lifestyle prop"},
    {"id": "flowers", "label": "Fresh Bouquet", "description": "Botanical romantic accent"},
    {"id": "shopping_bags", "label": "Boutique Bags", "description": "Retail shopping context"},
    {"id": "umbrella", "label": "Classic Umbrella", "description": "Urban weather/editorial prop"},
    {"id": "book", "label": "Hardcover Book", "description": "Relaxed cafe/park prop"},
    {"id": "bicycle", "label": "Vintage Bicycle", "description": "Street/park lifestyle prop"},
    {"id": "headphones", "label": "Wireless Headphones", "description": "Modern urban commuter prop"},
    {"id": "champagne_flute", "label": "Sparkling Glass", "description": "Rooftop evening prop"},
]

CATEGORY_PRESETS: dict[str, dict[str, Any]] = {
    "lifestyle_cafe_warm": {
        "presentation_mode": "lifestyle",
        "model_ethnicity": "diverse",
        "setting": "cafe",
        "time_of_day": "morning",
        "mood": "warm",
        "lighting": "natural_soft",
        "camera_movement": "dolly_in",
        "activity": "sitting",
        "description": "Person enjoying the product in a sunlit artisan cafe",
    },
    "product_hero_studio_dramatic": {
        "presentation_mode": "product-hero",
        "model_ethnicity": "diverse",
        "setting": "studio",
        "time_of_day": "midday",
        "mood": "sophisticated",
        "lighting": "studio_three_point",
        "camera_movement": "orbit",
        "activity": "standing",
        "description": "Hero product closeup on a sculptural pedestal with studio rim lighting",
    },
    "rooftop_sunset_editorial": {
        "presentation_mode": "model",
        "model_ethnicity": "european",
        "setting": "rooftop",
        "time_of_day": "sunset",
        "mood": "sophisticated",
        "lighting": "golden_backlight",
        "camera_movement": "dolly_in",
        "activity": "standing",
        "description": "European model on a city rooftop at sunset with sophisticated editorial mood",
    },
}

AGENTS_METADATA: list[dict[str, Any]] = [
    {
        "name": "root_agent",
        "internal_name": "ad_campaign_manager",
        "display_name": "Ad Campaign Coordinator",
        "badge": "All Agents",
        "step_numbers": [1, 2, 3, 4, 5, 6],
        "role": "Root orchestrator that routes user requests across the 4 specialized sub-agents.",
        "model": AGENT_MODEL,
        "capabilities": [
            "Multi-agent orchestration & routing",
            "Cross-workflow discovery",
            "Natural language intent resolution",
        ],
        "sample_prompts": [
            "What agents are available and what are our current campaigns?",
            "Show me a complete overview of our products, campaigns, and pending videos.",
        ],
        "tools": [
            "campaign_agent",
            "media_agent",
            "review_agent",
            "analytics_agent",
        ],
    },
    {
        "name": "campaign_agent",
        "internal_name": "campaign_agent",
        "display_name": "Campaign Agent",
        "badge": "Campaign Agent",
        "step_numbers": [1],
        "role": "Manages retail ad campaigns, multi-category product catalog, store locations, and onboarding.",
        "model": AGENT_MODEL,
        "capabilities": [
            "Create, list, view, and update campaigns",
            "Browse 22 fashion + 6 multi-category retail products",
            "Onboard new products (single, folder import, AI image generation, upload)",
            "Store address & location demographics lookups",
        ],
        "sample_prompts": [
            "What agents are available and what are our current campaigns?",
            "List all products in the catalog by category",
            "Create a new summer campaign for Blue Floral Maxi Dress in Miami, FL",
        ],
        "tools": [
            "create_campaign",
            "list_campaigns",
            "get_campaign",
            "update_campaign",
            "get_campaign_locations",
            "search_nearby_stores",
            "get_location_demographics",
            "list_products",
            "get_product",
            "list_product_categories",
            "create_product",
            "import_products_from_folder",
            "generate_product_image",
            "upload_product_image",
        ],
    },
    {
        "name": "media_agent",
        "internal_name": "media_agent",
        "display_name": "Media Agent",
        "badge": "Media Agent",
        "step_numbers": [2, 6],
        "role": "Generates personalized video variations at scale using Gemini 3 Pro Image + Veo 3.1 and applies winning creative formulas.",
        "model": AGENT_MODEL,
        "image_model": IMAGE_GENERATION_MODEL,
        "video_model": VIDEO_GEN_MODEL,
        "capabilities": [
            "Two-stage creative pipeline (Gemini 3 Pro Image -> Veo 3.1 Video)",
            "15+ configurable parameters (subjects/models, settings, tone/mood, lighting, camera, props)",
            "Category-aware presentation modes (model, lifestyle, product-hero)",
            "Batch variation generation & live prompt preview",
            "Video property extraction & Winning Formula replication across campaigns",
        ],
        "sample_prompts": [
            "Generate a video with a European model on a rooftop at sunset, sophisticated mood",
            "Apply the winning formula from video 5 to campaign 3",
            "What video variation options and presets are available?",
        ],
        "tools": [
            "generate_product_video",
            "list_variation_options",
            "generate_ad_video",
            "apply_winning_formula",
            "analyze_video_properties",
            "generate_video_with_properties",
            "list_video_property_options",
            "list_available_seed_images",
            "get_campaign_seed_images",
        ],
    },
    {
        "name": "review_agent",
        "internal_name": "review_agent",
        "display_name": "Review Agent",
        "badge": "Review Agent",
        "step_numbers": [3],
        "role": "Manages Human-in-the-Loop (HITL) video review, 1-click single/batch activation, lifecycle status, and experimental Omni video edits.",
        "model": AGENT_MODEL,
        "omni_edit_enabled": ENABLE_OMNI_EDIT,
        "omni_edit_model": OMNI_EDIT_MODEL,
        "capabilities": [
            "Human-in-the-Loop (HITL) review queue & comparison table",
            "1-click single & batch video activation (metrics start only after approval)",
            "Pause and archive lifecycle controls",
            "Extend metric simulations for activated videos",
            "Experimental post-generation visual editing via Gemini Omni Flash",
        ],
        "sample_prompts": [
            "Show me all pending videos waiting for review",
            "Activate videos 5 and 7",
            "Pause video 2 and show the activation summary",
        ],
        "tools": [
            "get_video_review_table",
            "get_video_details",
            "list_pending_videos",
            "activate_video",
            "activate_batch",
            "pause_video",
            "archive_video",
            "get_video_status",
            "get_activation_summary",
            "generate_additional_metrics",
            *(["edit_video_with_omni"] if ENABLE_OMNI_EDIT else []),
        ],
    },
    {
        "name": "analytics_agent",
        "internal_name": "analytics_agent",
        "display_name": "Analytics Agent",
        "badge": "Analytics Agent",
        "step_numbers": [4, 5],
        "role": "Analyzes in-store retail media metrics (RPI, Dwell Time, Circulation, Impressions, Revenue) and geographic store intelligence.",
        "model": AGENT_MODEL,
        "capabilities": [
            "Primary KPI tracking: Revenue Per Impression (RPI)",
            "Dwell Time, Circulation, Impressions, and Revenue analytics",
            "Top-performing creative rankings & automated optimization insights",
            "Deterministic creative comparison charts & AI infographics",
            "Geographic heat maps, Google Maps integration, and West vs. East Coast regional comparisons",
        ],
        "sample_prompts": [
            "Which videos have the highest RPI?",
            "Compare West Coast vs East Coast performance",
            "Show campaign 1 creative comparison and insights",
        ],
        "tools": [
            "get_campaign_metrics",
            "get_top_performing_ads",
            "get_campaign_insights",
            "compare_campaigns",
            "compare_creatives_within_campaign",
            "generate_creative_comparison_chart",
            "generate_metrics_visualization",
            "get_campaign_map_data",
            "generate_map_visualization",
            "generate_static_map",
        ],
    },
]

POSTER_WORKFLOW_STEPS: list[dict[str, Any]] = [
    {
        "step_number": 1,
        "id": "discover-ai-team",
        "title": "Discover Your AI Team",
        "agent_badge": "All Agents",
        "primary_agent": "root_agent",
        "headline": "Meet the 4 specialized AI agents and explore your active campaigns & products.",
        "highlights": [
            "4 specialized AI agents: Campaign, Media, Review, Analytics",
            "22 fashion products + 6 multi-category retail core products",
            "4 pre-loaded demo campaigns across LA, NYC, and Chicago",
        ],
        "sample_prompt": "What agents are available and what are our current campaigns?",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/discover", "purpose": "Load Step 1 overview"},
            {"method": "GET", "path": "/api/v1/agents", "purpose": "List all AI agents & tools"},
            {"method": "GET", "path": "/api/v1/campaigns", "purpose": "List current campaigns"},
            {"method": "GET", "path": "/api/v1/products", "purpose": "Browse product catalog"},
            {"method": "POST", "path": "/api/v1/agents/chat", "purpose": "Send natural-language prompt"},
        ],
    },
    {
        "step_number": 2,
        "id": "generate-creative-at-scale",
        "title": "Generate Creative at Scale",
        "agent_badge": "Media Agent",
        "primary_agent": "media_agent",
        "headline": "Create 100s of video variations with 15+ configurable parameters.",
        "highlights": [
            "Model Diversity & Presentation: Asian, European, Latina, Black, South Asian, Middle Eastern, Diverse + Model / Lifestyle / Product-Hero modes",
            "Settings & Environment: Beach, Rooftop, Urban, Cafe, Studio, Park, Garden, Street, Boutique + Time of Day, Weather & Season",
            "Moods, Tone & Energy: Sophisticated, Romantic, Confident, Playful, Energetic, Serene, Luxurious + Intensity & Warmth",
            "Lighting & Camera Movement: Golden Backlight, Natural Soft, Dramatic Side, Neon + Orbit, Dolly In/Out, Pan, Tracking, Crane",
            "Two-Stage Pipeline: Gemini 3 Pro Image (customized frame) -> Veo 3.1 (8-second motion video)",
        ],
        "sample_prompt": "Generate a video with a European model on a rooftop at sunset, sophisticated mood",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/videos/options", "purpose": "Get all 15+ configurable video component options"},
            {"method": "GET", "path": "/api/v1/videos/presets", "purpose": "Get curated variation presets"},
            {"method": "POST", "path": "/api/v1/videos/prompts/preview", "purpose": "Live preview Stage 1 & Stage 2 prompts"},
            {"method": "POST", "path": "/api/v1/videos/generate", "purpose": "Generate a video with custom components"},
            {"method": "POST", "path": "/api/v1/videos/generate/batch", "purpose": "Generate batch variations at scale"},
        ],
    },
    {
        "step_number": 3,
        "id": "you-stay-in-control",
        "title": "You Stay in Control",
        "agent_badge": "Review Agent",
        "primary_agent": "review_agent",
        "headline": "Human-in-the-loop approval before any video goes live.",
        "highlights": [
            "Review Pending Videos in a structured comparison table or visual cards",
            "1-Click Activation (single or batch) — metrics only start after human approval",
            "Lifecycle controls: Activate, Pause, Archive, Extend Metrics, and Experimental Omni Edit",
        ],
        "sample_prompt": "Activate videos 5 and 7",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/review/table", "purpose": "Get HITL video review table"},
            {"method": "GET", "path": "/api/v1/review/pending", "purpose": "List pending videos awaiting approval"},
            {"method": "GET", "path": "/api/v1/review/summary", "purpose": "Get activation status summary"},
            {"method": "POST", "path": "/api/v1/videos/{video_id}/activate", "purpose": "Activate a single video"},
            {"method": "POST", "path": "/api/v1/videos/activate-batch", "purpose": "Batch-activate multiple videos (e.g. 5 and 7)"},
            {"method": "POST", "path": "/api/v1/videos/{video_id}/pause", "purpose": "Pause an active video"},
            {"method": "POST", "path": "/api/v1/videos/{video_id}/archive", "purpose": "Archive a video"},
        ],
    },
    {
        "step_number": 4,
        "id": "measure-what-matters",
        "title": "Measure What Matters",
        "agent_badge": "Analytics Agent",
        "primary_agent": "analytics_agent",
        "headline": "In-store retail media metrics — no clicks or conversions needed.",
        "highlights": [
            "RPI (Revenue Per Impression) — Primary KPI",
            "Dwell Time — Attention duration in seconds",
            "Circulation — Foot traffic passing screens",
            "Impressions & Attributed Revenue",
        ],
        "sample_prompt": "Which videos have the highest RPI?",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/analytics/overview", "purpose": "Cross-campaign KPI summary"},
            {"method": "GET", "path": "/api/v1/analytics/top-ads", "purpose": "Rank top videos by RPI, revenue, impressions, or dwell time"},
            {"method": "GET", "path": "/api/v1/analytics/campaigns/{campaign_id}/metrics", "purpose": "Detailed campaign metrics & daily trends"},
            {"method": "GET", "path": "/api/v1/analytics/campaigns/{campaign_id}/insights", "purpose": "AI optimization insights"},
            {"method": "GET", "path": "/api/v1/analytics/campaigns/{campaign_id}/creatives", "purpose": "Compare creatives within a campaign"},
            {"method": "POST", "path": "/api/v1/analytics/campaigns/{campaign_id}/creatives/chart", "purpose": "Generate creative comparison chart"},
        ],
    },
    {
        "step_number": 5,
        "id": "see-the-big-picture",
        "title": "See the Big Picture",
        "agent_badge": "Analytics Agent",
        "primary_agent": "analytics_agent",
        "headline": "Geographic intelligence across all store locations.",
        "highlights": [
            "Performance Heat Map with high/medium/low RPI store tiers",
            "Regional Comparison (West Coast vs. East Coast vs. Midwest)",
            "Google Maps Integration, Static Maps, and Store Demographics",
        ],
        "sample_prompt": "Compare West Coast vs East Coast performance",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/maps/campaigns", "purpose": "Interactive map markers & store performance tiers"},
            {"method": "GET", "path": "/api/v1/maps/regions", "purpose": "Compare West Coast vs East Coast regional performance"},
            {"method": "GET", "path": "/api/v1/maps/locations", "purpose": "Get store addresses & coordinates"},
            {"method": "POST", "path": "/api/v1/maps/static", "purpose": "Generate Google Static Map URL"},
            {"method": "GET", "path": "/api/v1/maps/demographics", "purpose": "Get trade-area demographics"},
        ],
    },
    {
        "step_number": 6,
        "id": "scale-what-works",
        "title": "Scale What Works",
        "agent_badge": "Media Agent",
        "primary_agent": "media_agent",
        "headline": "Extract the winning DNA and apply across campaigns.",
        "highlights": [
            "Identify top performer DNA (e.g., Rooftop Setting + Sunset + Sophisticated Mood + European Model)",
            "1-click replication of winning creative parameters to any target campaign's product",
            "Supports optional component overrides while preserving the winning formula",
        ],
        "sample_prompt": "Apply the winning formula from video 5 to campaign 3",
        "ux_routes": [
            {"method": "GET", "path": "/api/v1/optimization/winning-formula", "purpose": "Extract winning DNA from top video or specific video ID"},
            {"method": "POST", "path": "/api/v1/optimization/apply-winning-formula", "purpose": "Apply winning formula from source video/campaign to target campaign"},
        ],
    },
]


# ============================================================================
# PYDANTIC REQUEST / RESPONSE SCHEMAS
# ============================================================================


class VideoComponentConfig(BaseModel):
    """Comprehensive user-configurable components for video generation.

    Unifies both `VideoVariation` (two-stage Veo parameters) and
    `VideoProperties` (fine-grained subject, environment, tone, lighting,
    camera, color, and audio controls) into a single ergonomic schema for the UX.
    """

    # --- Subjects & Presentation ---
    presentation_mode: str | None = Field(
        default=None,
        description="Presentation mode: 'model', 'lifestyle', or 'product-hero'. Defaults to product category's mode.",
    )
    model_ethnicity: str = Field(
        default="diverse",
        description="Model ethnicity/diversity: asian, european, latina, black, south_asian, middle_eastern, diverse.",
    )
    model_description: str | None = Field(
        default=None,
        description="Custom description of the model/subject (overrides standard ethnicity description when set).",
    )
    activity: str = Field(
        default="walking",
        description="Subject action/pose: walking, standing, sitting, dancing, spinning, posing.",
    )
    subject_count: str = Field(
        default="single",
        description="Subject count: none, single, couple, group.",
    )
    garment_visibility: str = Field(
        default="full",
        description="Product/garment visibility: full, partial, accent.",
    )
    has_multiple_outfits: bool = Field(
        default=False,
        description="Whether multiple outfits/products appear in the scene.",
    )
    props: list[str] = Field(
        default_factory=list,
        description="Scene props to include (e.g., ['sunglasses', 'coffee_cup', 'handbag']).",
    )

    # --- Settings & Environment ---
    setting: str = Field(
        default="studio",
        description="Scene setting: beach, urban, cafe, rooftop, studio, park, garden, street, boutique.",
    )
    setting_type: str | None = Field(
        default=None,
        description="Broad environment category: indoor, outdoor, studio, urban, nature, beach, architectural.",
    )
    location_detail: str | None = Field(
        default=None,
        description="Specific scene/location details (e.g., 'Parisian cobblestone street with bistro tables').",
    )
    time_of_day: str = Field(
        default="golden_hour",
        description="Time of day: golden_hour, morning, midday, afternoon, sunset, blue_hour, night.",
    )
    weather: str | None = Field(
        default="sunny",
        description="Weather condition: sunny, cloudy, overcast, rainy, windy, foggy.",
    )
    season: str | None = Field(
        default=None,
        description="Season context: spring, summer, fall, winter.",
    )
    background_complexity: str = Field(
        default="moderate",
        description="Background detail level: minimal, moderate, busy.",
    )

    # --- Tone, Mood & Energy ---
    mood: str = Field(
        default="confident",
        description="Primary tone/mood: romantic, confident, playful, serene, energetic, sophisticated, mysterious, joyful, editorial, warm, nostalgic, luxurious.",
    )
    mood_intensity: str = Field(
        default="moderate",
        description="Mood intensity: subtle, moderate, intense.",
    )
    has_warmth: bool = Field(
        default=True,
        description="Whether the scene projects emotional warmth.",
    )
    energy_level: str = Field(
        default="moderate",
        description="Pacing/energy level: calm, moderate, dynamic, high_energy.",
    )
    movement_amount: str = Field(
        default="moderate",
        description="Amount of motion in scene: static, minimal, moderate, high.",
    )

    # --- Lighting, Visual Style & Color ---
    lighting: str = Field(
        default="natural_soft",
        description="Lighting setup: natural_soft, golden_backlight, dramatic_side, bright_even, dappled, neon_ambient, studio_three_point.",
    )
    lighting_style: str | None = Field(
        default=None,
        description="Lighting style tag: natural, golden_hour, dramatic, soft_diffused, high_key, low_key, backlit, neon.",
    )
    visual_style: str = Field(
        default="cinematic",
        description="Overall aesthetic: cinematic, editorial, commercial, lifestyle, artistic, documentary, retro.",
    )
    color_grading: str = Field(
        default="warm",
        description="Color grading/temperature: warm, neutral, cool, vibrant, desaturated.",
    )
    color_saturation: str = Field(
        default="natural",
        description="Color saturation: muted, natural, vibrant, hyper_saturated.",
    )
    dominant_colors: list[str] = Field(
        default_factory=list,
        description="Dominant color palette (e.g., ['gold', 'navy', 'ivory']).",
    )
    style_tags: list[str] = Field(
        default_factory=list,
        description="Additional creative style tags (e.g., ['bokeh', 'film_grain', 'shallow_dof']).",
    )

    # --- Camera & Framing ---
    camera_movement: str = Field(
        default="dolly_in",
        description="Camera motion: orbit, pan, dolly_in, dolly_out, tracking, crane_up, crane_down, static.",
    )
    camera_angle: str = Field(
        default="eye_level",
        description="Camera framing angle: eye_level, low_angle, high_angle, dutch_angle, overhead.",
    )
    aspect_ratio: str = Field(
        default="9:16",
        description="Video aspect ratio: '9:16' (vertical retail display), '16:9', or '1:1'.",
    )

    # --- Audio & Production ---
    duration_seconds: int = Field(
        default=8,
        description="Video duration in seconds (4, 6, or 8).",
    )
    use_two_stage: bool = Field(
        default=True,
        description="Use two-stage pipeline (Gemini 3 Pro Image -> Veo 3.1 Video).",
    )
    audio_type: str = Field(
        default="music",
        description="Audio track type: silent, music, ambient, voiceover, full_mix.",
    )
    music_tempo: str | None = Field(
        default="medium",
        description="Music tempo: slow, medium, upbeat, dynamic.",
    )
    audio_mood: str | None = Field(
        default=None,
        description="Audio mood descriptor.",
    )
    has_text_overlays: bool = Field(
        default=False,
        description="Whether text overlays are requested (Stage 1/2 prompts enforce no rendered text by default).",
    )
    has_brand_elements: bool = Field(
        default=False,
        description="Whether brand elements/logos are present.",
    )
    custom_instructions: str | None = Field(
        default=None,
        description="Optional free-form creative direction appended to the generated prompt.",
    )
    preset_name: str | None = Field(
        default=None,
        description="Optional preset name to initialize base components before applying overrides.",
    )


class PromptPreviewRequest(BaseModel):
    """Request body for live prompt preview (`/api/v1/videos/prompts/preview`)."""

    campaign_id: int | None = None
    product_id: int | None = None
    components: VideoComponentConfig = Field(default_factory=VideoComponentConfig)


class VideoGenerateRequest(BaseModel):
    """Request body for single video generation (`/api/v1/videos/generate`)."""

    campaign_id: int
    product_id: int | None = None
    components: VideoComponentConfig | None = None
    # Convenience top-level overrides so UX can send flat JSON or nested `components`
    preset_name: str | None = None
    presentation_mode: str | None = None
    model_ethnicity: str | None = None
    model_description: str | None = None
    setting: str | None = None
    location_detail: str | None = None
    time_of_day: str | None = None
    weather: str | None = None
    season: str | None = None
    mood: str | None = None
    mood_intensity: str | None = None
    energy_level: str | None = None
    lighting: str | None = None
    visual_style: str | None = None
    color_grading: str | None = None
    dominant_colors: list[str] | None = None
    style_tags: list[str] | None = None
    camera_movement: str | None = None
    camera_angle: str | None = None
    aspect_ratio: str | None = None
    activity: str | None = None
    props: list[str] | None = None
    duration_seconds: int | None = None
    use_two_stage: bool | None = None
    custom_instructions: str | None = None
    dry_run: bool = Field(
        default=True,
        description="When True, creates the pending `campaign_videos` DB row and returns full prompts/metadata without billing live Vertex Veo calls.",
    )


class BatchVideoGenerateRequest(BaseModel):
    """Request body for batch video generation (`/api/v1/videos/generate/batch`)."""

    campaign_id: int
    product_id: int | None = None
    variations: list[VideoComponentConfig] | None = Field(
        default=None,
        description="Explicit list of video component configurations to generate.",
    )
    preset_names: list[str] | None = Field(
        default=None,
        description="List of preset names to generate.",
    )
    # Matrix generation options ("Create 100s of video variations")
    model_ethnicities: list[str] | None = None
    settings: list[str] | None = None
    times_of_day: list[str] | None = None
    moods: list[str] | None = None
    lightings: list[str] | None = None
    camera_movements: list[str] | None = None
    activities: list[str] | None = None
    base_components: VideoComponentConfig = Field(default_factory=VideoComponentConfig)
    max_variations: int = Field(default=20, ge=1, le=100)
    dry_run: bool = Field(default=True)


class CampaignCreateRequest(BaseModel):
    """Request body for creating a campaign."""

    product_id: int
    store_name: str
    city: str
    state: str
    name: str | None = None
    category: str = "promotional"
    start_date: str | None = None
    end_date: str | None = None
    target_audience: str | None = None
    street_address: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CampaignUpdateRequest(BaseModel):
    """Request body for updating a campaign."""

    name: str | None = None
    status: str | None = None
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    target_audience: str | None = None
    store_name: str | None = None
    city: str | None = None
    state: str | None = None
    product_id: int | None = None


class ProductCreateRequest(BaseModel):
    """Request body for onboarding a new product."""

    name: str
    category: str = "fashion"
    description: str | None = None
    style: str | None = None
    color: str | None = None
    material: str | None = None
    season: str | None = None
    garment_type: str | None = None
    attributes: dict[str, Any] | None = None
    image_filename: str | None = None


class ProductImportFolderRequest(BaseModel):
    """Request body for bulk importing products from a local folder."""

    folder_path: str
    category: str = "fashion"


class ProductGenerateImageRequest(BaseModel):
    """Request body for generating a product reference image."""

    custom_prompt: str | None = None
    dry_run: bool = False


class ProductUploadImageRequest(BaseModel):
    """Request body for attaching an image file to a product."""

    source_path: str


class VideoActivateRequest(BaseModel):
    """Request body for activating a single video."""

    days_of_metrics: int = Field(default=30, ge=1, le=365)


class VideoBatchActivateRequest(BaseModel):
    """Request body for batch activating videos (e.g. 'Activate videos 5 and 7')."""

    video_ids: list[int]
    days_of_metrics: int = Field(default=30, ge=1, le=365)


class VideoExtendMetricsRequest(BaseModel):
    """Request body for generating additional days of metrics."""

    additional_days: int = Field(default=7, ge=1, le=90)


class VideoOmniEditRequest(BaseModel):
    """Request body for experimental Omni Flash post-generation video edit."""

    edit_instruction: str
    dry_run: bool = False


class WinningFormulaApplyRequest(BaseModel):
    """Request body for Step 6: Scale What Works (`apply-winning-formula`)."""

    target_campaign_id: int
    source_video_id: int | None = Field(
        default=None,
        description="Specific video ID to copy the winning formula from (e.g. video 5).",
    )
    source_campaign_id: int | None = Field(
        default=None,
        description="Optional campaign ID to find the top-performing video from.",
    )
    override_components: dict[str, Any] | None = Field(
        default=None,
        description="Optional component overrides (e.g. keep winning rooftop/sunset/sophisticated DNA but change model_ethnicity).",
    )
    dry_run: bool = Field(
        default=True,
        description="When True, creates the new pending `campaign_videos` record immediately using the extracted winning DNA.",
    )


class AgentChatRequest(BaseModel):
    """Request body for natural-language agent interaction (`/api/v1/agents/chat`)."""

    prompt: str
    agent_name: str | None = Field(
        default=None,
        description="Optional target agent (`root_agent`, `campaign_agent`, `media_agent`, `review_agent`, `analytics_agent`). Auto-routed if omitted.",
    )
    session_id: str | None = None
    user_id: str = "ux_user"
    dry_run_media: bool = Field(
        default=True,
        description="For media generation prompts via chat, create pending DB records without billing live Veo unless False.",
    )
    prefer_live_agent: bool = Field(
        default=False,
        description="When True and ADK + Vertex/AI Studio credentials are configured, run the live LLM agent runner.",
    )


class DatasetSeedRequest(BaseModel):
    """Request body for seeding or resetting datasets."""

    dataset_mode: str = Field(
        default="fashion",
        description="Dataset mode to seed: 'fashion' (22 fashion + 6 retail core products, 4 campaigns) or 'none' (empty catalog for from-scratch onboarding).",
    )
    force_reseed: bool = Field(
        default=False,
        description="When True, wipes existing tables and reseeds from scratch.",
    )


class CampaignCompareRequest(BaseModel):
    """Request body for comparing campaigns."""

    campaign_ids: list[int] = Field(default_factory=lambda: [1, 2, 3, 4])


class StaticMapRequest(BaseModel):
    """Request body for generating a static map URL."""

    campaign_ids: list[int] | None = None
    width: int = 800
    height: int = 500
    zoom: int | None = None


class VisualizationRequest(BaseModel):
    """Request body for generating campaign or map visualizations."""

    campaign_id: int | None = None
    chart_type: str = "comparison"
    dry_run: bool = True


# ============================================================================
# HELPER FUNCTIONS FOR VIDEO COMPONENTS & DATABASE QUERIES
# ============================================================================


def _merge_video_components(req: VideoGenerateRequest) -> VideoComponentConfig:
    """Merge nested `components`, preset defaults, and top-level fields."""
    base_dict: dict[str, Any] = {}
    preset_key = req.preset_name or (req.components.preset_name if req.components else None)
    if preset_key:
        if preset_key in PRESET_VARIATIONS:
            preset_var = PRESET_VARIATIONS[preset_key]
            base_dict.update(
                {
                    "model_ethnicity": preset_var.model_ethnicity.value,
                    "setting": preset_var.setting.value,
                    "time_of_day": preset_var.time_of_day.value,
                    "mood": preset_var.mood.value,
                    "lighting": preset_var.lighting.value,
                    "camera_movement": preset_var.camera_movement.value,
                    "activity": preset_var.activity.value,
                    "props": list(preset_var.props or []),
                    "aspect_ratio": preset_var.aspect_ratio,
                    "duration_seconds": preset_var.duration_seconds,
                    "preset_name": preset_key,
                }
            )
        elif preset_key in CATEGORY_PRESETS:
            base_dict.update(CATEGORY_PRESETS[preset_key])
            base_dict["preset_name"] = preset_key

    if req.components is not None:
        comp_dump = req.components.model_dump(exclude_unset=True)
        for k, v in comp_dump.items():
            if v is not None:
                base_dict[k] = v

    override_fields = [
        "presentation_mode",
        "model_ethnicity",
        "model_description",
        "setting",
        "location_detail",
        "time_of_day",
        "weather",
        "season",
        "mood",
        "mood_intensity",
        "energy_level",
        "lighting",
        "visual_style",
        "color_grading",
        "dominant_colors",
        "style_tags",
        "camera_movement",
        "camera_angle",
        "aspect_ratio",
        "activity",
        "props",
        "duration_seconds",
        "use_two_stage",
        "custom_instructions",
        "preset_name",
    ]
    for field_name in override_fields:
        val = getattr(req, field_name, None)
        if val is not None:
            base_dict[field_name] = val

    return VideoComponentConfig(**base_dict)


def _safe_enum(enum_cls: Any, value: str | None, default: Any) -> Any:
    """Resolve an enum value case-insensitively with a safe fallback."""
    if not value:
        return default
    norm = value.strip().lower().replace(" ", "_").replace("-", "_")
    for member in enum_cls:
        if member.value.lower() == norm or member.name.lower() == norm:
            return member
    return default


def _build_variation_and_properties(
    config: VideoComponentConfig,
    product_row: dict[str, Any],
) -> tuple[VideoVariation, VideoProperties, dict[str, str]]:
    """Convert `VideoComponentConfig` + `product_row` into `VideoVariation`, `VideoProperties`, and Stage 1/2 prompts."""
    category = (product_row.get("category") or "fashion").lower()
    default_mode = CATEGORY_DEFAULT_PRESENTATION.get(category, "model")
    presentation_mode = config.presentation_mode or product_row.get("presentation_mode") or default_mode
    if presentation_mode not in VALID_PRESENTATION_MODES:
        presentation_mode = default_mode

    variation = VideoVariation(
        model_ethnicity=_safe_enum(ModelEthnicity, config.model_ethnicity, ModelEthnicity.DIVERSE),
        setting=_safe_enum(Setting, config.setting, Setting.STUDIO),
        time_of_day=_safe_enum(TimeOfDay, config.time_of_day, TimeOfDay.GOLDEN_HOUR),
        mood=_safe_enum(Mood, config.mood, Mood.CONFIDENT),
        lighting=_safe_enum(Lighting, config.lighting, Lighting.NATURAL_SOFT),
        camera_movement=_safe_enum(CameraMovement, config.camera_movement, CameraMovement.DOLLY_IN),
        activity=_safe_enum(Activity, config.activity, Activity.WALKING),
        props=list(config.props or []),
        color_grading=config.color_grading or "warm",
        aspect_ratio=config.aspect_ratio or "9:16",
        duration_seconds=config.duration_seconds if config.duration_seconds in (4, 6, 8) else 8,
    )

    setting_to_type = {
        "studio": SettingType.STUDIO,
        "beach": SettingType.BEACH,
        "park": SettingType.NATURE,
        "garden": SettingType.NATURE,
        "urban": SettingType.URBAN,
        "street": SettingType.URBAN,
        "rooftop": SettingType.ARCHITECTURAL,
        "cafe": SettingType.INDOOR,
        "boutique": SettingType.INDOOR,
    }
    inferred_setting_type = (
        _safe_enum(SettingType, config.setting_type, setting_to_type.get(variation.setting.value, SettingType.OUTDOOR))
        if config.setting_type
        else setting_to_type.get(variation.setting.value, SettingType.OUTDOOR)
    )

    subject_count = (
        SubjectCount.NONE
        if presentation_mode == "product-hero"
        else _safe_enum(SubjectCount, config.subject_count, SubjectCount.SINGLE)
    )

    video_props = VideoProperties(
        subject_count=subject_count,
        model_ethnicity=variation.model_ethnicity.value if presentation_mode != "product-hero" else None,
        model_description=config.model_description
        or (ETHNICITY_DESCRIPTIONS.get(variation.model_ethnicity) if presentation_mode != "product-hero" else None),
        garment_visibility=config.garment_visibility or "full",
        has_multiple_outfits=config.has_multiple_outfits,
        setting_type=inferred_setting_type,
        location_detail=config.location_detail or SETTING_DESCRIPTIONS.get(variation.setting),
        time_of_day=variation.time_of_day.value,
        weather=_safe_enum(WeatherCondition, config.weather, WeatherCondition.SUNNY) if config.weather else None,
        season=config.season or product_row.get("season"),
        background_complexity=config.background_complexity or "moderate",
        camera_movement=variation.camera_movement.value,
        camera_angle=_safe_enum(CameraAngle, config.camera_angle, CameraAngle.EYE_LEVEL),
        movement_amount=_safe_enum(MovementAmount, config.movement_amount, MovementAmount.MODERATE),
        energy_level=_safe_enum(EnergyLevel, config.energy_level, EnergyLevel.MODERATE),
        lighting_style=_safe_enum(LightingStyle, config.lighting_style or variation.lighting.value, LightingStyle.NATURAL),
        color_temperature=_safe_enum(ColorTemperature, config.color_grading, ColorTemperature.WARM),
        color_saturation=_safe_enum(ColorSaturation, config.color_saturation, ColorSaturation.NATURAL),
        dominant_colors=list(config.dominant_colors or ([product_row["color"]] if product_row.get("color") else [])),
        visual_style=_safe_enum(VisualStyle, config.visual_style, VisualStyle.CINEMATIC),
        mood=variation.mood.value,
        mood_intensity=_safe_enum(MoodIntensity, config.mood_intensity, MoodIntensity.MODERATE),
        has_warmth=config.has_warmth,
        audio_type=_safe_enum(AudioType, config.audio_type, AudioType.MUSIC),
        music_tempo=_safe_enum(MusicTempo, config.music_tempo, MusicTempo.MEDIUM) if config.music_tempo else None,
        audio_mood=config.audio_mood or variation.mood.value,
        aspect_ratio=_safe_enum(AspectRatio, config.aspect_ratio, AspectRatio.PORTRAIT_9_16),
        duration_seconds=variation.duration_seconds,
        has_text_overlays=config.has_text_overlays,
        has_brand_elements=config.has_brand_elements,
        style_tags=list(config.style_tags or []),
        notable_props=list(config.props or []),
    )

    raw_attrs = product_row.get("attributes")
    if isinstance(raw_attrs, str):
        try:
            attrs = json.loads(raw_attrs)
        except json.JSONDecodeError:
            attrs = {}
    elif isinstance(raw_attrs, dict):
        attrs = raw_attrs
    else:
        attrs = {}

    product_dict = {
        "name": product_row.get("name", "Product"),
        "description": product_row.get("description") or product_row.get("details") or "",
        "garment_type": product_row.get("garment_type") or product_row.get("category") or "item",
        "color": product_row.get("color", ""),
        "style": product_row.get("style", ""),
        "material": product_row.get("material") or product_row.get("fabric") or "",
        "category": category,
        "presentation_mode": presentation_mode,
        "attributes": attrs,
    }

    if category in FASHION_CATEGORIES and presentation_mode == "model":
        stage1_prompt = build_stage1_image_prompt(variation, product_dict)
        stage2_prompt = build_stage2_video_prompt(variation, product_dict)
    else:
        stage1_prompt, stage2_prompt = build_category_aware_prompts(
            variation, product_dict, presentation_mode=presentation_mode
        )

    extra_details: list[str] = []
    if config.model_description:
        extra_details.append(f"Subject detail: {config.model_description}.")
    if config.location_detail:
        extra_details.append(f"Location detail: {config.location_detail}.")
    if config.weather and config.weather != "sunny":
        extra_details.append(f"Weather: {config.weather}.")
    if config.visual_style and config.visual_style != "cinematic":
        extra_details.append(f"Visual style: {config.visual_style}.")
    if config.camera_angle and config.camera_angle != "eye_level":
        extra_details.append(f"Camera angle: {config.camera_angle.replace('_', ' ')}.")
    if config.dominant_colors:
        extra_details.append(f"Color palette: {', '.join(config.dominant_colors)}.")
    if config.style_tags:
        extra_details.append(f"Style elements: {', '.join(config.style_tags)}.")
    if config.custom_instructions:
        extra_details.append(f"Additional direction: {config.custom_instructions}.")

    if extra_details:
        addon = " " + " ".join(extra_details)
        stage1_prompt = stage1_prompt + addon
        stage2_prompt = stage2_prompt + addon

    single_stage_prompt = f"{stage1_prompt}\n\nMotion & Atmosphere:\n{stage2_prompt}"

    return (
        variation,
        video_props,
        {
            "presentation_mode": presentation_mode,
            "stage1_image_prompt": stage1_prompt,
            "stage2_video_prompt": stage2_prompt,
            "single_stage_prompt": single_stage_prompt,
            "variation_modifier": video_props.to_prompt_modifier(),
        },
    )


def _fetch_product_row(product_id: int) -> dict[str, Any] | None:
    """Fetch a product row from SQLite and enrich with normalized fields, public URL, and image_status."""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            return None
        p = dict(row)

    prod_obj = Product.from_row(p)
    p["attributes"] = dict(prod_obj.attributes or {})
    p["description"] = p.get("details") or prod_obj.description or ""
    p["material"] = p.get("fabric") or p["attributes"].get("fabric") or p["attributes"].get("material") or ""
    p["garment_type"] = p.get("category") or "fashion"
    p["season"] = p["attributes"].get("season") or p.get("occasion") or "all-season"

    category = (p.get("category") or "fashion").lower()
    p["presentation_mode"] = CATEGORY_DEFAULT_PRESENTATION.get(category, "model")
    img_file = p.get("image_filename")
    if img_file:
        p["image_url"] = to_public_url(BUCKET_PRODUCT_IMAGES, img_file)
        p["gateway_asset_url"] = f"/api/v1/assets/{BUCKET_PRODUCT_IMAGES}/{img_file}"
        local_path = resolve_asset_path(BUCKET_PRODUCT_IMAGES, img_file)
        p["image_status"] = "available" if local_path.exists() else "missing"
    else:
        p["image_url"] = None
        p["gateway_asset_url"] = None
        p["image_status"] = "missing"
    return p


def _enrich_video_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON fields and attach asset URLs on a `campaign_videos` row."""
    out = dict(row_dict)
    raw_vp = out.get("variation_params")
    if isinstance(raw_vp, str) and raw_vp.strip():
        try:
            out["variation_params"] = json.loads(raw_vp)
        except json.JSONDecodeError:
            out["variation_params"] = {}
    elif not isinstance(raw_vp, dict):
        out["variation_params"] = {}

    raw_props = out.get("video_properties")
    if isinstance(raw_props, str) and raw_props.strip():
        try:
            out["video_properties"] = json.loads(raw_props)
        except json.JSONDecodeError:
            out["video_properties"] = {}
    elif not isinstance(raw_props, dict):
        out["video_properties"] = out["variation_params"].get("video_properties", {})

    out["prompt_used"] = out.get("prompt_used") or out.get("video_prompt") or out.get("scene_prompt")

    filename = out.get("video_filename")
    if filename:
        out["video_url"] = out.get("gcs_path") or to_public_url(BUCKET_GENERATED, filename)
        out["gateway_video_url"] = f"/api/v1/assets/{BUCKET_GENERATED}/{filename}"
    return out


# ============================================================================
# UX DESIGNER OBJECT MODEL (object.js COMPATIBILITY)
# ============================================================================


class UXStatus(IntEnum):
    """Statuses used for *both* overall status of campaigns *and* status of individual videos.

    Matches `Status` enum in object.js exactly.
    """

    NONE = 0
    GENERATING_ACTIVE = 1
    GENERATING_COMPLETE = 2
    GENERATING_FAILED = 3
    REVIEW_NEEDED = 4
    APPROVAL_UPDATED = 5
    TESTING_ACTIVE = 6
    TESTING_COMPLETE = 7
    TESTING_FAILED = 8


class UXApprovalStatus(IntEnum):
    """Video approval statuses.

    Matches `ApprovalStatus` enum in object.js exactly.
    """

    NONE = 0
    APPROVED = 1
    REJECTED = 2


class UXSettingSection(BaseModel):
    """Prompt + files indicating component details in campaign/video settings."""

    prompt: str = ""
    files: list[str] = Field(default_factory=list)


class UXSettingsFormat(BaseModel):
    """Format settings for generated videos."""

    duration: int = 8
    aspect_ratios: list[str] = Field(default_factory=lambda: ["16:9"])
    resolution: str = "1080p"


class UXSettingsTesting(BaseModel):
    """Testing parameters for video variant generation."""

    variants_per_generation: int = 10
    rules: str | None = None
    duration: int = 24


class UXCampaignSettings(BaseModel):
    """Default settings used for generating video variants in a campaign."""

    overall: UXSettingSection = Field(default_factory=UXSettingSection)
    items: UXSettingSection = Field(default_factory=UXSettingSection)
    people: UXSettingSection = Field(default_factory=UXSettingSection)
    performance: UXSettingSection = Field(default_factory=UXSettingSection)
    setting: UXSettingSection = Field(default_factory=UXSettingSection)
    audio: UXSettingSection = Field(default_factory=UXSettingSection)
    languages: list[str] = Field(default_factory=lambda: ["en-US"])
    guidelines: list[str] = Field(default_factory=list)
    format: UXSettingsFormat = Field(default_factory=UXSettingsFormat)
    testing: UXSettingsTesting = Field(default_factory=UXSettingsTesting)


class UXVideo(BaseModel):
    """Video object conforming to `videoExample` in object.js."""

    id: str = "000001"
    name: str = "000-000-001"
    parent_id: str | None = "000000"
    campaign_id: str | None = None
    created_date: str = "2026-01-01T00:00:00Z"
    modified_date: str | None = None
    is_favorite: bool = False
    is_archived: bool = False
    approval_status: int = UXApprovalStatus.NONE
    approval_date: str | None = None
    status: int = UXStatus.TESTING_ACTIVE
    status_meta: dict[str, Any] = Field(default_factory=dict)
    thumbnail: str | None = None
    description: str | None = None
    url: str | None = None
    testing_period: dict[str, str] | None = None
    duration: int = 8
    impressions: int = 0
    impressions_id: str = ""
    revenue: float = 0.0
    revenue_id: str = ""
    rank: int = 1
    settings: dict[str, Any] = Field(default_factory=dict)


class UXCampaign(BaseModel):
    """Campaign object conforming to `campaignExample` in object.js."""

    id: str = "000001"
    name: str = "Campaign"
    owner: str = "cid@domain.com"
    shared_with: list[str] = Field(default_factory=lambda: ["tommy@domain.com", "fred@domain.com"])
    created_date: str = "2026-01-01T00:00:00Z"
    modified_date: str = "2026-01-01T00:00:00Z"
    is_template: bool = False
    is_favorite: bool = False
    is_archived: bool = False
    status: int = UXStatus.TESTING_ACTIVE
    status_meta: dict[str, Any] = Field(default_factory=dict)
    thumbnail: str | None = None
    description: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    videos: list[UXVideo] = Field(default_factory=list)


def map_video_status_to_ux(video_dict: dict[str, Any]) -> tuple[int, int]:
    """Map backend video row to (UXStatus, UXApprovalStatus)."""
    raw_status = str(video_dict.get("status") or "").strip().lower()
    activated_at = video_dict.get("activated_at")

    if raw_status == "archived":
        approval = UXApprovalStatus.REJECTED
    elif raw_status == "activated" or activated_at:
        approval = UXApprovalStatus.APPROVED
    else:
        approval = UXApprovalStatus.NONE

    if raw_status in ("generating", "pending"):
        st = UXStatus.GENERATING_ACTIVE
    elif raw_status in ("generating_failed", "failed"):
        st = UXStatus.GENERATING_FAILED
    elif raw_status == "generated":
        st = UXStatus.REVIEW_NEEDED
    elif raw_status == "paused":
        st = UXStatus.APPROVAL_UPDATED
    elif raw_status == "activated":
        st = UXStatus.TESTING_ACTIVE
    elif raw_status == "testing_complete":
        st = UXStatus.TESTING_COMPLETE
    elif raw_status == "testing_failed":
        st = UXStatus.TESTING_FAILED
    elif raw_status == "archived":
        st = UXStatus.NONE
    else:
        st = UXStatus.REVIEW_NEEDED
    return int(st), int(approval)


def map_campaign_status_to_ux(
    campaign_dict: dict[str, Any], videos: list[dict[str, Any]] | None = None
) -> int:
    """Map backend campaign row to UXStatus integer."""
    raw = str(campaign_dict.get("status") or "").strip().lower()
    if raw == "archived":
        return int(UXStatus.NONE)
    if raw in ("generating", "generating_active"):
        return int(UXStatus.GENERATING_ACTIVE)
    if raw == "generating_failed":
        return int(UXStatus.GENERATING_FAILED)
    if raw == "paused":
        return int(UXStatus.APPROVAL_UPDATED)

    if videos:
        if any(str(v.get("status") or "").lower() == "activated" for v in videos):
            return int(UXStatus.TESTING_ACTIVE)
        if any(str(v.get("status") or "").lower() in ("generated", "review_needed") for v in videos):
            return int(UXStatus.REVIEW_NEEDED)
        if any(str(v.get("status") or "").lower() in ("generating", "pending") for v in videos):
            return int(UXStatus.GENERATING_ACTIVE)

    if raw in ("active", "testing_active"):
        return int(UXStatus.TESTING_ACTIVE)
    if raw == "testing_complete":
        return int(UXStatus.TESTING_COMPLETE)
    if raw == "draft":
        return int(UXStatus.NONE)
    return int(UXStatus.TESTING_ACTIVE)


def to_ux_video(
    video_row: dict[str, Any],
    campaign_info: dict[str, Any] | None = None,
    rank: int = 1,
) -> dict[str, Any]:
    """Transform backend campaign_videos row into the exact UX Designer `videoExample` object."""
    v = _enrich_video_row(dict(video_row))
    vid_id_int = int(v.get("id") or 1)
    camp_id_int = int(v.get("campaign_id") or (campaign_info.get("id") if campaign_info else 1) or 1)

    vid_id_str = f"{vid_id_int:06d}"
    camp_id_str = f"{camp_id_int:06d}"
    parent_id = f"{int(v['parent_video_id']):06d}" if v.get("parent_video_id") else "000000"

    st, app_st = map_video_status_to_ux(v)

    created_dt = v.get("created_at") or "2026-01-01T00:00:00Z"
    if isinstance(created_dt, str) and not created_dt.endswith("Z") and "+" not in created_dt:
        created_dt = f"{created_dt}Z"

    mod_dt = v.get("activated_at") or v.get("created_at") or "2026-01-01T00:00:00Z"
    if isinstance(mod_dt, str) and not mod_dt.endswith("Z") and "+" not in mod_dt:
        mod_dt = f"{mod_dt}Z"

    approval_date = v.get("activated_at")
    if approval_date and not str(approval_date).endswith("Z") and "+" not in str(approval_date):
        approval_date = f"{approval_date}Z"
    elif app_st == UXApprovalStatus.APPROVED and not approval_date:
        approval_date = created_dt

    # Filename & asset paths
    filename = v.get("video_filename")
    if filename:
        video_url = to_public_url(BUCKET_GENERATED, filename) or f"/api/v1/assets/{BUCKET_GENERATED}/{filename}"
    else:
        video_url = f"/generated_assets/{camp_id_str}_{vid_id_str}.mp4"

    thumb_path = v.get("thumbnail_path") or v.get("thumbnail_filename")
    if thumb_path:
        thumb_name = str(thumb_path).split("/")[-1]
        thumb_url = to_public_url(BUCKET_GENERATED, thumb_name) or f"/api/v1/assets/{BUCKET_GENERATED}/{thumb_name}"
    else:
        thumb_url = f"/generated_assets/{camp_id_str}_{vid_id_str}.jpg"

    # Metrics
    imp = int(v.get("total_impressions") or v.get("impressions") or 0)
    rev = float(v.get("total_revenue") or v.get("revenue") or 0.0)

    imp_id = hashlib.md5(f"imp-{vid_id_int}-{imp}".encode()).hexdigest()[:8]
    rev_id = hashlib.md5(f"rev-{vid_id_int}-{rev}".encode()).hexdigest()[:8]

    # Testing period from video_metrics if available
    testing_period = None
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT MIN(metric_date) as min_d, MAX(metric_date) as max_d FROM video_metrics WHERE video_id = ?",
                (vid_id_int,),
            )
            r = cursor.fetchone()
            if r and r["min_d"] and r["max_d"]:
                testing_period = {
                    "start_date": f"{r['min_d']}T00:00:00Z",
                    "end_date": f"{r['max_d']}T23:59:59Z",
                }
    except Exception:
        pass

    if not testing_period:
        testing_period = {
            "start_date": created_dt,
            "end_date": mod_dt,
        }

    status_meta: dict[str, Any] = {
        "quantity": 1,
        "end_date": testing_period["end_date"],
    }
    if v.get("status_message"):
        status_meta["message"] = v["status_message"]

    # Component settings overrides
    vp = v.get("variation_params") or {}
    video_settings: dict[str, Any] = {}
    if vp:
        if vp.get("setting"):
            video_settings["setting"] = {"prompt": vp.get("setting"), "files": []}
        if vp.get("mood"):
            video_settings["overall"] = {"prompt": f"Mood: {vp.get('mood')}", "files": []}
        if vp.get("model_ethnicity"):
            video_settings["people"] = {"prompt": vp.get("model_ethnicity"), "files": []}
        if vp.get("activity"):
            video_settings["performance"] = {"prompt": vp.get("activity"), "files": []}
        if vp.get("aspect_ratio"):
            video_settings["format"] = {
                "duration": int(v.get("duration_seconds") or 8),
                "aspect_ratios": [vp.get("aspect_ratio")],
                "resolution": "1080p",
            }

    name = v.get("name") or f"{camp_id_int:03d}-{vid_id_int:03d}-{int(rank):03d}"
    desc = v.get("prompt_used") or v.get("scene_prompt") or v.get("video_prompt") or f"Variant video ad #{vid_id_str}"

    return {
        "id": vid_id_str,
        "name": name,
        "parent_id": parent_id,
        "campaign_id": camp_id_str,
        "created_date": created_dt,
        "is_favorite": bool(v.get("is_favorite", False)),
        "is_archived": bool(v.get("is_archived", (str(v.get("status") or "").lower() == "archived"))),
        "approval_status": app_st,
        "approval_date": approval_date,
        "status": st,
        "status_meta": status_meta,
        "thumbnail": thumb_url,
        "description": desc,
        "url": video_url,
        "testing_period": testing_period,
        "duration": int(v.get("duration_seconds") or 8),
        "impressions": imp,
        "impressions_id": imp_id,
        "revenue": round(rev, 2),
        "revenue_id": rev_id,
        "rank": int(rank),
        "settings": video_settings,
    }


def to_ux_campaign(
    campaign_row: dict[str, Any],
    videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Transform backend campaign row into the exact UX Designer `campaignExample` object."""
    c = dict(campaign_row)
    cid_int = int(c.get("id") or 1)
    cid_str = f"{cid_int:06d}"

    raw_videos = videos if videos is not None else []
    if videos is None:
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cv.*,
                           COALESCE(SUM(vm.impressions), 0) as total_impressions,
                           COALESCE(SUM(vm.revenue), 0.0) as total_revenue
                    FROM campaign_videos cv
                    LEFT JOIN video_metrics vm ON cv.id = vm.video_id
                    WHERE cv.campaign_id = ?
                    GROUP BY cv.id
                    ORDER BY cv.id DESC
                    """,
                    (cid_int,),
                )
                raw_videos = [dict(r) for r in cursor.fetchall()]
        except Exception:
            raw_videos = []

    # Sort videos by revenue/impressions descending to compute rank
    sorted_vids = sorted(
        raw_videos,
        key=lambda x: (
            float(x.get("total_revenue") or 0.0)
            / (float(x.get("total_impressions") or 0) or 1.0)
        ),
        reverse=True,
    )
    ux_videos: list[dict[str, Any]] = []
    for rank_idx, vid in enumerate(sorted_vids, 1):
        ux_videos.append(to_ux_video(vid, campaign_info=c, rank=rank_idx))

    st = map_campaign_status_to_ux(c, raw_videos)

    created_dt = c.get("created_at") or "2026-01-01T00:00:00Z"
    if isinstance(created_dt, str) and not created_dt.endswith("Z") and "+" not in created_dt:
        created_dt = f"{created_dt}Z"

    mod_dt = c.get("updated_at") or c.get("created_at") or "2026-01-01T00:00:00Z"
    if isinstance(mod_dt, str) and not mod_dt.endswith("Z") and "+" not in mod_dt:
        mod_dt = f"{mod_dt}Z"

    # Status meta
    end_date = "2026-01-01T00:00:00Z"
    if ux_videos and ux_videos[0].get("testing_period"):
        end_date = ux_videos[0]["testing_period"]["end_date"]
    status_meta: dict[str, Any] = {
        "quantity": len(ux_videos),
        "end_date": end_date,
    }
    if c.get("status_message"):
        status_meta["message"] = c["status_message"]

    # Thumbnail
    thumbnail = None
    if ux_videos and ux_videos[0].get("thumbnail"):
        thumbnail = ux_videos[0]["thumbnail"]
    elif c.get("product_image_filename"):
        thumbnail = to_public_url(BUCKET_PRODUCT_IMAGES, str(c["product_image_filename"]))
    else:
        thumbnail = f"/generated_assets/{cid_str}.jpg"

    # Settings
    prod_name = c.get("product_name") or "Featured Product"
    prod_desc = c.get("product_description") or c.get("description") or f"Promotion for {prod_name}"
    store_loc = f"{c.get('city', 'Los Angeles')}, {c.get('state', 'CA')}"

    prod_files: list[str] = []
    if c.get("product_image_filename"):
        prod_files.append(to_public_url(BUCKET_PRODUCT_IMAGES, str(c["product_image_filename"])))

    settings = {
        "overall": {
            "prompt": c.get("target_audience") or f"In-store retail video campaign for {prod_name} at {c.get('store_name', 'Flagship Store')}",
            "files": [],
        },
        "items": {
            "prompt": f"{prod_name}: {prod_desc}",
            "files": prod_files,
        },
        "people": {
            "prompt": "Diverse cast of contemporary models with poised editorial presence",
            "files": [],
        },
        "performance": {
            "prompt": "Walking naturally and posing to showcase the featured product in store",
            "files": [],
        },
        "setting": {
            "prompt": f"Premium retail store environment in {store_loc}",
            "files": [],
        },
        "audio": {
            "prompt": "Upbeat contemporary background music with subtle commercial flair",
            "files": [],
        },
        "languages": ["en-US"],
        "guidelines": [],
        "format": {
            "duration": 8,
            "aspect_ratios": ["16:9"],
            "resolution": "1080p",
        },
        "testing": {
            "variants_per_generation": 10,
            "rules": "/api/v1/videos/options",
            "duration": 24,
        },
    }

    return {
        "id": cid_str,
        "name": c.get("name") or f"Campaign #{cid_str}",
        "owner": c.get("owner") or "cid@domain.com",
        "shared_with": list(c.get("shared_with") or ["tommy@domain.com", "fred@domain.com"]),
        "created_date": created_dt,
        "modified_date": mod_dt,
        "is_template": bool(c.get("is_template", False)),
        "is_favorite": bool(c.get("is_favorite", False)),
        "is_archived": bool(c.get("is_archived", (str(c.get("status") or "").lower() == "archived"))),
        "status": st,
        "status_meta": status_meta,
        "thumbnail": thumbnail,
        "description": c.get("description") or c.get("target_audience") or f"Campaign for {prod_name}",
        "settings": settings,
        "videos": ux_videos,
    }


# ============================================================================
# CORE API GATEWAY SERVICE
# ============================================================================


class APIGatewayService:
    """Transport-independent service implementing all API Gateway routes."""

    def __init__(self, auto_init_db: bool = True) -> None:
        if auto_init_db:
            self.ensure_initialized()

    def ensure_initialized(self) -> None:
        """Ensure SQLite schema exists and demo data is populated if empty."""
        init_database()
        try:
            with get_db_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM campaigns")
                row = cursor.fetchone()
                count = row["cnt"] if row else 0
            if count == 0:
                seed_demo_data()
        except Exception:
            pass

    # ------------------------------------------------------------------------
    # 1. OVERVIEW, HEALTH & POSTER WORKFLOW STEPS
    # ------------------------------------------------------------------------

    def get_health(self) -> dict[str, Any]:
        """Return API gateway health, active mode, model IDs, and DB counts."""
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM campaigns")
            campaigns_cnt = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) as cnt FROM products")
            products_cnt = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) as cnt FROM campaign_videos")
            videos_cnt = cursor.fetchone()["cnt"]

        return {
            "status": "healthy",
            "gateway_version": GATEWAY_VERSION,
            "app_mode": APP_MODE,
            "demo_dataset": str(DEMO_DATASET.value if hasattr(DEMO_DATASET, "value") else DEMO_DATASET),
            "storage_mode": "gcs" if GCS_BUCKET else "local",
            "models": {
                "agent_model": AGENT_MODEL,
                "image_generation_model": IMAGE_GENERATION_MODEL,
                "video_gen_model": VIDEO_GEN_MODEL,
                "omni_edit_model": OMNI_EDIT_MODEL,
                "omni_edit_enabled": ENABLE_OMNI_EDIT,
            },
            "counts": {
                "campaigns": campaigns_cnt,
                "products": products_cnt,
                "videos": videos_cnt,
                "agents": 4,
            },
        }

    def get_overview(self) -> dict[str, Any]:
        """Return hero banner metrics, old-vs-new comparison, live KPIs, and workflow steps."""
        summary = get_activation_summary()
        placeholders = ",".join("?" for _ in FASHION_CATEGORIES)
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM campaigns")
            campaigns_cnt = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) as cnt FROM products")
            products_cnt = cursor.fetchone()["cnt"]
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM products WHERE LOWER(category) IN ({placeholders})",
                list(FASHION_CATEGORIES),
            )
            fashion_cnt = cursor.fetchone()["cnt"]
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM products WHERE LOWER(category) NOT IN ({placeholders})",
                list(FASHION_CATEGORIES),
            )
            retail_cnt = cursor.fetchone()["cnt"]
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(impressions), 0) as total_impressions,
                    COALESCE(SUM(revenue), 0.0) as total_revenue,
                    COALESCE(AVG(dwell_time_seconds), 0.0) as avg_dwell_time,
                    COALESCE(SUM(circulation), 0) as total_circulation
                FROM video_metrics
                """
            )
            m_row = dict(cursor.fetchone())

        total_imp = int(m_row["total_impressions"] or 0)
        total_rev = float(m_row["total_revenue"] or 0.0)
        overall_rpi = round(total_rev / total_imp, 4) if total_imp > 0 else 0.0

        return {
            "status": "success",
            "title": "Ad Video Optimization Agent",
            "subtitle": "From a single product image to hundreds of localized video ads — generated, tested, and optimized by AI",
            "hero_highlights": [
                {"metric": "10x", "label": "Faster Creative Production"},
                {"metric": "100s", "label": "of Personalized Videos"},
                {"metric": "4", "label": "AI Agents Working Together"},
            ],
            "value_comparison": {
                "old_way": {
                    "duration": "4-6 weeks",
                    "description": "One generic video for all locations, manual shoots, no creative testing",
                },
                "new_way": {
                    "duration": "<10 minutes",
                    "description": "Localized videos per demographic, continuous optimization",
                },
            },
            "powered_by": [
                "ADK (Agent Development Kit)",
                "Gemini 3 Pro",
                "Veo 3.1",
                "Agent Engine",
                "Gemini Enterprise",
                "Cloud Run",
            ],
            "live_summary": {
                "campaigns_count": campaigns_cnt,
                "products_count": products_cnt,
                "fashion_products_count": fashion_cnt,
                "retail_core_products_count": retail_cnt,
                "videos_by_status": summary.get("by_status", {}),
                "total_videos": summary.get("total_videos", 0),
                "total_impressions": total_imp,
                "total_revenue": round(total_rev, 2),
                "overall_rpi": overall_rpi,
                "avg_dwell_time_seconds": round(float(m_row["avg_dwell_time"] or 0.0), 2),
                "total_circulation": int(m_row["total_circulation"] or 0),
            },
            "workflow_steps": POSTER_WORKFLOW_STEPS,
            "agents": AGENTS_METADATA,
        }

    def get_use_cases(self) -> dict[str, Any]:
        """Return all 6 poster steps and their UX API mappings."""
        return {
            "status": "success",
            "poster_asset": "/assets/use-case-poster.jpeg",
            "total_steps": len(POSTER_WORKFLOW_STEPS),
            "steps": POSTER_WORKFLOW_STEPS,
        }

    # ------------------------------------------------------------------------
    # 2. STEP 1: DISCOVER YOUR AI TEAM & AGENT CHAT
    # ------------------------------------------------------------------------

    def get_discover(self) -> dict[str, Any]:
        """Return combined Step 1 payload: AI team, current campaigns, and product catalog summary."""
        campaigns_res = self.list_campaigns_filtered()
        products_res = self.list_products_filtered()
        return {
            "status": "success",
            "step": POSTER_WORKFLOW_STEPS[0],
            "agents": AGENTS_METADATA,
            "campaigns": campaigns_res.get("campaigns", []),
            "campaigns_count": campaigns_res.get("total_count", len(campaigns_res.get("campaigns", []))),
            "products_summary": {
                "total_count": products_res["total_count"],
                "by_category": products_res["by_category"],
                "featured_products": products_res["products"][:8],
            },
            "sample_prompts": [step["sample_prompt"] for step in POSTER_WORKFLOW_STEPS],
        }

    def list_agents(self) -> dict[str, Any]:
        """List all 4 specialized agents + root coordinator."""
        return {
            "status": "success",
            "total_specialized_agents": 4,
            "coordinator": AGENTS_METADATA[0],
            "specialized_agents": AGENTS_METADATA[1:],
            "all_agents": AGENTS_METADATA,
        }

    def get_agent_info(self, agent_name: str) -> dict[str, Any]:
        """Return metadata for a specific agent by name."""
        norm = agent_name.strip().lower()
        for agent in AGENTS_METADATA:
            if norm in (agent["name"].lower(), agent["internal_name"].lower(), agent["display_name"].lower()):
                return {"status": "success", "agent": agent}
        return {
            "status": "error",
            "error": f"Agent '{agent_name}' not found. Valid agents: root_agent, campaign_agent, media_agent, review_agent, analytics_agent.",
        }

    def chat_with_agent(self, req: AgentChatRequest) -> dict[str, Any]:
        """Route a natural-language prompt to the appropriate agent & tools.

        Supports all 6 poster prompts out of the box and optionally invokes the
        live ADK Runner when `prefer_live_agent=True` and credentials exist.
        """
        prompt = (req.prompt or "").strip()
        if not prompt:
            return {"status": "error", "error": "Prompt cannot be empty."}

        lower = prompt.lower()
        tools_invoked: list[str] = []
        routed_agent = req.agent_name or "root_agent"
        structured_result: dict[str, Any] = {}
        reply = ""

        # Optional live ADK execution if explicitly requested and credentials exist
        if req.prefer_live_agent and (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CLOUD_PROJECT")):
            try:
                live_reply = self._try_live_adk_chat(prompt, req.user_id, req.session_id)
                if live_reply:
                    return {
                        "status": "success",
                        "execution_mode": "live_adk",
                        "prompt": prompt,
                        "routed_agent": routed_agent,
                        "reply": live_reply,
                    }
            except Exception:
                pass

        # Step 6 intent: "Apply the winning formula from video 5 to campaign 3"
        if "winning formula" in lower or ("apply" in lower and "formula" in lower):
            routed_agent = "media_agent"
            tools_invoked.append("apply_winning_formula")
            vid_match = re.search(r"video\s+#?(\d+)", lower)
            camp_matches = re.findall(r"campaign\s+#?(\d+)", lower)
            source_video_id = int(vid_match.group(1)) if vid_match else None
            target_campaign_id = int(camp_matches[-1]) if camp_matches else 3
            source_campaign_id = int(camp_matches[0]) if len(camp_matches) > 1 else None

            wf_res = self.apply_winning_formula(
                WinningFormulaApplyRequest(
                    target_campaign_id=target_campaign_id,
                    source_video_id=source_video_id,
                    source_campaign_id=source_campaign_id,
                    dry_run=req.dry_run_media,
                )
            )
            structured_result = wf_res
            if wf_res.get("status") == "success":
                formula = wf_res.get("winning_formula", {})
                new_vid = wf_res.get("new_video", {})
                reply = (
                    f"Applied the winning formula from video #{formula.get('source_video_id')} "
                    f"({formula.get('model_ethnicity')} model, {formula.get('setting')} setting, "
                    f"{formula.get('time_of_day')} lighting, {formula.get('mood')} mood — "
                    f"RPI ${formula.get('rpi', 0):.4f}) to Campaign #{target_campaign_id} "
                    f"({wf_res.get('target_campaign', {}).get('name', '')}). "
                    f"Created video #{new_vid.get('video_id')} in 'generated' (pending review) status."
                )
            else:
                reply = wf_res.get("error", "Could not apply winning formula.")

        # Step 3 intent: "Activate videos 5 and 7" / "Activate video 5"
        elif "activate" in lower and "video" in lower:
            routed_agent = "review_agent"
            nums = [int(n) for n in re.findall(r"\b(\d+)\b", lower)]
            if len(nums) > 1:
                tools_invoked.append("activate_batch")
                structured_result = activate_batch(video_ids=nums)
                reply = structured_result.get(
                    "message",
                    f"Processed batch activation for videos {nums}.",
                )
            elif len(nums) == 1:
                tools_invoked.append("activate_video")
                structured_result = activate_video(video_id=nums[0])
                reply = structured_result.get(
                    "message",
                    f"Activated video #{nums[0]}.",
                )
            else:
                tools_invoked.append("list_pending_videos")
                structured_result = list_pending_videos()
                reply = "Here are the pending videos ready for activation."

        # Step 3 intent: pending / review table
        elif any(k in lower for k in ("pending video", "review table", "waiting for review", "stay in control")):
            routed_agent = "review_agent"
            tools_invoked.extend(["get_video_review_table", "get_activation_summary"])
            structured_result = {
                "review_table": get_video_review_table(),
                "summary": get_activation_summary(),
            }
            reply = "Loaded the Human-in-the-Loop video review table and activation summary."

        # Step 5 intent: "Compare West Coast vs East Coast performance" or map/region queries
        elif any(k in lower for k in ("west coast", "east coast", "region", "heat map", "heatmap", "map")):
            routed_agent = "analytics_agent"
            tools_invoked.extend(["get_regional_comparison", "get_campaign_map_data"])
            reg = self.get_regional_comparison()
            maps = self.get_campaign_map_data()
            structured_result = {"regional_comparison": reg, "map_data": maps}
            west = reg.get("regions", {}).get("West Coast", {})
            east = reg.get("regions", {}).get("East Coast", {})
            reply = (
                f"Regional Comparison: West Coast (RPI ${west.get('rpi', 0):.4f}, "
                f"Revenue ${west.get('total_revenue', 0):,.2f}, "
                f"Impressions {west.get('total_impressions', 0):,}) vs. "
                f"East Coast (RPI ${east.get('rpi', 0):.4f}, "
                f"Revenue ${east.get('total_revenue', 0):,.2f}, "
                f"Impressions {east.get('total_impressions', 0):,}). "
                f"Leading region by RPI: {reg.get('top_region_by_rpi', 'N/A')}."
            )

        # Step 4 intent: "Which videos have the highest RPI?" or top performing / metrics
        elif any(k in lower for k in ("highest rpi", "top performing", "best performing", "measure what matters", "metrics", "dwell time", "circulation")):
            routed_agent = "analytics_agent"
            tools_invoked.append("get_top_performing_ads")
            metric = "rpi"
            if "dwell" in lower:
                metric = "dwell_time"
            elif "revenue" in lower and "rpi" not in lower:
                metric = "revenue"
            elif "impression" in lower and "rpi" not in lower:
                metric = "impressions"
            structured_result = self.get_top_performing(metric=metric, limit=10)
            top_vids = structured_result.get("top_campaign_videos", [])
            if top_vids:
                best = top_vids[0]
                reply = (
                    f"Top performing video by {metric.upper()} is Video #{best['video_id']} "
                    f"({best.get('product_name', 'Product')} in {best.get('campaign_name', 'Campaign')}) "
                    f"with RPI ${best.get('rpi', 0):.4f}, Revenue ${best.get('total_revenue', 0):,.2f}, "
                    f"Impressions {best.get('total_impressions', 0):,}, and Avg Dwell Time {best.get('avg_dwell_time_seconds', 0):.1f}s."
                )
            else:
                reply = structured_result.get("message", "Retrieved top performing ads.")

        # Step 2 intent: "Generate a video with a European model on a rooftop at sunset, sophisticated mood"
        elif any(k in lower for k in ("generate a video", "create a video", "generate video", "make a video")):
            routed_agent = "media_agent"
            tools_invoked.append("generate_product_video")
            comp = self._parse_components_from_prompt(lower)
            camp_match = re.search(r"campaign\s+#?(\d+)", lower)
            campaign_id = int(camp_match.group(1)) if camp_match else 1
            gen_res = self.generate_video(
                VideoGenerateRequest(
                    campaign_id=campaign_id,
                    components=comp,
                    dry_run=req.dry_run_media,
                )
            )
            structured_result = gen_res
            vid = gen_res.get("video", {})
            reply = (
                f"Generated video #{vid.get('video_id')} for Campaign #{campaign_id} "
                f"with {comp.model_ethnicity} model, {comp.setting} setting at {comp.time_of_day}, "
                f"{comp.mood} mood, {comp.lighting} lighting, and {comp.camera_movement} camera movement. "
                f"Status is 'generated' (awaiting human review before activation)."
            )

        # Step 1 intent: "What agents are available and what are our current campaigns?"
        else:
            routed_agent = "root_agent"
            tools_invoked.extend(["list_agents", "list_campaigns", "list_products"])
            discover = self.get_discover()
            structured_result = discover
            campaigns = discover.get("campaigns", [])
            camp_names = ", ".join(f"#{c['id']} {c['name']} ({c['city']}, {c['state']})" for c in campaigns[:4])
            reply = (
                f"We have 4 specialized AI agents (Campaign Agent, Media Agent, Review Agent, and Analytics Agent) "
                f"coordinated by the Root Agent, plus {discover['products_summary']['total_count']} products across "
                f"{len(discover['products_summary']['by_category'])} categories and {len(campaigns)} active campaigns: {camp_names}."
            )

        return {
            "status": "success",
            "execution_mode": "gateway_router",
            "prompt": prompt,
            "routed_agent": routed_agent,
            "tools_invoked": tools_invoked,
            "reply": reply,
            "data": structured_result,
        }

    def _parse_components_from_prompt(self, lower_prompt: str) -> VideoComponentConfig:
        """Extract configurable video components from natural-language prompt text."""
        comp = VideoComponentConfig()
        for eth in ModelEthnicity:
            if eth.value.replace("_", " ") in lower_prompt or eth.value in lower_prompt:
                comp.model_ethnicity = eth.value
                break
        for s in Setting:
            if s.value in lower_prompt:
                comp.setting = s.value
                break
        for t in TimeOfDay:
            if t.value.replace("_", " ") in lower_prompt or t.value in lower_prompt:
                comp.time_of_day = t.value
                if t == TimeOfDay.SUNSET or t == TimeOfDay.GOLDEN_HOUR:
                    comp.lighting = Lighting.GOLDEN_BACKLIGHT.value
                break
        for m in Mood:
            if m.value in lower_prompt:
                comp.mood = m.value
                break
        for light in Lighting:
            if light.value.replace("_", " ") in lower_prompt or light.value in lower_prompt:
                comp.lighting = light.value
                break
        for cam in CameraMovement:
            if cam.value.replace("_", " ") in lower_prompt or cam.value in lower_prompt:
                comp.camera_movement = cam.value
                break
        for act in Activity:
            if act.value in lower_prompt:
                comp.activity = act.value
                break
        for prop_item in SUGGESTED_PROPS:
            pid = prop_item["id"]
            if pid.replace("_", " ") in lower_prompt or pid in lower_prompt:
                comp.props.append(pid)
        if "product-hero" in lower_prompt or "product hero" in lower_prompt:
            comp.presentation_mode = "product-hero"
        elif "lifestyle" in lower_prompt:
            comp.presentation_mode = "lifestyle"
        return comp

    def _try_live_adk_chat(self, prompt: str, user_id: str, session_id: str | None) -> str | None:
        """Run a prompt through the live ADK Runner if google-adk is available."""
        import asyncio

        from google.adk.runners import InMemoryRunner
        from google.genai import types as genai_types

        from app.agent import root_agent

        async def _run() -> str:
            runner = InMemoryRunner(agent=root_agent, app_name="ad_campaign_agent")
            session = await runner.session_service.create_session(
                app_name="ad_campaign_agent",
                user_id=user_id,
                session_id=session_id,
            )
            content = genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=prompt)],
            )
            chunks: list[str] = []
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            chunks.append(part.text)
            return "\n".join(chunks).strip()

        return asyncio.run(_run())

    # ------------------------------------------------------------------------
    # 3. CAMPAIGNS & PRODUCTS ENDPOINTS
    # ------------------------------------------------------------------------

    def list_campaigns_filtered(
        self,
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        product_id: int | None = None,
    ) -> dict[str, Any]:
        """List campaigns with optional filters and enriched city/state/region fields."""
        base = list_campaigns(status=status, product_id=product_id)
        campaigns = base.get("campaigns", [])

        enriched: list[dict[str, Any]] = []
        for c in campaigns:
            c_copy = dict(c)
            if "city" not in c_copy or "state" not in c_copy:
                loc_str = str(c_copy.get("location") or "")
                if "," in loc_str:
                    parts = [p.strip() for p in loc_str.split(",", 1)]
                    c_copy.setdefault("city", parts[0])
                    c_copy.setdefault("state", parts[1])
                else:
                    c_copy.setdefault("city", loc_str)
                    c_copy.setdefault("state", "")
            st = (c_copy.get("state") or "").upper()
            c_copy["state"] = st
            c_copy["region"] = REGION_BY_STATE.get(st, "Other")
            coords = CITY_COORDINATES.get((str(c_copy.get("city") or "").lower(), st))
            if coords:
                c_copy["latitude"] = coords[0]
                c_copy["longitude"] = coords[1]
            enriched.append(c_copy)

        if category:
            enriched = [c for c in enriched if (c.get("category") or "").lower() == category.lower()]
        if state:
            enriched = [c for c in enriched if (c.get("state") or "").upper() == state.upper()]

        return {
            "status": "success",
            "total_count": len(enriched),
            "campaigns": enriched,
        }

    def create_new_campaign(self, req: CampaignCreateRequest) -> dict[str, Any]:
        """Create a new campaign using `campaign_tools.create_campaign`."""
        category_aliases = {
            "seasonal": "summer",
            "promotional": "always-on",
            "everyday": "essentials",
            "business": "professional",
            "evening": "formal",
        }
        norm_cat = (req.category or "").strip().lower()
        mapped_cat = category_aliases.get(norm_cat, norm_cat)
        if mapped_cat not in CAMPAIGN_CATEGORIES:
            mapped_cat = "always-on"

        return create_campaign(
            product_id=req.product_id,
            store_name=req.store_name,
            city=req.city,
            state=req.state,
            name=req.name,
            description=req.target_audience,
            category=mapped_cat,
        )

    def get_campaign_by_id(self, campaign_id: int) -> dict[str, Any]:
        """Get full campaign details including product and videos."""
        res = get_campaign(campaign_id=campaign_id)
        if res.get("status") == "success":
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM campaign_videos WHERE campaign_id = ? ORDER BY id DESC",
                    (campaign_id,),
                )
                videos = [_enrich_video_row(dict(r)) for r in cursor.fetchall()]
            res["campaign_videos"] = videos
            camp_dict = res.get("campaign", {})
            st = (camp_dict.get("state") or "").upper()
            camp_dict["region"] = REGION_BY_STATE.get(st, "Other")
            coords = CITY_COORDINATES.get((str(camp_dict.get("city") or "").lower(), st))
            if coords:
                camp_dict["latitude"] = coords[0]
                camp_dict["longitude"] = coords[1]
        return res

    def update_campaign_by_id(self, campaign_id: int, req: CampaignUpdateRequest) -> dict[str, Any]:
        """Update an existing campaign using `campaign_tools.update_campaign`."""
        return update_campaign(
            campaign_id=campaign_id,
            name=req.name,
            description=req.target_audience,
            status=req.status,
        )

    def list_products_filtered(
        self,
        category: str | None = None,
        garment_type: str | None = None,
        style: str | None = None,
        season: str | None = None,
        search: str | None = None,
        catalog_source: str = "all",
    ) -> dict[str, Any]:
        """List products from the database with rich filtering and category counts."""
        query = "SELECT * FROM products WHERE 1=1"
        params: list[Any] = []

        if category:
            if category.lower() == "fashion":
                placeholders = ",".join("?" for _ in FASHION_CATEGORIES)
                query += f" AND LOWER(category) IN ({placeholders})"
                params.extend(FASHION_CATEGORIES)
            else:
                query += " AND LOWER(category) = LOWER(?)"
                params.append(category)
        if garment_type:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(garment_type)
        if style:
            query += " AND LOWER(style) LIKE LOWER(?)"
            params.append(f"%{style}%")
        if search:
            query += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(details) LIKE LOWER(?) OR LOWER(color) LIKE LOWER(?) OR LOWER(metadata) LIKE LOWER(?))"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
        if catalog_source == "fashion":
            placeholders = ",".join("?" for _ in FASHION_CATEGORIES)
            query += f" AND LOWER(category) IN ({placeholders})"
            params.extend(FASHION_CATEGORIES)
        elif catalog_source == "retail_core":
            placeholders = ",".join("?" for _ in FASHION_CATEGORIES)
            query += f" AND LOWER(category) NOT IN ({placeholders})"
            params.extend(FASHION_CATEGORIES)

        query += " ORDER BY id ASC"

        with get_db_cursor() as cursor:
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

        products: list[dict[str, Any]] = []
        by_category: dict[str, int] = {}
        for r in rows:
            enriched = _fetch_product_row(r["id"]) or r
            if season and (enriched.get("season") or "").lower() not in (season.lower(), "all-season"):
                continue
            cat = (enriched.get("category") or "fashion").lower()
            by_category[cat] = by_category.get(cat, 0) + 1
            products.append(enriched)

        return {
            "status": "success",
            "total_count": len(products),
            "by_category": by_category,
            "products": products,
        }

    def get_product_categories(self) -> dict[str, Any]:
        """Return all valid product categories, default presentation modes, and DB counts."""
        with get_db_cursor() as cursor:
            cursor.execute("SELECT category, COUNT(*) as cnt FROM products GROUP BY category")
            counts = {r["category"]: r["cnt"] for r in cursor.fetchall()}

        categories = [
            {
                "category": cat,
                "default_presentation_mode": CATEGORY_DEFAULT_PRESENTATION.get(cat, "model"),
                "product_count": counts.get(cat, 0),
            }
            for cat in sorted(VALID_CATEGORIES)
        ]
        return {
            "status": "success",
            "valid_categories": sorted(VALID_CATEGORIES),
            "presentation_modes": list(VALID_PRESENTATION_MODES),
            "categories": categories,
        }

    def get_product_by_id(self, product_id: int) -> dict[str, Any]:
        """Get full details for a single product."""
        product = _fetch_product_row(product_id)
        if not product:
            return {"status": "error", "error": f"Product with ID {product_id} not found."}
        return {"status": "success", "product": product}

    def create_new_product(self, req: ProductCreateRequest) -> dict[str, Any]:
        """Create/onboard a new product in the catalog."""
        cat = req.category.strip().lower()
        if cat not in VALID_CATEGORIES:
            return {
                "status": "error",
                "error": f"Invalid category '{req.category}'. Valid categories: {sorted(VALID_CATEGORIES)}",
            }
        slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-") or "product"
        img_filename = req.image_filename or f"{slug}.png"
        attrs = dict(req.attributes or {})
        if req.style and "style" not in attrs:
            attrs["style"] = req.style
        if req.color and "color" not in attrs:
            attrs["color"] = req.color
        if req.material and "fabric" not in attrs:
            attrs["fabric"] = req.material
        if req.season and "season" not in attrs:
            attrs["season"] = req.season

        prod = Product(
            name=req.name,
            category=cat,
            description=req.description or f"{req.name} ({cat})",
            image_filename=img_filename,
            local_path=f"{BUCKET_PRODUCT_IMAGES}/{img_filename}",
            attributes=attrs,
        )
        stored = insert_product(prod)
        new_id = int(stored.id) if stored and stored.id is not None else 0
        return {
            "status": "success",
            "message": f"Created product '{req.name}' (ID {new_id}) in category '{cat}'.",
            "product": _fetch_product_row(new_id),
        }

    def import_products_folder(self, req: ProductImportFolderRequest) -> dict[str, Any]:
        """Bulk-import products from a local image folder."""
        try:
            from app.tools.product_tools import import_products_from_folder

            return import_products_from_folder(folder_path=req.folder_path, category=req.category)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def generate_product_reference_image(
        self, product_id: int, req: ProductGenerateImageRequest
    ) -> dict[str, Any]:
        """Generate a product reference image (supports dry_run or live Gemini Image)."""
        product = _fetch_product_row(product_id)
        if not product:
            return {"status": "error", "error": f"Product {product_id} not found."}
        if req.dry_run:
            slug = re.sub(r"[^a-z0-9]+", "-", product["name"].lower()).strip("-")
            filename = product.get("image_filename") or f"{slug}.png"
            return {
                "status": "success",
                "dry_run": True,
                "product_id": product_id,
                "image_filename": filename,
                "image_url": to_public_url(BUCKET_PRODUCT_IMAGES, filename),
                "prompt": req.custom_prompt
                or f"Studio product reference photo of {product['name']}: {product.get('description', '')}",
            }
        try:
            from app.tools.product_tools import generate_product_image

            return generate_product_image(product_id=product_id, custom_prompt=req.custom_prompt)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def upload_product_reference_image(
        self, product_id: int, req: ProductUploadImageRequest
    ) -> dict[str, Any]:
        """Attach an existing local image file to a product."""
        try:
            from app.tools.product_tools import upload_product_image

            return upload_product_image(product_id=product_id, image_path=req.source_path)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------------
    # 4. STEP 2: CONFIGURABLE VIDEO GENERATION & MEDIA OPTIONS
    # ------------------------------------------------------------------------

    def get_video_component_options(self) -> dict[str, Any]:
        """Return all 15+ configurable video component options for UX form controls."""
        return {
            "status": "success",
            "component_groups": {
                "subjects": {
                    "label": "Subjects & Model Diversity",
                    "description": "Configure the person/model, presentation mode, pose/activity, and props.",
                    "presentation_modes": [
                        {
                            "value": mode,
                            "label": mode.replace("-", " ").title(),
                            "default_for_categories": [
                                c for c, m in CATEGORY_DEFAULT_PRESENTATION.items() if m == mode
                            ],
                        }
                        for mode in VALID_PRESENTATION_MODES
                    ],
                    "model_ethnicities": [
                        {
                            "value": e.value,
                            "label": e.value.replace("_", " ").title(),
                            "description": ETHNICITY_DESCRIPTIONS[e],
                        }
                        for e in ModelEthnicity
                    ],
                    "activities": [
                        {
                            "value": a.value,
                            "label": a.value.replace("_", " ").title(),
                            "description": ACTIVITY_DESCRIPTIONS[a],
                        }
                        for a in Activity
                    ],
                    "subject_counts": [s.value for s in SubjectCount],
                    "garment_visibility_options": ["full", "partial", "accent"],
                    "suggested_props": SUGGESTED_PROPS,
                },
                "settings": {
                    "label": "Settings & Environment",
                    "description": "Configure location, indoor/outdoor type, time of day, weather, and season.",
                    "settings": [
                        {
                            "value": s.value,
                            "label": s.value.replace("_", " ").title(),
                            "description": SETTING_DESCRIPTIONS[s],
                        }
                        for s in Setting
                    ],
                    "setting_types": [st.value for st in SettingType],
                    "times_of_day": [
                        {
                            "value": t.value,
                            "label": t.value.replace("_", " ").title(),
                            "description": TIME_DESCRIPTIONS[t],
                        }
                        for t in TimeOfDay
                    ],
                    "weather_conditions": [w.value for w in WeatherCondition],
                    "seasons": ["spring", "summer", "fall", "winter"],
                    "background_complexities": ["minimal", "moderate", "busy"],
                },
                "tone": {
                    "label": "Tone, Mood & Energy",
                    "description": "Configure emotional mood, intensity, warmth, energy pacing, and motion amount.",
                    "moods": [
                        {
                            "value": m.value,
                            "label": m.value.replace("_", " ").title(),
                            "description": MOOD_DESCRIPTIONS.get(m, m.value),
                        }
                        for m in Mood
                    ],
                    "additional_moods": ["editorial", "warm", "nostalgic", "luxurious"],
                    "mood_intensities": [mi.value for mi in MoodIntensity],
                    "energy_levels": [el.value for el in EnergyLevel],
                    "movement_amounts": [ma.value for ma in MovementAmount],
                },
                "visual_style": {
                    "label": "Lighting, Visual Style & Color",
                    "description": "Configure lighting setup, cinematic aesthetic, color grading, and saturation.",
                    "lightings": [
                        {
                            "value": l.value,
                            "label": l.value.replace("_", " ").title(),
                            "description": LIGHTING_DESCRIPTIONS[l],
                        }
                        for l in Lighting
                    ],
                    "lighting_styles": [ls.value for ls in LightingStyle],
                    "visual_styles": [vs.value for vs in VisualStyle],
                    "color_gradings": ["warm", "neutral", "cool", "vibrant", "desaturated"],
                    "color_saturations": [cs.value for cs in ColorSaturation],
                },
                "camera": {
                    "label": "Camera Movement & Framing",
                    "description": "Configure camera motion, framing angle, and display aspect ratio.",
                    "camera_movements": [
                        {
                            "value": c.value,
                            "label": c.value.replace("_", " ").title(),
                            "description": CAMERA_DESCRIPTIONS[c],
                        }
                        for c in CameraMovement
                    ],
                    "camera_angles": [ca.value for ca in CameraAngle],
                    "aspect_ratios": [ar.value for ar in AspectRatio],
                },
                "production": {
                    "label": "Audio & Production Pipeline",
                    "description": "Configure duration, two-stage Gemini+Veo pipeline, and audio track.",
                    "durations_seconds": [4, 6, 8],
                    "audio_types": [at.value for at in AudioType],
                    "music_tempos": [mt.value for mt in MusicTempo],
                    "default_use_two_stage": True,
                },
            },
            "presets": self.get_video_presets()["presets"],
        }

    def get_video_presets(self) -> dict[str, Any]:
        """Return all curated presets for 1-click UX selection."""
        presets: dict[str, Any] = {}
        for name, var in PRESET_VARIATIONS.items():
            presets[name] = {
                "name": name,
                "label": name.replace("_", " ").title(),
                "presentation_mode": "model",
                "model_ethnicity": var.model_ethnicity.value,
                "setting": var.setting.value,
                "time_of_day": var.time_of_day.value,
                "mood": var.mood.value,
                "lighting": var.lighting.value,
                "camera_movement": var.camera_movement.value,
                "activity": var.activity.value,
                "props": list(var.props or []),
                "color_grading": var.color_grading,
                "aspect_ratio": var.aspect_ratio,
                "duration_seconds": var.duration_seconds,
            }
        for name, cfg in CATEGORY_PRESETS.items():
            presets[name] = {
                "name": name,
                "label": name.replace("_", " ").title(),
                **cfg,
            }
        return {
            "status": "success",
            "total_presets": len(presets),
            "presets": presets,
        }

    def preview_video_prompts(self, req: PromptPreviewRequest) -> dict[str, Any]:
        """Build and return Stage 1 & Stage 2 prompts for any user-configured video components."""
        product_id = req.product_id
        if product_id is None and req.campaign_id is not None:
            camp = get_campaign(req.campaign_id)
            if camp.get("status") == "success":
                product_id = camp["campaign"].get("product_id")
        if product_id is None:
            product_id = 1

        product_row = _fetch_product_row(product_id) or {
            "id": product_id,
            "name": "Featured Product",
            "description": "Retail product",
            "category": "fashion",
            "garment_type": "dress",
            "color": "blue",
            "style": "modern",
            "material": "silk",
        }

        variation, video_props, prompts = _build_variation_and_properties(req.components, product_row)
        return {
            "status": "success",
            "product": {
                "id": product_row.get("id"),
                "name": product_row.get("name"),
                "category": product_row.get("category", "fashion"),
                "presentation_mode": prompts["presentation_mode"],
            },
            "variation_name": variation.variation_name,
            "filename_suffix": variation.to_filename_suffix(),
            "variation_params": {
                **variation.to_dict(),
                "presentation_mode": prompts["presentation_mode"],
                "visual_style": req.components.visual_style,
                "camera_angle": req.components.camera_angle,
                "energy_level": req.components.energy_level,
                "mood_intensity": req.components.mood_intensity,
                "weather": req.components.weather,
                "season": req.components.season,
                "location_detail": req.components.location_detail,
                "model_description": req.components.model_description,
                "dominant_colors": req.components.dominant_colors,
                "style_tags": req.components.style_tags,
            },
            "video_properties": video_props.to_dict(),
            "prompts": prompts,
        }

    def generate_video(self, req: VideoGenerateRequest) -> dict[str, Any]:
        """Generate a video with all user-configured components (subjects, settings, tone, etc.)."""
        camp_res = get_campaign(req.campaign_id)
        if camp_res.get("status") != "success":
            return {"status": "error", "error": f"Campaign {req.campaign_id} not found."}
        campaign = camp_res["campaign"]

        product_id = req.product_id or campaign.get("product_id") or 1
        product_row = _fetch_product_row(int(product_id))
        if not product_row:
            return {"status": "error", "error": f"Product {product_id} not found."}

        components = _merge_video_components(req)
        variation, video_props, prompts = _build_variation_and_properties(components, product_row)

        # If live generation is requested (`dry_run=False`), invoke the Media Agent tool
        if not req.dry_run:
            try:
                from app.tools.media_tools import generate_product_video

                live_res = generate_product_video(
                    campaign_id=req.campaign_id,
                    product_id=int(product_id),
                    model_ethnicity=variation.model_ethnicity.value,
                    setting=variation.setting.value,
                    time_of_day=variation.time_of_day.value,
                    mood=variation.mood.value,
                    lighting=variation.lighting.value,
                    camera_movement=variation.camera_movement.value,
                    activity=variation.activity.value,
                    props=variation.props,
                    color_grading=variation.color_grading,
                    aspect_ratio=variation.aspect_ratio,
                    duration_seconds=variation.duration_seconds,
                    use_two_stage=components.use_two_stage,
                    presentation_mode=prompts["presentation_mode"],
                )
                if live_res.get("status") == "success":
                    return live_res
            except Exception as exc:
                return {"status": "error", "error": f"Live video generation failed: {exc}"}

        # Dry-run / demo mode: persist a realistic `campaign_videos` record in 'generated' status
        slug = re.sub(r"[^a-z0-9]+", "-", product_row["name"].lower()).strip("-")
        short_hash = hashlib.sha256(
            f"{req.campaign_id}:{product_id}:{variation.variation_name}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:6]
        video_filename = f"{slug}-{short_hash}-{variation.to_filename_suffix()}.mp4"
        video_url = to_public_url(BUCKET_GENERATED, video_filename)

        props_payload = video_props.to_dict()
        variation_payload = {
            **variation.to_dict(),
            "presentation_mode": prompts["presentation_mode"],
            "visual_style": components.visual_style,
            "camera_angle": components.camera_angle,
            "energy_level": components.energy_level,
            "mood_intensity": components.mood_intensity,
            "weather": components.weather,
            "season": components.season,
            "location_detail": components.location_detail,
            "model_description": components.model_description,
            "dominant_colors": components.dominant_colors,
            "style_tags": components.style_tags,
            "custom_instructions": components.custom_instructions,
            "video_properties": props_payload,
        }

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO campaign_videos (
                    campaign_id, product_id, video_filename, gcs_path, local_path,
                    scene_prompt, video_prompt, pipeline_type,
                    variation_name, variation_params,
                    duration_seconds, aspect_ratio, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated')
                """,
                (
                    req.campaign_id,
                    int(product_id),
                    video_filename,
                    video_url,
                    f"{BUCKET_GENERATED}/{video_filename}",
                    prompts["stage1_image_prompt"],
                    prompts["stage2_video_prompt"] if components.use_two_stage else prompts["single_stage_prompt"],
                    "two_stage" if components.use_two_stage else "single_stage",
                    variation.variation_name,
                    json.dumps(variation_payload),
                    variation.duration_seconds,
                    variation.aspect_ratio,
                ),
            )
            video_id = int(cursor.lastrowid)

        return {
            "status": "success",
            "dry_run": req.dry_run,
            "message": (
                f"Generated video #{video_id} ('{variation.variation_name}') for "
                f"campaign '{campaign['name']}'. Status is 'generated' (pending HITL review)."
            ),
            "video": {
                "video_id": video_id,
                "campaign_id": req.campaign_id,
                "campaign_name": campaign["name"],
                "product_id": int(product_id),
                "product_name": product_row["name"],
                "video_filename": video_filename,
                "video_url": video_url,
                "gateway_video_url": f"/api/v1/assets/{BUCKET_GENERATED}/{video_filename}",
                "status": "generated",
                "variation_name": variation.variation_name,
                "variation_params": variation_payload,
                "video_properties": props_payload,
                "duration_seconds": variation.duration_seconds,
                "aspect_ratio": variation.aspect_ratio,
                "prompts": prompts,
            },
        }

    def generate_video_batch(self, req: BatchVideoGenerateRequest) -> dict[str, Any]:
        """Generate multiple video variations in a single call ('Create 100s of video variations')."""
        configs: list[VideoComponentConfig] = []

        if req.variations:
            configs.extend(req.variations)

        if req.preset_names:
            for preset_name in req.preset_names:
                c = req.base_components.model_copy(deep=True)
                c.preset_name = preset_name
                configs.append(c)

        # Matrix / Cartesian product generation if dimension lists are provided
        if any(
            [
                req.model_ethnicities,
                req.settings,
                req.times_of_day,
                req.moods,
                lightings := req.lightings,
                req.camera_movements,
                req.activities,
            ]
        ):
            eths = req.model_ethnicities or [req.base_components.model_ethnicity]
            sets = req.settings or [req.base_components.setting]
            times = req.times_of_day or [req.base_components.time_of_day]
            moods = req.moods or [req.base_components.mood]
            lights = lightings or [req.base_components.lighting]
            cams = req.camera_movements or [req.base_components.camera_movement]
            acts = req.activities or [req.base_components.activity]

            for eth in eths:
                for s in sets:
                    for t in times:
                        for m in moods:
                            for l_val in lights:
                                for cam in cams:
                                    for act in acts:
                                        if len(configs) >= req.max_variations:
                                            break
                                        c = req.base_components.model_copy(deep=True)
                                        c.model_ethnicity = eth
                                        c.setting = s
                                        c.time_of_day = t
                                        c.mood = m
                                        c.lighting = l_val
                                        c.camera_movement = cam
                                        c.activity = act
                                        configs.append(c)

        if not configs:
            # Default: generate 3 diverse variations if none specified
            for preset in ("asian_beach_romantic", "european_rooftop_sophisticated", "latina_urban_confident"):
                c = req.base_components.model_copy(deep=True)
                c.preset_name = preset
                configs.append(c)

        configs = configs[: req.max_variations]
        generated_videos: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for cfg in configs:
            single_req = VideoGenerateRequest(
                campaign_id=req.campaign_id,
                product_id=req.product_id,
                components=cfg,
                preset_name=cfg.preset_name,
                dry_run=req.dry_run,
            )
            res = self.generate_video(single_req)
            if res.get("status") == "success":
                generated_videos.append(res["video"])
            else:
                errors.append(res)

        return {
            "status": "success" if generated_videos else "error",
            "campaign_id": req.campaign_id,
            "requested_count": len(configs),
            "generated_count": len(generated_videos),
            "video_ids": [v["video_id"] for v in generated_videos],
            "videos": generated_videos,
            "errors": errors,
        }

    def get_video_properties_by_id(self, video_id: int) -> dict[str, Any]:
        """Return structured `VideoProperties` and `variation_params` for a video."""
        details = get_video_details(video_id=video_id)
        if details.get("status") == "error":
            return details
        video = details.get("video", {})
        return {
            "status": "success",
            "video_id": video_id,
            "variation_name": video.get("variation_name"),
            "variation_params": video.get("variation_params", {}),
            "video_properties": video.get("video_properties", {}),
            "prompt_used": video.get("prompt_used"),
        }

    def list_seed_images(self, campaign_id: int | None = None) -> dict[str, Any]:
        """List available seed/product images for video generation."""
        products_res = self.list_products_filtered()
        images = [
            {
                "product_id": p["id"],
                "product_name": p["name"],
                "category": p.get("category", "fashion"),
                "image_filename": p.get("image_filename"),
                "image_url": p.get("image_url"),
                "gateway_asset_url": p.get("gateway_asset_url"),
                "image_status": p.get("image_status"),
            }
            for p in products_res.get("products", [])
            if p.get("image_filename")
        ]
        if campaign_id is not None:
            camp = get_campaign(campaign_id)
            if camp.get("status") == "success":
                pid = camp["campaign"].get("product_id")
                images = [img for img in images if img["product_id"] == pid]
        return {
            "status": "success",
            "total_count": len(images),
            "seed_images": images,
        }

    # ------------------------------------------------------------------------
    # 5. STEP 3: HUMAN-IN-THE-LOOP (HITL) REVIEW & LIFECYCLE
    # ------------------------------------------------------------------------

    def list_videos_filtered(
        self,
        campaign_id: int | None = None,
        status: str | None = None,
        product_id: int | None = None,
        model_ethnicity: str | None = None,
        setting: str | None = None,
        mood: str | None = None,
    ) -> dict[str, Any]:
        """List all videos in `campaign_videos` with rich filtering and metrics."""
        query = """
            SELECT
                cv.*,
                c.name as campaign_name,
                c.store_name,
                c.city,
                c.state,
                p.name as product_name,
                p.category as product_category,
                p.image_filename as product_image_filename,
                COALESCE(SUM(vm.impressions), 0) as total_impressions,
                COALESCE(SUM(vm.revenue), 0.0) as total_revenue,
                COALESCE(AVG(vm.dwell_time_seconds), 0.0) as avg_dwell_time_seconds,
                COALESCE(SUM(vm.circulation), 0) as total_circulation,
                COUNT(vm.id) as metric_days
            FROM campaign_videos cv
            LEFT JOIN campaigns c ON cv.campaign_id = c.id
            LEFT JOIN products p ON cv.product_id = p.id
            LEFT JOIN video_metrics vm ON cv.id = vm.video_id
            WHERE 1=1
        """
        params: list[Any] = []
        if campaign_id is not None:
            query += " AND cv.campaign_id = ?"
            params.append(campaign_id)
        if status:
            query += " AND LOWER(cv.status) = LOWER(?)"
            params.append(status)
        if product_id is not None:
            query += " AND cv.product_id = ?"
            params.append(product_id)

        query += " GROUP BY cv.id ORDER BY cv.id DESC"

        with get_db_cursor() as cursor:
            cursor.execute(query, params)
            rows = [_enrich_video_row(dict(r)) for r in cursor.fetchall()]

        filtered: list[dict[str, Any]] = []
        for r in rows:
            imp = int(r.get("total_impressions") or 0)
            rev = float(r.get("total_revenue") or 0.0)
            r["rpi"] = round(rev / imp, 4) if imp > 0 else 0.0
            vp = r.get("variation_params") or {}
            if model_ethnicity and (vp.get("model_ethnicity") or "").lower() != model_ethnicity.lower():
                continue
            if setting and (vp.get("setting") or "").lower() != setting.lower():
                continue
            if mood and (vp.get("mood") or "").lower() != mood.lower():
                continue
            filtered.append(r)

        return {
            "status": "success",
            "total_count": len(filtered),
            "videos": filtered,
        }

    def edit_video_omni(self, video_id: int, req: VideoOmniEditRequest) -> dict[str, Any]:
        """Run or simulate experimental Gemini Omni Flash post-generation video editing."""
        details = get_video_details(video_id=video_id)
        if details.get("status") == "error":
            return details

        if req.dry_run or not ENABLE_OMNI_EDIT:
            src_video = details.get("video", {})
            return {
                "status": "success",
                "dry_run": True,
                "omni_edit_enabled": ENABLE_OMNI_EDIT,
                "source_video_id": video_id,
                "edit_instruction": req.edit_instruction,
                "model": OMNI_EDIT_MODEL,
                "message": (
                    f"Simulated Omni Flash edit on video #{video_id} "
                    f"('{src_video.get('video_filename')}'): {req.edit_instruction}"
                ),
            }
        try:
            from app.tools.omni_video_tools import edit_video_with_omni

            return edit_video_with_omni(video_id=video_id, edit_instruction=req.edit_instruction)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------------
    # 6. STEP 4: ANALYTICS & IN-STORE RETAIL MEDIA METRICS
    # ------------------------------------------------------------------------

    def get_analytics_overview(self) -> dict[str, Any]:
        """Return cross-campaign retail media KPI overview and metric glossary."""
        top_res = self.get_top_performing(metric="rpi", limit=5)
        campaigns_res = compare_campaigns(campaign_ids=[1, 2, 3, 4])
        return {
            "status": "success",
            "primary_kpi": "rpi",
            "metric_definitions": {
                "rpi": "Revenue Per Impression (revenue / impressions) — primary KPI measuring dollar value generated per ad view.",
                "dwell_time_seconds": "Average duration in seconds that in-store shoppers spend in the screen viewing zone.",
                "circulation": "Total store foot traffic passing through the screen's outer detection zone.",
                "impressions": "Qualified ad views recorded when a visitor enters the inner viewing zone during an active ad play.",
                "revenue": "Attributed in-store POS revenue correlated with active video plays.",
            },
            "top_performing_videos": top_res.get("top_campaign_videos", []),
            "campaign_comparison": campaigns_res,
        }

    def get_top_performing(
        self,
        metric: str = "rpi",
        limit: int = 10,
        campaign_id: int | None = None,
    ) -> dict[str, Any]:
        """Rank top performing videos across both `campaign_videos` and legacy `campaign_ads`."""
        tool_metric_map = {
            "rpi": "revenue_per_impression",
            "revenue_per_impression": "revenue_per_impression",
            "revenue": "revenue_per_impression",
            "impressions": "impressions",
            "dwell_time": "dwell_time",
            "circulation": "circulation",
        }
        tool_metric = tool_metric_map.get(metric.lower(), "revenue_per_impression")
        legacy_res = get_top_performing_ads(metric=tool_metric, limit=limit)

        vids_res = self.list_videos_filtered(campaign_id=campaign_id, status="activated")
        videos = vids_res.get("videos", [])

        sort_key_map = {
            "rpi": lambda v: float(v.get("rpi") or 0.0),
            "revenue_per_impression": lambda v: float(v.get("rpi") or 0.0),
            "revenue": lambda v: float(v.get("total_revenue") or 0.0),
            "impressions": lambda v: int(v.get("total_impressions") or 0),
            "dwell_time": lambda v: float(v.get("avg_dwell_time_seconds") or 0.0),
            "circulation": lambda v: int(v.get("total_circulation") or 0),
        }
        key_fn = sort_key_map.get(metric.lower(), sort_key_map["rpi"])
        ranked_videos = sorted(videos, key=key_fn, reverse=True)[:limit]

        formatted_videos = [
            {
                "rank": idx + 1,
                "video_id": v["id"],
                "campaign_id": v["campaign_id"],
                "campaign_name": v.get("campaign_name"),
                "store_name": v.get("store_name"),
                "city": v.get("city"),
                "state": v.get("state"),
                "product_id": v.get("product_id"),
                "product_name": v.get("product_name"),
                "video_filename": v.get("video_filename"),
                "video_url": v.get("video_url"),
                "gateway_video_url": v.get("gateway_video_url"),
                "variation_name": v.get("variation_name"),
                "variation_params": v.get("variation_params", {}),
                "rpi": v.get("rpi", 0.0),
                "total_revenue": round(float(v.get("total_revenue") or 0.0), 2),
                "total_impressions": int(v.get("total_impressions") or 0),
                "avg_dwell_time_seconds": round(float(v.get("avg_dwell_time_seconds") or 0.0), 2),
                "total_circulation": int(v.get("total_circulation") or 0),
            }
            for idx, v in enumerate(ranked_videos)
        ]

        return {
            "status": "success",
            "ranked_by": metric,
            "limit": limit,
            "top_campaign_videos": formatted_videos,
            "top_ads": legacy_res.get("top_ads", formatted_videos),
        }

    def generate_campaign_chart(self, campaign_id: int) -> dict[str, Any]:
        """Generate deterministic creative comparison chart for a campaign."""
        try:
            res = generate_creative_comparison_chart(campaign_id=campaign_id)
            if res.get("chart_filename"):
                res["gateway_chart_url"] = f"/api/v1/assets/{BUCKET_GENERATED}/{res['chart_filename']}"
            return res
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def generate_campaign_infographic(
        self, campaign_id: int, req: VisualizationRequest
    ) -> dict[str, Any]:
        """Generate campaign metrics visualization (supports dry_run or live Gemini Image)."""
        if req.dry_run:
            metrics = get_campaign_metrics(campaign_id=campaign_id)
            return {
                "status": "success",
                "dry_run": True,
                "campaign_id": campaign_id,
                "chart_type": req.chart_type,
                "metrics_summary": metrics.get("summary", {}),
                "message": f"Prepared metrics visualization payload for campaign #{campaign_id}.",
            }
        try:
            from app.tools.metrics_tools import generate_metrics_visualization

            return generate_metrics_visualization(campaign_id=campaign_id, chart_type=req.chart_type)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------------
    # 7. STEP 5: GEOGRAPHIC INTELLIGENCE & MAPS
    # ------------------------------------------------------------------------

    def get_campaign_map_data(self, campaign_ids: list[int] | None = None) -> dict[str, Any]:
        """Return interactive map markers, coordinates, and RPI performance tiers across store locations."""
        with get_db_cursor() as cursor:
            query = """
                SELECT
                    c.id, c.name, c.status, c.store_name,
                    c.city, c.state, c.category,
                    p.name as product_name,
                    COALESCE(SUM(vm.impressions), 0) as total_impressions,
                    COALESCE(SUM(vm.revenue), 0.0) as total_revenue,
                    COALESCE(AVG(vm.dwell_time_seconds), 0.0) as avg_dwell_time,
                    COALESCE(SUM(vm.circulation), 0) as total_circulation
                FROM campaigns c
                LEFT JOIN products p ON c.product_id = p.id
                LEFT JOIN campaign_videos cv ON c.id = cv.campaign_id AND cv.status = 'activated'
                LEFT JOIN video_metrics vm ON cv.id = vm.video_id
            """
            params: list[Any] = []
            if campaign_ids:
                placeholders = ",".join("?" for _ in campaign_ids)
                query += f" WHERE c.id IN ({placeholders})"
                params.extend(campaign_ids)
            query += " GROUP BY c.id ORDER BY c.id ASC"
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

        markers: list[dict[str, Any]] = []
        for idx, r in enumerate(rows):
            imp = int(r["total_impressions"] or 0)
            rev = float(r["total_revenue"] or 0.0)
            rpi = round(rev / imp, 4) if imp > 0 else 0.0
            tier = "high" if rpi >= 0.05 else ("medium" if rpi >= 0.03 else "low")
            city = str(r.get("city") or "")
            st = (r.get("state") or "").upper()
            base_coords = CITY_COORDINATES.get((city.lower(), st), (39.8283, -98.5795))
            # Add slight deterministic offset when multiple stores are in the same city
            lat = round(base_coords[0] + (idx * 0.008), 6)
            lng = round(base_coords[1] - (idx * 0.008), 6)
            markers.append(
                {
                    "campaign_id": r["id"],
                    "campaign_name": r["name"],
                    "store_name": r["store_name"],
                    "city": city,
                    "state": st,
                    "region": REGION_BY_STATE.get(st, "Other"),
                    "latitude": lat,
                    "longitude": lng,
                    "product_name": r.get("product_name"),
                    "performance_tier": tier,
                    "metrics": {
                        "rpi": rpi,
                        "total_revenue": round(rev, 2),
                        "total_impressions": imp,
                        "avg_dwell_time_seconds": round(float(r["avg_dwell_time"] or 0.0), 2),
                        "total_circulation": int(r["total_circulation"] or 0),
                    },
                    "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
                }
            )
        return {
            "status": "success",
            "total_locations": len(markers),
            "locations": markers,
            "markers": markers,
        }

    def get_campaign_locations_data(self, campaign_id: int | None = None) -> dict[str, Any]:
        """Return store locations for campaigns (tries live Google Maps tool if configured, falls back to SQLite + coordinates)."""
        if os.getenv("GOOGLE_MAPS_API_KEY") and campaign_id is None:
            try:
                from app.tools.maps_tools import get_campaign_locations as _live_locations

                res = _live_locations()
                if res.get("status") == "success":
                    return res
            except Exception:
                pass
        cids = [campaign_id] if campaign_id is not None else None
        return self.get_campaign_map_data(campaign_ids=cids)

    def get_location_demographics_data(self, city: str = "Los Angeles", state: str = "CA") -> dict[str, Any]:
        """Return demographic profile and creative recommendations for a store trade area."""
        if os.getenv("GOOGLE_MAPS_API_KEY"):
            try:
                from app.tools.maps_tools import get_location_demographics as _live_demo

                res = _live_demo(city=city, state=state)
                if res.get("status") == "success":
                    return res
            except Exception:
                pass

        st = state.strip().upper()
        key = (city.strip().lower(), st)
        profile = CITY_DEMOGRAPHICS.get(
            key,
            {
                "population_estimate": "1.2M metro",
                "median_age": 36.5,
                "income_tier": "Middle to Upper-Middle",
                "key_segments": ["Local Shoppers", "Commuters", "Families"],
                "recommended_creative_dna": {
                    "setting": "studio",
                    "time_of_day": "golden_hour",
                    "mood": "confident",
                    "lighting": "natural_soft",
                },
            },
        )
        coords = CITY_COORDINATES.get(key, (39.8283, -98.5795))
        return {
            "status": "success",
            "city": city,
            "state": st,
            "region": REGION_BY_STATE.get(st, "Other"),
            "coordinates": {"lat": coords[0], "lng": coords[1]},
            "demographics": profile,
        }

    def search_nearby_stores_data(
        self, city: str = "Los Angeles", state: str = "CA", store_type: str = "clothing_store"
    ) -> dict[str, Any]:
        """Search retail stores in the specified city/state."""
        if os.getenv("GOOGLE_MAPS_API_KEY"):
            try:
                from app.tools.maps_tools import search_nearby_stores as _live_stores

                res = _live_stores(city=city, state=state, store_type=store_type)
                if res.get("status") == "success":
                    return res
            except Exception:
                pass

        st = state.strip().upper()
        camps = self.list_campaigns_filtered(state=st).get("campaigns", [])
        stores = [
            {
                "store_name": c.get("store_name"),
                "city": c.get("city"),
                "state": c.get("state"),
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "store_type": store_type,
                "latitude": c.get("latitude"),
                "longitude": c.get("longitude"),
            }
            for c in camps
        ]
        return {
            "status": "success",
            "city": city,
            "state": st,
            "store_type": store_type,
            "total_stores": len(stores),
            "stores": stores,
        }

    def get_regional_comparison(self) -> dict[str, Any]:
        """Compare store performance across geographic regions (e.g., West Coast vs. East Coast)."""
        map_data = self.get_campaign_map_data()
        locations = map_data.get("locations", map_data.get("markers", []))

        regions: dict[str, dict[str, Any]] = {}
        for loc in locations:
            st = (loc.get("state") or "").upper()
            region = loc.get("region") or REGION_BY_STATE.get(st, "Other")
            if region not in regions:
                regions[region] = {
                    "region": region,
                    "states": [],
                    "cities": [],
                    "campaign_count": 0,
                    "campaign_ids": [],
                    "stores": [],
                    "total_impressions": 0,
                    "total_revenue": 0.0,
                    "total_circulation": 0,
                    "dwell_time_samples": [],
                }
            bucket = regions[region]
            if st and st not in bucket["states"]:
                bucket["states"].append(st)
            city = loc.get("city")
            if city and city not in bucket["cities"]:
                bucket["cities"].append(city)
            cid = loc.get("campaign_id") or loc.get("id")
            if cid is not None:
                bucket["campaign_count"] += 1
                bucket["campaign_ids"].append(cid)
            if loc.get("store_name"):
                bucket["stores"].append(loc["store_name"])

            metrics = loc.get("metrics", loc)
            imp = int(metrics.get("total_impressions", metrics.get("impressions", 0)) or 0)
            rev = float(metrics.get("total_revenue", metrics.get("revenue", 0.0)) or 0.0)
            circ = int(metrics.get("total_circulation", metrics.get("circulation", 0)) or 0)
            dwell = float(metrics.get("avg_dwell_time_seconds", metrics.get("dwell_time_seconds", 0.0)) or 0.0)

            bucket["total_impressions"] += imp
            bucket["total_revenue"] = round(bucket["total_revenue"] + rev, 2)
            bucket["total_circulation"] += circ
            if dwell > 0:
                bucket["dwell_time_samples"].append(dwell)

        formatted_regions: dict[str, dict[str, Any]] = {}
        for reg_name, b in regions.items():
            imp = b["total_impressions"]
            rev = b["total_revenue"]
            samples = b.pop("dwell_time_samples", [])
            b["rpi"] = round(rev / imp, 4) if imp > 0 else 0.0
            b["avg_dwell_time_seconds"] = round(sum(samples) / len(samples), 2) if samples else 0.0
            formatted_regions[reg_name] = b

        ranked = sorted(formatted_regions.values(), key=lambda r: r["rpi"], reverse=True)
        top_region = ranked[0]["region"] if ranked else None

        west = formatted_regions.get("West Coast", {})
        east = formatted_regions.get("East Coast", {})
        west_vs_east_delta = {
            "rpi_diff": round(float(west.get("rpi", 0.0)) - float(east.get("rpi", 0.0)), 4),
            "revenue_diff": round(float(west.get("total_revenue", 0.0)) - float(east.get("total_revenue", 0.0)), 2),
            "impressions_diff": int(west.get("total_impressions", 0)) - int(east.get("total_impressions", 0)),
            "leader": "West Coast" if float(west.get("rpi", 0.0)) >= float(east.get("rpi", 0.0)) else "East Coast",
        }

        return {
            "status": "success",
            "top_region_by_rpi": top_region,
            "west_coast_vs_east_coast": west_vs_east_delta,
            "regions": formatted_regions,
            "ranked_regions": ranked,
        }

    def generate_static_map_url(self, req: StaticMapRequest) -> dict[str, Any]:
        """Generate a Google Static Maps URL for campaign locations."""
        map_data = self.get_campaign_map_data(campaign_ids=req.campaign_ids)
        locs = map_data.get("locations", [])
        coords = [
            f"{loc['latitude']},{loc['longitude']}"
            for loc in locs
            if loc.get("latitude") is not None and loc.get("longitude") is not None
        ]
        markers_param = "|".join(coords)
        return {
            "status": "success",
            "static_map_url": f"https://maps.googleapis.com/maps/api/staticmap?size={req.width}x{req.height}&markers={markers_param}",
            "locations_count": len(coords),
        }

    def generate_map_infographic(self, req: VisualizationRequest) -> dict[str, Any]:
        """Generate a geographic performance map visualization (supports dry_run or live Gemini Image)."""
        if req.dry_run:
            reg = self.get_regional_comparison()
            return {
                "status": "success",
                "dry_run": True,
                "chart_type": req.chart_type,
                "regional_summary": reg,
                "message": "Prepared geographic map visualization payload.",
            }
        try:
            from app.tools.maps_tools import generate_map_visualization

            return generate_map_visualization()
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------------
    # 8. STEP 6: SCALE WHAT WORKS (WINNING FORMULA EXTRACTION & APPLICATION)
    # ------------------------------------------------------------------------

    def get_winning_formula(
        self,
        video_id: int | None = None,
        campaign_id: int | None = None,
    ) -> dict[str, Any]:
        """Extract the winning creative DNA from a specific video or the highest-RPI video."""
        target_video: dict[str, Any] | None = None

        if video_id is not None:
            vids = self.list_videos_filtered()
            for v in vids.get("videos", []):
                if v["id"] == video_id:
                    target_video = v
                    break
        else:
            top = self.get_top_performing(metric="rpi", limit=1, campaign_id=campaign_id)
            top_vids = top.get("top_campaign_videos", [])
            if top_vids:
                vid_id = top_vids[0]["video_id"]
                vids = self.list_videos_filtered()
                for v in vids.get("videos", []):
                    if v["id"] == vid_id:
                        target_video = v
                        break
            if target_video is None:
                all_vids = self.list_videos_filtered(campaign_id=campaign_id).get("videos", [])
                if all_vids:
                    target_video = all_vids[0]

        if not target_video:
            return {"status": "error", "error": "No matching video found to extract a winning formula."}

        vp = target_video.get("variation_params") or {}
        vprops = target_video.get("video_properties") or {}

        # Fallback inference from filename or variation_name if variation_params is sparse
        var_name = (target_video.get("variation_name") or target_video.get("video_filename") or "").lower()
        inferred_eth = vp.get("model_ethnicity") or vprops.get("model_ethnicity")
        if not inferred_eth:
            for e in ModelEthnicity:
                if e.value in var_name:
                    inferred_eth = e.value
                    break
        inferred_setting = vp.get("setting")
        if not inferred_setting:
            for s in Setting:
                if s.value in var_name:
                    inferred_setting = s.value
                    break
        inferred_mood = vp.get("mood") or vprops.get("mood")
        if not inferred_mood:
            for m in Mood:
                if m.value in var_name:
                    inferred_mood = m.value
                    break

        formula = {
            "source_video_id": target_video["id"],
            "source_campaign_id": target_video.get("campaign_id"),
            "source_campaign_name": target_video.get("campaign_name"),
            "source_product_id": target_video.get("product_id"),
            "source_product_name": target_video.get("product_name"),
            "variation_name": target_video.get("variation_name"),
            "presentation_mode": vp.get("presentation_mode", "model"),
            "model_ethnicity": inferred_eth or "european",
            "setting": inferred_setting or "rooftop",
            "time_of_day": vp.get("time_of_day") or vprops.get("time_of_day") or "sunset",
            "mood": inferred_mood or "sophisticated",
            "lighting": vp.get("lighting") or vprops.get("lighting_style") or "golden_backlight",
            "camera_movement": vp.get("camera_movement") or vprops.get("camera_movement") or "dolly_in",
            "activity": vp.get("activity") or "standing",
            "props": vp.get("props") or vprops.get("notable_props") or [],
            "color_grading": vp.get("color_grading") or vprops.get("color_temperature") or "warm",
            "aspect_ratio": target_video.get("aspect_ratio") or "9:16",
            "duration_seconds": target_video.get("duration_seconds") or 8,
            "rpi": target_video.get("rpi", 0.0),
            "total_revenue": round(float(target_video.get("total_revenue") or 0.0), 2),
            "total_impressions": int(target_video.get("total_impressions") or 0),
            "avg_dwell_time_seconds": round(float(target_video.get("avg_dwell_time_seconds") or 0.0), 2),
        }

        return {
            "status": "success",
            "winning_formula": formula,
            "dna_summary": [
                f"{str(formula['setting']).replace('_', ' ').title()} Setting",
                f"{str(formula['time_of_day']).replace('_', ' ').title()} Time",
                f"{str(formula['mood']).replace('_', ' ').title()} Mood",
                f"{str(formula['model_ethnicity']).replace('_', ' ').title()} Model",
                f"{str(formula['lighting']).replace('_', ' ').title()} Lighting",
                f"{str(formula['camera_movement']).replace('_', ' ').title()} Camera",
            ],
        }

    def apply_winning_formula(self, req: WinningFormulaApplyRequest) -> dict[str, Any]:
        """Extract winning DNA from a source video/campaign and apply it to `target_campaign_id`."""
        target_camp_res = get_campaign(req.target_campaign_id)
        if target_camp_res.get("status") != "success":
            return {"status": "error", "error": f"Target campaign {req.target_campaign_id} not found."}
        target_campaign = target_camp_res["campaign"]

        wf_res = self.get_winning_formula(
            video_id=req.source_video_id,
            campaign_id=req.source_campaign_id,
        )
        if wf_res.get("status") != "success":
            return wf_res
        formula = wf_res["winning_formula"]

        comp_dict = {
            "presentation_mode": formula.get("presentation_mode"),
            "model_ethnicity": formula.get("model_ethnicity", "european"),
            "setting": formula.get("setting", "rooftop"),
            "time_of_day": formula.get("time_of_day", "sunset"),
            "mood": formula.get("mood", "sophisticated"),
            "lighting": formula.get("lighting", "golden_backlight"),
            "camera_movement": formula.get("camera_movement", "dolly_in"),
            "activity": formula.get("activity", "standing"),
            "props": list(formula.get("props") or []),
            "color_grading": formula.get("color_grading", "warm"),
            "aspect_ratio": formula.get("aspect_ratio", "9:16"),
            "duration_seconds": int(formula.get("duration_seconds") or 8),
        }
        if req.override_components:
            comp_dict.update(req.override_components)

        gen_res = self.generate_video(
            VideoGenerateRequest(
                campaign_id=req.target_campaign_id,
                product_id=target_campaign.get("product_id"),
                components=VideoComponentConfig(**comp_dict),
                dry_run=req.dry_run,
            )
        )
        if gen_res.get("status") != "success":
            return gen_res

        return {
            "status": "success",
            "message": (
                f"Applied winning formula from video #{formula['source_video_id']} "
                f"to campaign #{req.target_campaign_id} ('{target_campaign['name']}')."
            ),
            "winning_formula": formula,
            "dna_summary": wf_res["dna_summary"],
            "target_campaign": target_campaign,
            "new_video": gen_res["video"],
        }

    # ------------------------------------------------------------------------
    # 9. DATASETS EXPLORER & MANAGEMENT
    # ------------------------------------------------------------------------

    def list_datasets(self) -> dict[str, Any]:
        """List all available datasets with row counts, schemas, and descriptions."""
        with get_db_cursor() as cursor:
            def _count(table: str) -> int:
                try:
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                    return int(cursor.fetchone()["cnt"])
                except Exception:
                    return 0

            counts = {
                "products": _count("products"),
                "campaigns": _count("campaigns"),
                "videos": _count("campaign_videos"),
                "video_metrics": _count("video_metrics"),
                "video_attribution": _count("video_attribution"),
                "demo_meta": _count("demo_meta"),
                "legacy_ads": _count("campaign_ads"),
            }
            counts["ad_plays"] = counts["video_attribution"] * 6

        datasets = [
            {
                "name": "fashion_catalog",
                "title": "Fashion Catalog Dataset (In-Memory Reference)",
                "category": "catalog",
                "row_count": len(PRODUCTS_DATA),
                "description": "22 curated fashion & apparel products with garment types, styles, materials, and seasons.",
                "columns": ["name", "details", "style", "color", "fabric", "occasion", "category", "image_filename"],
            },
            {
                "name": "retail_core_catalog",
                "title": "Multi-Category Retail Core Dataset (In-Memory Reference)",
                "category": "catalog",
                "row_count": len(RETAIL_PRODUCTS_DATA),
                "description": "6 multi-category retail products across beverage, QSR menu, electronics, automotive, and home improvement.",
                "columns": ["name", "description", "category", "attributes", "image_filename"],
            },
            {
                "name": "products",
                "title": "Active Products Table (SQLite)",
                "category": "database",
                "row_count": counts["products"],
                "description": "All seeded and user-onboarded products in SQLite with image availability status and presentation modes.",
                "columns": ["id", "name", "category", "presentation_mode", "garment_type", "color", "style", "material", "season", "attributes", "image_filename", "image_status"],
            },
            {
                "name": "campaigns",
                "title": "Retail Store Campaigns (SQLite)",
                "category": "database",
                "row_count": counts["campaigns"],
                "description": "In-store retail media campaigns linked to products, store coordinates, and trade areas.",
                "columns": ["id", "name", "product_id", "product_name", "status", "category", "store_name", "city", "state", "region", "latitude", "longitude", "start_date", "end_date"],
            },
            {
                "name": "videos",
                "title": "Generated & Activated Videos (`campaign_videos`)",
                "category": "database",
                "row_count": counts["videos"],
                "description": "All generated, activated, paused, and archived video variations with variation_params, video_properties, and RPI.",
                "columns": ["id", "campaign_id", "product_id", "video_filename", "status", "variation_name", "variation_params", "video_properties", "rpi", "total_impressions", "total_revenue"],
            },
            {
                "name": "video_metrics",
                "title": "Daily Video Performance Metrics (`video_metrics`)",
                "category": "analytics",
                "row_count": counts["video_metrics"],
                "description": "Daily time-series metrics per activated video: impressions, dwell_time_seconds, circulation, revenue, and RPI.",
                "columns": ["id", "video_id", "metric_date", "impressions", "dwell_time_seconds", "circulation", "revenue", "rpi"],
            },
            {
                "name": "video_attribution",
                "title": "Screen Attribution Schedule (`video_attribution`)",
                "category": "analytics",
                "row_count": counts["video_attribution"],
                "description": "Maps video IDs to in-store screen IDs and active time windows for BlueZoo audience attribution.",
                "columns": ["video_id", "ad_campaign_id", "screen_id", "active_from", "active_to"],
            },
            {
                "name": "ad_plays",
                "title": "Screen Ad Play Log (`ad_plays`)",
                "category": "analytics",
                "row_count": counts["ad_plays"],
                "description": "Timestamped ad play events on in-store digital signage screens.",
                "columns": ["play_id", "video_id", "ad_campaign_id", "screen_id", "played_at", "duration_seconds"],
            },
            {
                "name": "audience_visits",
                "title": "BlueZoo Audience Sensor Visits (`AudienceDataSource`)",
                "category": "audience",
                "row_count": 384,
                "description": "15-minute slot sensor visit counts (inner viewing zone vs. outer circulation zone) and average dwell seconds.",
                "columns": ["screen_id", "slot_start", "slot_end", "inner_count", "outer_count", "avg_dwell_seconds", "valid"],
            },
            {
                "name": "demo_meta",
                "title": "Demo Environment Metadata (`demo_meta`)",
                "category": "system",
                "row_count": counts["demo_meta"],
                "description": "Key-value metadata tracking active demo_dataset mode and schema state.",
                "columns": ["key", "value"],
            },
            {
                "name": "legacy_ads",
                "title": "Legacy Campaign Ads (`campaign_ads`)",
                "category": "legacy",
                "row_count": counts["legacy_ads"],
                "description": "Legacy ad records and aggregated metrics.",
                "columns": ["id", "campaign_id", "video_filename", "model_ethnicity", "setting", "mood", "status"],
            },
            {
                "name": "assets",
                "title": "Media Assets Inventory (`product-images`, `selected`, `generated`)",
                "category": "storage",
                "row_count": len(self._scan_local_assets()),
                "description": "Local and GCS media files (product reference images, selected seed images, and generated MP4 videos/charts).",
                "columns": ["bucket", "filename", "size_bytes", "gateway_url", "public_url"],
            },
        ]

        return {
            "status": "success",
            "active_demo_dataset": str(DEMO_DATASET.value if hasattr(DEMO_DATASET, "value") else DEMO_DATASET),
            "app_mode": APP_MODE,
            "total_datasets": len(datasets),
            "datasets": datasets,
        }

    def get_dataset(
        self,
        dataset_name: str,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
        campaign_id: int | None = None,
        product_id: int | None = None,
        video_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        screen_id: int | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Return records from any named dataset with filtering, search, and pagination."""
        name = dataset_name.strip().lower().replace("-", "_")
        records: list[dict[str, Any]] = []

        if name == "fashion_catalog":
            for idx, item in enumerate(PRODUCTS_DATA, start=1):
                row = {"catalog_index": idx, **item}
                if row.get("image_filename"):
                    row["image_url"] = to_public_url(BUCKET_PRODUCT_IMAGES, row["image_filename"])
                    row["gateway_asset_url"] = f"/api/v1/assets/{BUCKET_PRODUCT_IMAGES}/{row['image_filename']}"
                records.append(row)

        elif name == "retail_core_catalog":
            for idx, item in enumerate(RETAIL_PRODUCTS_DATA, start=1):
                row = {"catalog_index": idx, **item}
                if row.get("image_filename"):
                    row["image_url"] = to_public_url(BUCKET_PRODUCT_IMAGES, row["image_filename"])
                    row["gateway_asset_url"] = f"/api/v1/assets/{BUCKET_PRODUCT_IMAGES}/{row['image_filename']}"
                records.append(row)

        elif name == "products":
            res = self.list_products_filtered(category=category, search=q)
            records = res.get("products", [])
            if product_id is not None:
                records = [r for r in records if r["id"] == product_id]

        elif name == "campaigns":
            res = self.list_campaigns_filtered(
                status=status,
                category=category,
                state=state,
                product_id=product_id,
            )
            records = res.get("campaigns", [])
            if campaign_id is not None:
                records = [r for r in records if r["id"] == campaign_id]

        elif name in ("videos", "campaign_videos"):
            res = self.list_videos_filtered(
                campaign_id=campaign_id,
                status=status,
                product_id=product_id,
            )
            records = res.get("videos", [])
            if video_id is not None:
                records = [r for r in records if r["id"] == video_id]

        elif name == "video_metrics":
            query = """
                SELECT vm.*, cv.campaign_id, cv.video_filename, cv.variation_name
                FROM video_metrics vm
                LEFT JOIN campaign_videos cv ON vm.video_id = cv.id
                WHERE 1=1
            """
            params: list[Any] = []
            if video_id is not None:
                query += " AND vm.video_id = ?"
                params.append(video_id)
            if campaign_id is not None:
                query += " AND cv.campaign_id = ?"
                params.append(campaign_id)
            query += " ORDER BY vm.metric_date DESC, vm.id DESC"
            with get_db_cursor() as cursor:
                cursor.execute(query, params)
                for r in cursor.fetchall():
                    d = dict(r)
                    imp = int(d.get("impressions") or 0)
                    rev = float(d.get("revenue") or 0.0)
                    d["rpi"] = round(rev / imp, 4) if imp > 0 else 0.0
                    records.append(d)

        elif name == "video_attribution":
            query = "SELECT * FROM video_attribution WHERE 1=1"
            params = []
            if campaign_id is not None:
                query += " AND ad_campaign_id = ?"
                params.append(campaign_id)
            if screen_id is not None:
                query += " AND screen_id = ?"
                params.append(screen_id)
            with get_db_cursor() as cursor:
                cursor.execute(query, params)
                records = [dict(r) for r in cursor.fetchall()]

        elif name == "ad_plays":
            attr_rows = self.get_dataset(
                "video_attribution",
                limit=500,
                campaign_id=campaign_id,
                screen_id=screen_id,
            ).get("records", [])
            play_id = 1
            for attr in attr_rows:
                vid = attr.get("video_id")
                cid = attr.get("ad_campaign_id")
                sid = attr.get("screen_id", 101)
                base_str = str(attr.get("active_from") or "2026-04-01T09:00:00")[:19]
                try:
                    base_dt = datetime.fromisoformat(base_str)
                except ValueError:
                    base_dt = datetime(2026, 4, 1, 9, 0, 0)
                for slot_idx in range(6):
                    played_dt = base_dt + timedelta(minutes=15 * slot_idx)
                    records.append(
                        {
                            "play_id": play_id,
                            "video_id": vid,
                            "ad_campaign_id": cid,
                            "screen_id": sid,
                            "played_at": played_dt.isoformat(),
                            "duration_seconds": 15,
                        }
                    )
                    play_id += 1

        elif name == "audience_visits":
            from app.audience import get_audience_datasource

            src = get_audience_datasource()
            screens = [screen_id] if screen_id is not None else [101, 102]
            end_d = date.today()
            start_d = end_d - timedelta(days=max(1, min(days, 30)))
            visits = src.get_visit_intervals(screen_ids=screens, date_from=start_d, date_to=end_d)
            records = [
                {
                    "screen_id": v.screen_id,
                    "timestamp": v.timestamp.isoformat(),
                    "ad_campaign_id": v.ad_campaign_id,
                    "incoming_inner_count": v.incoming_inner_count,
                    "outgoing_inner_count": v.outgoing_inner_count,
                    "incoming_outer_count": v.incoming_outer_count,
                    "outgoing_outer_count": v.outgoing_outer_count,
                    "average_visitors_inner": v.average_visitors_inner,
                    "valid": v.valid,
                }
                for v in visits
            ]

        elif name == "demo_meta":
            with get_db_cursor() as cursor:
                cursor.execute("SELECT * FROM demo_meta")
                records = [dict(r) for r in cursor.fetchall()]

        elif name in ("legacy_ads", "campaign_ads"):
            with get_db_cursor() as cursor:
                cursor.execute("SELECT * FROM campaign_ads ORDER BY id DESC")
                records = [dict(r) for r in cursor.fetchall()]

        elif name == "assets":
            records = self._scan_local_assets()

        else:
            return {
                "status": "error",
                "error": (
                    f"Unknown dataset '{dataset_name}'. Valid datasets: "
                    "fashion_catalog, retail_core_catalog, products, campaigns, videos, "
                    "video_metrics, video_attribution, ad_plays, audience_visits, "
                    "demo_meta, legacy_ads, assets."
                ),
            }

        if q and name not in ("products",):
            q_low = q.lower()
            records = [
                r for r in records if q_low in json.dumps(r, default=str).lower()
            ]

        total_count = len(records)
        sliced = records[offset : offset + limit]
        columns = list(sliced[0].keys()) if sliced else (list(records[0].keys()) if records else [])

        return {
            "status": "success",
            "dataset": name,
            "total_count": total_count,
            "returned_count": len(sliced),
            "offset": offset,
            "limit": limit,
            "columns": columns,
            "records": sliced,
        }

    def seed_or_reset_dataset(self, req: DatasetSeedRequest, reset: bool = False) -> dict[str, Any]:
        """Seed or reset the SQLite database using the specified `dataset_mode` ('fashion' or 'none')."""
        mode = req.dataset_mode.strip().lower()
        if mode not in ("fashion", "none"):
            return {
                "status": "error",
                "error": f"Invalid dataset_mode '{req.dataset_mode}'. Must be 'fashion' or 'none'.",
            }

        if reset or req.force_reseed:
            reset_database()
        else:
            init_database()

        import app.config as cfg_mod
        import app.database.mock_data as mock_mod

        prev_cfg = cfg_mod.DEMO_DATASET
        try:
            cfg_mod.DEMO_DATASET = DemoDataset(mode)
            mock_mod.seed_demo_data()
        finally:
            cfg_mod.DEMO_DATASET = prev_cfg

        health = self.get_health()
        return {
            "status": "success",
            "action": "reset" if reset else "seed",
            "dataset_mode": mode,
            "counts": health["counts"],
        }

    def _scan_local_assets(self) -> list[dict[str, Any]]:
        """Scan local asset directories (`product-images`, `selected`, `generated`)."""
        items: list[dict[str, Any]] = []
        for bucket in (BUCKET_PRODUCT_IMAGES, BUCKET_SELECTED, BUCKET_GENERATED):
            folder = Path(LOCAL_ASSETS_DIR) / bucket
            if not folder.exists() or not folder.is_dir():
                continue
            for p in sorted(folder.iterdir()):
                if p.is_file() and not p.name.startswith("."):
                    items.append(
                        {
                            "bucket": bucket,
                            "filename": p.name,
                            "size_bytes": p.stat().st_size,
                            "gateway_url": f"/api/v1/assets/{bucket}/{p.name}",
                            "public_url": to_public_url(bucket, p.name),
                        }
                    )
        return items

    def resolve_static_asset(self, bucket_dir: str, filename: str) -> tuple[Path | None, str]:
        """Safely resolve a local asset file path and MIME type."""
        allowed_buckets = {BUCKET_PRODUCT_IMAGES, BUCKET_SELECTED, BUCKET_GENERATED, "assets"}
        if bucket_dir not in allowed_buckets or ".." in filename or "/" in filename or "\\" in filename:
            return None, "application/octet-stream"
        path = resolve_asset_path(bucket_dir, filename)
        if not path.exists() or not path.is_file():
            return None, "application/octet-stream"
        mime, _ = mimetypes.guess_type(str(path))
        return path, mime or "application/octet-stream"

    # ------------------------------------------------------------------------
    # 9. UX DESIGNER OBJECT MODEL METHODS (object.js COMPLIANCE)
    # ------------------------------------------------------------------------

    def get_ux_enums(self) -> dict[str, Any]:
        """Return Status and ApprovalStatus enums as defined in object.js."""
        return {
            "Status": {
                "NONE": int(UXStatus.NONE),
                "GENERATING_ACTIVE": int(UXStatus.GENERATING_ACTIVE),
                "GENERATING_COMPLETE": int(UXStatus.GENERATING_COMPLETE),
                "GENERATING_FAILED": int(UXStatus.GENERATING_FAILED),
                "REVIEW_NEEDED": int(UXStatus.REVIEW_NEEDED),
                "APPROVAL_UPDATED": int(UXStatus.APPROVAL_UPDATED),
                "TESTING_ACTIVE": int(UXStatus.TESTING_ACTIVE),
                "TESTING_COMPLETE": int(UXStatus.TESTING_COMPLETE),
                "TESTING_FAILED": int(UXStatus.TESTING_FAILED),
            },
            "ApprovalStatus": {
                "NONE": int(UXApprovalStatus.NONE),
                "APPROVED": int(UXApprovalStatus.APPROVED),
                "REJECTED": int(UXApprovalStatus.REJECTED),
            },
        }

    def get_ux_schema(self) -> dict[str, Any]:
        """Return JSON schemas and example objects matching object.js."""
        return {
            "enums": self.get_ux_enums(),
            "campaign_schema": UXCampaign.model_json_schema(),
            "video_schema": UXVideo.model_json_schema(),
        }

    def list_ux_campaigns(
        self,
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        product_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List campaigns formatted as UX Designer Campaign objects."""
        base_res = self.list_campaigns_filtered(
            status=status, category=category, state=state, product_id=product_id
        )
        campaigns = base_res.get("campaigns", [])
        return [to_ux_campaign(c) for c in campaigns]

    def get_ux_campaign(self, campaign_id: int | str) -> dict[str, Any]:
        """Get a single campaign formatted as a UX Designer Campaign object."""
        try:
            cid = int(campaign_id)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid campaign_id: {campaign_id}"}

        res = self.get_campaign_by_id(cid)
        if res.get("status") == "error":
            return res
        camp = res.get("campaign", {})
        videos = res.get("campaign_videos", [])
        return to_ux_campaign(camp, videos=videos)

    def create_ux_campaign(self, req: dict[str, Any]) -> dict[str, Any]:
        """Create a new campaign from UX Designer payload and return UXCampaign."""
        name = req.get("name") or "New Campaign"
        desc = req.get("description") or ""
        settings = req.get("settings") or {}
        if not desc and settings.get("overall", {}).get("prompt"):
            desc = settings["overall"]["prompt"]
        prod_id = req.get("product_id") or 1
        store = req.get("store_name") or "Retail Store"
        city = req.get("city") or "Los Angeles"
        state = req.get("state") or "CA"
        category = req.get("category") or "always-on"

        created = self.create_new_campaign(
            CampaignCreateRequest(
                product_id=int(prod_id),
                store_name=str(store),
                city=str(city),
                state=str(state),
                name=str(name),
                target_audience=str(desc),
                category=str(category),
            )
        )
        if created.get("status") != "success":
            return created
        new_id = created.get("campaign_id") or created.get("campaign", {}).get("id")
        return self.get_ux_campaign(new_id)

    def update_ux_campaign(self, campaign_id: int | str, req: dict[str, Any]) -> dict[str, Any]:
        """Update campaign using UX Designer payload and return updated UXCampaign."""
        try:
            cid = int(campaign_id)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid campaign_id: {campaign_id}"}

        name = req.get("name")
        desc = req.get("description")
        st_val = req.get("status")
        status_str = None
        if isinstance(st_val, int):
            if st_val == UXStatus.NONE:
                status_str = "archived"
            elif st_val == UXStatus.APPROVAL_UPDATED:
                status_str = "paused"
            elif st_val in (UXStatus.TESTING_ACTIVE, UXStatus.TESTING_COMPLETE):
                status_str = "active"
        elif isinstance(st_val, str):
            status_str = st_val

        self.update_campaign_by_id(
            cid,
            CampaignUpdateRequest(name=name, target_audience=desc, status=status_str),
        )
        return self.get_ux_campaign(cid)

    def list_ux_videos(
        self,
        campaign_id: int | None = None,
        status: str | None = None,
        approval_status: int | None = None,
    ) -> list[dict[str, Any]]:
        """List videos formatted as UX Designer Video objects."""
        base_res = self.list_videos_filtered(campaign_id=campaign_id, status=status)
        vids = base_res.get("videos", [])
        ux_vids = [to_ux_video(v, rank=idx) for idx, v in enumerate(vids, 1)]
        if approval_status is not None:
            ux_vids = [v for v in ux_vids if v.get("approval_status") == int(approval_status)]
        return ux_vids

    def get_ux_video(self, video_id: int | str) -> dict[str, Any]:
        """Get a single video formatted as a UX Designer Video object."""
        try:
            vid = int(video_id)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid video_id: {video_id}"}

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT cv.*,
                       c.name as campaign_name, c.store_name, c.city, c.state,
                       COALESCE(SUM(vm.impressions), 0) as total_impressions,
                       COALESCE(SUM(vm.revenue), 0.0) as total_revenue
                FROM campaign_videos cv
                LEFT JOIN campaigns c ON cv.campaign_id = c.id
                LEFT JOIN video_metrics vm ON cv.id = vm.video_id
                WHERE cv.id = ?
                GROUP BY cv.id
                """,
                (vid,),
            )
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": f"Video #{vid} not found"}
            return to_ux_video(dict(row))

    def update_ux_video(self, video_id: int | str, req: dict[str, Any]) -> dict[str, Any]:
        """Update video fields from UX Designer payload."""
        try:
            vid = int(video_id)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid video_id: {video_id}"}

        app_st = req.get("approval_status")
        if app_st is not None:
            return self.set_ux_video_approval(vid, int(app_st))

        st_val = req.get("status")
        if st_val is not None:
            if int(st_val) == UXStatus.TESTING_ACTIVE:
                activate_video(video_id=vid)
            elif int(st_val) == UXStatus.APPROVAL_UPDATED:
                pause_video(video_id=vid)
            elif int(st_val) == UXStatus.NONE:
                archive_video(video_id=vid)

        return self.get_ux_video(vid)

    def set_ux_video_approval(self, video_id: int | str, approval_status: int) -> dict[str, Any]:
        """Update video approval status (1=APPROVED, 2=REJECTED, 0=NONE)."""
        try:
            vid = int(video_id)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid video_id: {video_id}"}

        if approval_status == UXApprovalStatus.APPROVED:
            activate_video(video_id=vid)
        elif approval_status == UXApprovalStatus.REJECTED:
            archive_video(video_id=vid)
        else:
            pause_video(video_id=vid)
        return self.get_ux_video(vid)

    # ------------------------------------------------------------------------
    # UNIFIED HTTP REQUEST DISPATCHER (WORKS WITH OR WITHOUT FASTAPI)
    # ------------------------------------------------------------------------

    def dispatch(
        self,
        method: str,
        path: str,
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Dispatch an HTTP-style request to the corresponding service handler."""
        m = method.upper()
        clean_path = path.rstrip("/") or "/"
        q = query_params or {}
        b = body or {}

        def _int_param(val: Any, default: int | None = None) -> int | None:
            if val is None or val == "":
                return default
            if isinstance(val, list):
                val = val[0]
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        def _str_param(val: Any, default: str | None = None) -> str | None:
            if val is None:
                return default
            if isinstance(val, list):
                return str(val[0]) if val else default
            return str(val)

        try:
            # --- Root / Health / Overview / Use-Cases ---
            if m == "GET" and clean_path in ("/", "/api/v1/health"):
                return 200, self.get_health()
            if m == "GET" and clean_path == "/api/v1/overview":
                return 200, self.get_overview()
            if m == "GET" and clean_path in ("/api/v1/use-cases", "/api/v1/workflow/steps"):
                return 200, self.get_use_cases()

            # --- Step 1: Discover & Agents ---
            if m == "GET" and clean_path == "/api/v1/discover":
                return 200, self.get_discover()
            if m == "GET" and clean_path == "/api/v1/agents":
                return 200, self.list_agents()
            if m == "POST" and clean_path == "/api/v1/agents/chat":
                return 200, self.chat_with_agent(AgentChatRequest(**b))

            agent_chat_match = re.match(r"^/api/v1/agents/([^/]+)/chat$", clean_path)
            if m == "POST" and agent_chat_match:
                b_copy = dict(b)
                b_copy["agent_name"] = agent_chat_match.group(1)
                return 200, self.chat_with_agent(AgentChatRequest(**b_copy))

            agent_info_match = re.match(r"^/api/v1/agents/([^/]+)$", clean_path)
            if m == "GET" and agent_info_match:
                res = self.get_agent_info(agent_info_match.group(1))
                return (200 if res["status"] == "success" else 404), res

            # --- UX Designer Object Model (/api/v1/ux/*) ---
            if m == "GET" and clean_path == "/api/v1/ux/enums":
                return 200, self.get_ux_enums()
            if m == "GET" and clean_path == "/api/v1/ux/schema":
                return 200, self.get_ux_schema()
            if m == "GET" and clean_path == "/api/v1/ux/campaigns":
                camps = self.list_ux_campaigns(
                    status=_str_param(q.get("status")),
                    category=_str_param(q.get("category")),
                    state=_str_param(q.get("state")),
                    product_id=_int_param(q.get("product_id")),
                )
                return 200, {"status": "success", "total_count": len(camps), "campaigns": camps}
            if m == "POST" and clean_path == "/api/v1/ux/campaigns":
                res = self.create_ux_campaign(b)
                return (201 if res.get("id") else 400), res

            ux_camp_match = re.match(r"^/api/v1/ux/campaigns/(\d+)$", clean_path)
            if ux_camp_match:
                cid = int(ux_camp_match.group(1))
                if m == "GET":
                    res = self.get_ux_campaign(cid)
                    return (200 if res.get("id") else 404), res
                if m in ("PUT", "PATCH"):
                    res = self.update_ux_campaign(cid, b)
                    return (200 if res.get("id") else 400), res

            if m == "GET" and clean_path == "/api/v1/ux/videos":
                vids = self.list_ux_videos(
                    campaign_id=_int_param(q.get("campaign_id")),
                    status=_str_param(q.get("status")),
                    approval_status=_int_param(q.get("approval_status")),
                )
                return 200, {"status": "success", "total_count": len(vids), "videos": vids}

            ux_vid_app_match = re.match(r"^/api/v1/ux/videos/(\d+)/approval$", clean_path)
            if m == "POST" and ux_vid_app_match:
                vid = int(ux_vid_app_match.group(1))
                app_st = _int_param(b.get("approval_status"), UXApprovalStatus.APPROVED) or UXApprovalStatus.APPROVED
                res = self.set_ux_video_approval(vid, app_st)
                return (200 if res.get("id") else 400), res

            ux_vid_match = re.match(r"^/api/v1/ux/videos/(\d+)$", clean_path)
            if ux_vid_match:
                vid = int(ux_vid_match.group(1))
                if m == "GET":
                    res = self.get_ux_video(vid)
                    return (200 if res.get("id") else 404), res
                if m in ("PATCH", "PUT"):
                    res = self.update_ux_video(vid, b)
                    return (200 if res.get("id") else 400), res

            # --- Campaigns ---
            if m == "GET" and clean_path == "/api/v1/campaigns":
                if _str_param(q.get("format")) == "ux":
                    camps = self.list_ux_campaigns(
                        status=_str_param(q.get("status")),
                        category=_str_param(q.get("category")),
                        state=_str_param(q.get("state")),
                        product_id=_int_param(q.get("product_id")),
                    )
                    return 200, {"status": "success", "total_count": len(camps), "campaigns": camps}
                return 200, self.list_campaigns_filtered(
                    status=_str_param(q.get("status")),
                    category=_str_param(q.get("category")),
                    state=_str_param(q.get("state")),
                    product_id=_int_param(q.get("product_id")),
                )
            if m == "POST" and clean_path == "/api/v1/campaigns":
                res = self.create_new_campaign(CampaignCreateRequest(**b))
                return (201 if res.get("status") == "success" else 400), res

            camp_seed_match = re.match(r"^/api/v1/campaigns/(\d+)/seed-images$", clean_path)
            if m == "GET" and camp_seed_match:
                return 200, self.list_seed_images(campaign_id=int(camp_seed_match.group(1)))

            camp_id_match = re.match(r"^/api/v1/campaigns/(\d+)$", clean_path)
            if camp_id_match:
                cid = int(camp_id_match.group(1))
                if m == "GET":
                    if _str_param(q.get("format")) == "ux":
                        res = self.get_ux_campaign(cid)
                        return (200 if res.get("id") else 404), res
                    res = self.get_campaign_by_id(cid)
                    return (200 if res.get("status") == "success" else 404), res
                if m in ("PATCH", "PUT"):
                    res = self.update_campaign_by_id(cid, CampaignUpdateRequest(**b))
                    return (200 if res.get("status") == "success" else 400), res

            # --- Products ---
            if m == "GET" and clean_path == "/api/v1/products":
                return 200, self.list_products_filtered(
                    category=_str_param(q.get("category")),
                    garment_type=_str_param(q.get("garment_type")),
                    style=_str_param(q.get("style")),
                    season=_str_param(q.get("season")),
                    search=_str_param(q.get("search") or q.get("q")),
                    catalog_source=_str_param(q.get("catalog_source"), "all") or "all",
                )
            if m == "POST" and clean_path == "/api/v1/products":
                res = self.create_new_product(ProductCreateRequest(**b))
                return (201 if res.get("status") == "success" else 400), res
            if m == "GET" and clean_path == "/api/v1/products/categories":
                return 200, self.get_product_categories()
            if m == "POST" and clean_path == "/api/v1/products/import-folder":
                return 200, self.import_products_folder(ProductImportFolderRequest(**b))

            prod_gen_img_match = re.match(r"^/api/v1/products/(\d+)/generate-image$", clean_path)
            if m == "POST" and prod_gen_img_match:
                return 200, self.generate_product_reference_image(
                    int(prod_gen_img_match.group(1)), ProductGenerateImageRequest(**b)
                )

            prod_up_img_match = re.match(r"^/api/v1/products/(\d+)/upload-image$", clean_path)
            if m == "POST" and prod_up_img_match:
                return 200, self.upload_product_reference_image(
                    int(prod_up_img_match.group(1)), ProductUploadImageRequest(**b)
                )

            prod_id_match = re.match(r"^/api/v1/products/(\d+)$", clean_path)
            if m == "GET" and prod_id_match:
                res = self.get_product_by_id(int(prod_id_match.group(1)))
                return (200 if res["status"] == "success" else 404), res

            # --- Step 2: Configurable Video Generation & Media ---
            if m == "GET" and clean_path in ("/api/v1/videos/options", "/api/v1/videos/components/schema"):
                return 200, self.get_video_component_options()
            if m == "GET" and clean_path == "/api/v1/videos/presets":
                return 200, self.get_video_presets()
            if m == "POST" and clean_path == "/api/v1/videos/prompts/preview":
                return 200, self.preview_video_prompts(PromptPreviewRequest(**b))
            if m == "POST" and clean_path in ("/api/v1/videos/generate", "/api/v1/videos/generate-with-properties"):
                res = self.generate_video(VideoGenerateRequest(**b))
                return (200 if res.get("status") == "success" else 400), res
            if m == "POST" and clean_path == "/api/v1/videos/generate/batch":
                res = self.generate_video_batch(BatchVideoGenerateRequest(**b))
                return (200 if res.get("status") == "success" else 400), res
            if m == "POST" and clean_path == "/api/v1/videos/analyze":
                vid_id = _int_param(b.get("video_id"), 1) or 1
                res = self.get_video_properties_by_id(vid_id)
                return (200 if res.get("status") != "error" else 404), res
            if m == "GET" and clean_path == "/api/v1/media/seed-images":
                return 200, self.list_seed_images(campaign_id=_int_param(q.get("campaign_id")))

            # --- Step 3: HITL Review & Video Lifecycle ---
            if m == "GET" and clean_path == "/api/v1/videos":
                if _str_param(q.get("format")) == "ux":
                    vids = self.list_ux_videos(
                        campaign_id=_int_param(q.get("campaign_id")),
                        status=_str_param(q.get("status")),
                        approval_status=_int_param(q.get("approval_status")),
                    )
                    return 200, {"status": "success", "total_count": len(vids), "videos": vids}
                return 200, self.list_videos_filtered(
                    campaign_id=_int_param(q.get("campaign_id")),
                    status=_str_param(q.get("status")),
                    product_id=_int_param(q.get("product_id")),
                    model_ethnicity=_str_param(q.get("model_ethnicity")),
                    setting=_str_param(q.get("setting")),
                    mood=_str_param(q.get("mood")),
                )
            if m == "GET" and clean_path == "/api/v1/review/table":
                return 200, get_video_review_table(
                    campaign_id=_int_param(q.get("campaign_id")),
                    status=_str_param(q.get("status")),
                )
            if m == "GET" and clean_path == "/api/v1/review/pending":
                res = list_pending_videos(campaign_id=_int_param(q.get("campaign_id")))
                res["pending_videos"] = res.get("videos", [])
                return 200, res
            if m == "GET" and clean_path == "/api/v1/review/summary":
                return 200, get_activation_summary(campaign_id=_int_param(q.get("campaign_id")))
            if m == "POST" and clean_path == "/api/v1/videos/activate-batch":
                req_batch = VideoBatchActivateRequest(**b)
                res = activate_batch(video_ids=req_batch.video_ids)
                res["activated_count"] = res.get("success_count", 0)
                return 200, res

            vid_prop_match = re.match(r"^/api/v1/videos/(\d+)/properties$", clean_path)
            if m == "GET" and vid_prop_match:
                res = self.get_video_properties_by_id(int(vid_prop_match.group(1)))
                return (200 if res.get("status") != "error" else 404), res

            vid_status_match = re.match(r"^/api/v1/videos/(\d+)/status$", clean_path)
            if m == "GET" and vid_status_match:
                res = get_video_status(video_id=int(vid_status_match.group(1)))
                if "video" in res and "video_status" in res["video"]:
                    res["video_status"] = res["video"]["video_status"]
                return 200, res

            vid_act_match = re.match(r"^/api/v1/videos/(\d+)/activate$", clean_path)
            if m == "POST" and vid_act_match:
                res = activate_video(video_id=int(vid_act_match.group(1)))
                res["video_status"] = "activated"
                return 200, res

            vid_pause_match = re.match(r"^/api/v1/videos/(\d+)/pause$", clean_path)
            if m == "POST" and vid_pause_match:
                res = pause_video(video_id=int(vid_pause_match.group(1)))
                res["new_status"] = res.get("video", {}).get("new_status", "paused")
                return 200, res

            vid_arch_match = re.match(r"^/api/v1/videos/(\d+)/archive$", clean_path)
            if m == "POST" and vid_arch_match:
                res = archive_video(video_id=int(vid_arch_match.group(1)))
                res["new_status"] = res.get("video", {}).get("new_status", "archived")
                return 200, res

            vid_ext_match = re.match(r"^/api/v1/videos/(\d+)/extend-metrics$", clean_path)
            if m == "POST" and vid_ext_match:
                req_ext = VideoExtendMetricsRequest(**b)
                return 200, generate_additional_metrics(
                    video_id=int(vid_ext_match.group(1)),
                    days=req_ext.additional_days,
                )

            vid_edit_match = re.match(r"^/api/v1/videos/(\d+)/edit$", clean_path)
            if m == "POST" and vid_edit_match:
                return 200, self.edit_video_omni(
                    int(vid_edit_match.group(1)), VideoOmniEditRequest(**b)
                )

            vid_id_match = re.match(r"^/api/v1/videos/(\d+)$", clean_path)
            if m == "GET" and vid_id_match:
                vid = int(vid_id_match.group(1))
                if _str_param(q.get("format")) == "ux":
                    res = self.get_ux_video(vid)
                    return (200 if res.get("id") else 404), res
                res = get_video_details(video_id=vid)
                return (200 if res.get("status") != "error" else 404), res

            # --- Step 4: Analytics & Metrics ---
            if m == "GET" and clean_path == "/api/v1/analytics/overview":
                return 200, self.get_analytics_overview()
            if m == "GET" and clean_path == "/api/v1/analytics/top-ads":
                return 200, self.get_top_performing(
                    metric=_str_param(q.get("metric"), "rpi") or "rpi",
                    limit=_int_param(q.get("limit"), 10) or 10,
                    campaign_id=_int_param(q.get("campaign_id")),
                )
            if clean_path == "/api/v1/analytics/campaigns/compare":
                if m == "POST":
                    req_cmp = CampaignCompareRequest(**b)
                    return 200, compare_campaigns(campaign_ids=req_cmp.campaign_ids)
                if m == "GET":
                    raw_ids = _str_param(q.get("campaign_ids"), "1,2,3,4") or "1,2,3,4"
                    cids = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
                    return 200, compare_campaigns(campaign_ids=cids or [1, 2, 3, 4])

            ana_metrics_match = re.match(r"^/api/v1/analytics/campaigns/(\d+)/metrics$", clean_path)
            if m == "GET" and ana_metrics_match:
                days_val = _int_param(q.get("days"))
                kwargs = {"days": days_val} if days_val is not None else {}
                return 200, get_campaign_metrics(campaign_id=int(ana_metrics_match.group(1)), **kwargs)

            ana_ins_match = re.match(r"^/api/v1/analytics/campaigns/(\d+)/insights$", clean_path)
            if m == "GET" and ana_ins_match:
                return 200, get_campaign_insights(campaign_id=int(ana_ins_match.group(1)))

            ana_cre_match = re.match(r"^/api/v1/analytics/campaigns/(\d+)/creatives$", clean_path)
            if m == "GET" and ana_cre_match:
                return 200, compare_creatives_within_campaign(campaign_id=int(ana_cre_match.group(1)))

            ana_chart_match = re.match(r"^/api/v1/analytics/campaigns/(\d+)/creatives/chart$", clean_path)
            if m == "POST" and ana_chart_match:
                return 200, self.generate_campaign_chart(int(ana_chart_match.group(1)))

            ana_vis_match = re.match(r"^/api/v1/analytics/campaigns/(\d+)/visualizations$", clean_path)
            if m == "POST" and ana_vis_match:
                return 200, self.generate_campaign_infographic(
                    int(ana_vis_match.group(1)), VisualizationRequest(**b)
                )

            # --- Step 5: Geographic Intelligence & Maps ---
            if m == "GET" and clean_path == "/api/v1/maps/campaigns":
                raw_ids = _str_param(q.get("campaign_ids"))
                cids = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()] if raw_ids else None
                return 200, self.get_campaign_map_data(campaign_ids=cids)
            if m == "GET" and clean_path == "/api/v1/maps/locations":
                return 200, self.get_campaign_locations_data(campaign_id=_int_param(q.get("campaign_id")))
            if m == "GET" and clean_path == "/api/v1/maps/regions":
                return 200, self.get_regional_comparison()
            if m == "POST" and clean_path == "/api/v1/maps/static":
                return 200, self.generate_static_map_url(StaticMapRequest(**b))
            if m == "POST" and clean_path == "/api/v1/maps/visualizations":
                return 200, self.generate_map_infographic(VisualizationRequest(**b))
            if m == "GET" and clean_path == "/api/v1/maps/demographics":
                city = _str_param(q.get("city"), "Los Angeles") or "Los Angeles"
                state = _str_param(q.get("state"), "CA") or "CA"
                return 200, self.get_location_demographics_data(city=city, state=state)
            if m == "GET" and clean_path == "/api/v1/maps/nearby-stores":
                city = _str_param(q.get("city"), "Los Angeles") or "Los Angeles"
                state = _str_param(q.get("state"), "CA") or "CA"
                store_type = _str_param(q.get("store_type"), "clothing_store") or "clothing_store"
                return 200, self.search_nearby_stores_data(city=city, state=state, store_type=store_type)

            # --- Step 6: Winning Formula & Optimization ---
            if m == "GET" and clean_path == "/api/v1/optimization/winning-formula":
                res = self.get_winning_formula(
                    video_id=_int_param(q.get("video_id")),
                    campaign_id=_int_param(q.get("campaign_id")),
                )
                return (200 if res["status"] == "success" else 404), res
            if m == "POST" and clean_path == "/api/v1/optimization/apply-winning-formula":
                res = self.apply_winning_formula(WinningFormulaApplyRequest(**b))
                return (200 if res.get("status") == "success" else 400), res

            # --- Datasets Explorer & Management ---
            if m == "GET" and clean_path == "/api/v1/datasets":
                return 200, self.list_datasets()
            if m == "POST" and clean_path == "/api/v1/datasets/seed":
                res = self.seed_or_reset_dataset(DatasetSeedRequest(**b), reset=False)
                return (200 if res["status"] == "success" else 400), res
            if m == "POST" and clean_path == "/api/v1/datasets/reset":
                res = self.seed_or_reset_dataset(DatasetSeedRequest(**b), reset=True)
                return (200 if res["status"] == "success" else 400), res

            ds_match = re.match(r"^/api/v1/datasets/([^/]+)$", clean_path)
            if m == "GET" and ds_match:
                res = self.get_dataset(
                    dataset_name=ds_match.group(1),
                    limit=_int_param(q.get("limit"), 100) or 100,
                    offset=_int_param(q.get("offset"), 0) or 0,
                    q=_str_param(q.get("q") or q.get("search")),
                    campaign_id=_int_param(q.get("campaign_id")),
                    product_id=_int_param(q.get("product_id")),
                    video_id=_int_param(q.get("video_id")),
                    status=_str_param(q.get("status")),
                    category=_str_param(q.get("category")),
                    state=_str_param(q.get("state")),
                    screen_id=_int_param(q.get("screen_id")),
                    days=_int_param(q.get("days"), 7) or 7,
                )
                return (200 if res["status"] == "success" else 404), res

            return 404, {"status": "error", "error": f"Route not found: {m} {clean_path}"}
        except Exception as exc:
            return 422, {"status": "error", "error": str(exc)}


# ============================================================================
# GATEWAY CLIENT (DROP-IN TEST CLIENT WORKABLE WITH OR WITHOUT FASTAPI)
# ============================================================================


class GatewayResponse:
    """HTTP-like response returned by `GatewayClient`."""

    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {"content-type": "application/json"}

    def json(self) -> dict[str, Any]:
        if isinstance(self._payload, bytes):
            return json.loads(self._payload.decode("utf-8"))
        return self._payload

    @property
    def content(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


class GatewayClient:
    """Unified test/programmatic client for `APIGatewayService`."""

    def __init__(self, service: APIGatewayService | None = None) -> None:
        self.service = service or APIGatewayService()

    def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        parsed = urlparse(url)
        query: dict[str, Any] = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
        if params:
            query.update(params)

        asset_match = re.match(r"^/api/v1/assets/([^/]+)/([^/]+)$", parsed.path)
        if method.upper() == "GET" and asset_match:
            file_path, mime = self.service.resolve_static_asset(asset_match.group(1), asset_match.group(2))
            if not file_path:
                return GatewayResponse(404, {"status": "error", "error": "Asset not found."})
            return GatewayResponse(200, file_path.read_bytes(), headers={"content-type": mime})

        code, data = self.service.dispatch(method, parsed.path, query_params=query, body=json_body)
        return GatewayResponse(code, data)

    def get(self, url: str, params: dict[str, Any] | None = None) -> GatewayResponse:
        return self.request("GET", url, params=params)

    def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        payload = json if json is not None else body
        return self.request("POST", url, params=params, json_body=payload)

    def patch(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        payload = json if json is not None else body
        return self.request("PATCH", url, params=params, json_body=payload)

    def put(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        payload = json if json is not None else body
        return self.request("PUT", url, params=params, json_body=payload)


# ============================================================================
# FASTAPI APPLICATION FACTORY (WHEN FASTAPI IS INSTALLED) + STDLIB HTTP SERVER
# ============================================================================

gateway_service = APIGatewayService(auto_init_db=False)


def create_fastapi_app(service: APIGatewayService | None = None) -> Any:
    """Create a full FastAPI application with OpenAPI/Swagger UI and CORS middleware.

    Falls back gracefully to returning a `GatewayClient`-compatible wrapper if
    `fastapi` is not installed in the current Python environment.
    """
    svc = service or gateway_service
    try:
        from fastapi import FastAPI, HTTPException, Query, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse
    except ModuleNotFoundError:
        return GatewayClient(svc)

    app = FastAPI(
        title="Video Ad Optimization Agent — UX API Gateway",
        description=(
            "REST API Gateway exposing all 4 AI Agents, 6 poster workflows, "
            "15+ configurable video generation components, HITL review controls, "
            "in-store retail media analytics, geographic intelligence, winning "
            "formula scaling, and dataset exploration."
        ),
        version=GATEWAY_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _on_startup() -> None:
        svc.ensure_initialized()

    @app.get("/api/v1/health", tags=["Overview & Workflow"])
    def health() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_health()

    @app.get("/api/v1/overview", tags=["Overview & Workflow"])
    def overview() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_overview()

    @app.get("/api/v1/use-cases", tags=["Overview & Workflow"])
    @app.get("/api/v1/workflow/steps", tags=["Overview & Workflow"])
    def use_cases() -> dict[str, Any]:
        return svc.get_use_cases()

    # Step 1: Discover & Agents
    @app.get("/api/v1/discover", tags=["Step 1: Discover & Agents"])
    def discover() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_discover()

    @app.get("/api/v1/agents", tags=["Step 1: Discover & Agents"])
    def agents_list() -> dict[str, Any]:
        return svc.list_agents()

    @app.get("/api/v1/agents/{agent_name}", tags=["Step 1: Discover & Agents"])
    def agent_detail(agent_name: str) -> Any:
        res = svc.get_agent_info(agent_name)
        if res["status"] != "success":
            raise HTTPException(status_code=404, detail=res["error"])
        return res

    @app.post("/api/v1/agents/chat", tags=["Step 1: Discover & Agents"])
    def agent_chat(req: AgentChatRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.chat_with_agent(req)

    @app.post("/api/v1/agents/{agent_name}/chat", tags=["Step 1: Discover & Agents"])
    def specific_agent_chat(agent_name: str, req: AgentChatRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        req.agent_name = agent_name
        return svc.chat_with_agent(req)

    # UX Designer Object Model (object.js compliance)
    @app.get("/api/v1/ux/enums", tags=["UX Designer Object Model"])
    def ux_enums() -> dict[str, Any]:
        return svc.get_ux_enums()

    @app.get("/api/v1/ux/schema", tags=["UX Designer Object Model"])
    def ux_schema() -> dict[str, Any]:
        return svc.get_ux_schema()

    @app.get("/api/v1/ux/campaigns", tags=["UX Designer Object Model"])
    def ux_campaigns_list(
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        product_id: int | None = None,
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        camps = svc.list_ux_campaigns(status=status, category=category, state=state, product_id=product_id)
        return {"status": "success", "total_count": len(camps), "campaigns": camps}

    @app.post("/api/v1/ux/campaigns", status_code=201, tags=["UX Designer Object Model"])
    def ux_campaigns_create(req: dict[str, Any]) -> Any:
        svc.ensure_initialized()
        res = svc.create_ux_campaign(req)
        if not res.get("id"):
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/ux/campaigns/{campaign_id}", tags=["UX Designer Object Model"])
    def ux_campaigns_get(campaign_id: int) -> Any:
        svc.ensure_initialized()
        res = svc.get_ux_campaign(campaign_id)
        if not res.get("id"):
            return JSONResponse(status_code=404, content=res)
        return res

    @app.patch("/api/v1/ux/campaigns/{campaign_id}", tags=["UX Designer Object Model"])
    @app.put("/api/v1/ux/campaigns/{campaign_id}", tags=["UX Designer Object Model"])
    def ux_campaigns_update(campaign_id: int, req: dict[str, Any]) -> Any:
        svc.ensure_initialized()
        res = svc.update_ux_campaign(campaign_id, req)
        if not res.get("id"):
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/ux/videos", tags=["UX Designer Object Model"])
    def ux_videos_list(
        campaign_id: int | None = None,
        status: str | None = None,
        approval_status: int | None = None,
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        vids = svc.list_ux_videos(campaign_id=campaign_id, status=status, approval_status=approval_status)
        return {"status": "success", "total_count": len(vids), "videos": vids}

    @app.get("/api/v1/ux/videos/{video_id}", tags=["UX Designer Object Model"])
    def ux_videos_get(video_id: int) -> Any:
        svc.ensure_initialized()
        res = svc.get_ux_video(video_id)
        if not res.get("id"):
            return JSONResponse(status_code=404, content=res)
        return res

    @app.patch("/api/v1/ux/videos/{video_id}", tags=["UX Designer Object Model"])
    @app.put("/api/v1/ux/videos/{video_id}", tags=["UX Designer Object Model"])
    def ux_videos_update(video_id: int, req: dict[str, Any]) -> Any:
        svc.ensure_initialized()
        res = svc.update_ux_video(video_id, req)
        if not res.get("id"):
            return JSONResponse(status_code=400, content=res)
        return res

    @app.post("/api/v1/ux/videos/{video_id}/approval", tags=["UX Designer Object Model"])
    def ux_videos_set_approval(video_id: int, req: dict[str, Any]) -> Any:
        svc.ensure_initialized()
        app_st = req.get("approval_status", UXApprovalStatus.APPROVED)
        res = svc.set_ux_video_approval(video_id, int(app_st))
        if not res.get("id"):
            return JSONResponse(status_code=400, content=res)
        return res

    # Campaigns & Products
    @app.get("/api/v1/campaigns", tags=["Campaigns & Products"])
    def campaigns_list(
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        product_id: int | None = None,
        format: str | None = None,
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        if format == "ux":
            camps = svc.list_ux_campaigns(status=status, category=category, state=state, product_id=product_id)
            return {"status": "success", "total_count": len(camps), "campaigns": camps}
        return svc.list_campaigns_filtered(
            status=status, category=category, state=state, product_id=product_id
        )

    @app.post("/api/v1/campaigns", status_code=201, tags=["Campaigns & Products"])
    def campaigns_create(req: CampaignCreateRequest) -> Any:
        svc.ensure_initialized()
        res = svc.create_new_campaign(req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/campaigns/{campaign_id}", tags=["Campaigns & Products"])
    def campaigns_get(campaign_id: int, format: str | None = None) -> Any:
        svc.ensure_initialized()
        if format == "ux":
            res = svc.get_ux_campaign(campaign_id)
            if not res.get("id"):
                return JSONResponse(status_code=404, content=res)
            return res
        res = svc.get_campaign_by_id(campaign_id)
        if res.get("status") != "success":
            return JSONResponse(status_code=404, content=res)
        return res

    @app.patch("/api/v1/campaigns/{campaign_id}", tags=["Campaigns & Products"])
    @app.put("/api/v1/campaigns/{campaign_id}", tags=["Campaigns & Products"])
    def campaigns_update(campaign_id: int, req: CampaignUpdateRequest) -> Any:
        svc.ensure_initialized()
        res = svc.update_campaign_by_id(campaign_id, req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/products", tags=["Campaigns & Products"])
    def products_list(
        category: str | None = None,
        garment_type: str | None = None,
        style: str | None = None,
        season: str | None = None,
        search: str | None = None,
        catalog_source: str = "all",
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.list_products_filtered(
            category=category,
            garment_type=garment_type,
            style=style,
            season=season,
            search=search,
            catalog_source=catalog_source,
        )

    @app.post("/api/v1/products", status_code=201, tags=["Campaigns & Products"])
    def products_create(req: ProductCreateRequest) -> Any:
        svc.ensure_initialized()
        res = svc.create_new_product(req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/products/categories", tags=["Campaigns & Products"])
    def products_categories() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_product_categories()

    @app.get("/api/v1/products/{product_id}", tags=["Campaigns & Products"])
    def products_get(product_id: int) -> Any:
        svc.ensure_initialized()
        res = svc.get_product_by_id(product_id)
        if res.get("status") != "success":
            return JSONResponse(status_code=404, content=res)
        return res

    @app.post("/api/v1/products/import-folder", tags=["Campaigns & Products"])
    def products_import_folder(req: ProductImportFolderRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.import_products_folder(req)

    @app.post("/api/v1/products/{product_id}/generate-image", tags=["Campaigns & Products"])
    def products_generate_image(product_id: int, req: ProductGenerateImageRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.generate_product_reference_image(product_id, req)

    @app.post("/api/v1/products/{product_id}/upload-image", tags=["Campaigns & Products"])
    def products_upload_image(product_id: int, req: ProductUploadImageRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.upload_product_reference_image(product_id, req)

    # Step 2: Configurable Video Generation
    @app.get("/api/v1/videos/options", tags=["Step 2: Video Generation & Components"])
    @app.get("/api/v1/videos/components/schema", tags=["Step 2: Video Generation & Components"])
    def videos_options() -> dict[str, Any]:
        return svc.get_video_component_options()

    @app.get("/api/v1/videos/presets", tags=["Step 2: Video Generation & Components"])
    def videos_presets() -> dict[str, Any]:
        return svc.get_video_presets()

    @app.post("/api/v1/videos/prompts/preview", tags=["Step 2: Video Generation & Components"])
    def videos_prompt_preview(req: PromptPreviewRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.preview_video_prompts(req)

    @app.post("/api/v1/videos/generate", tags=["Step 2: Video Generation & Components"])
    @app.post("/api/v1/videos/generate-with-properties", tags=["Step 2: Video Generation & Components"])
    def videos_generate(req: VideoGenerateRequest) -> Any:
        svc.ensure_initialized()
        res = svc.generate_video(req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.post("/api/v1/videos/generate/batch", tags=["Step 2: Video Generation & Components"])
    def videos_generate_batch(req: BatchVideoGenerateRequest) -> Any:
        svc.ensure_initialized()
        res = svc.generate_video_batch(req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/media/seed-images", tags=["Step 2: Video Generation & Components"])
    def media_seed_images(campaign_id: int | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.list_seed_images(campaign_id=campaign_id)

    @app.get("/api/v1/campaigns/{campaign_id}/seed-images", tags=["Step 2: Video Generation & Components"])
    def campaign_seed_images(campaign_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.list_seed_images(campaign_id=campaign_id)

    # Step 3: HITL Review & Activation
    @app.get("/api/v1/videos", tags=["Step 3: HITL Review & Activation"])
    def videos_list(
        campaign_id: int | None = None,
        status: str | None = None,
        product_id: int | None = None,
        model_ethnicity: str | None = None,
        setting: str | None = None,
        mood: str | None = None,
        format: str | None = None,
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        if format == "ux":
            vids = svc.list_ux_videos(campaign_id=campaign_id, status=status)
            return {"status": "success", "total_count": len(vids), "videos": vids}
        return svc.list_videos_filtered(
            campaign_id=campaign_id,
            status=status,
            product_id=product_id,
            model_ethnicity=model_ethnicity,
            setting=setting,
            mood=mood,
        )

    @app.get("/api/v1/review/table", tags=["Step 3: HITL Review & Activation"])
    def review_table(campaign_id: int | None = None, status: str | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return get_video_review_table(campaign_id=campaign_id, status=status)

    @app.get("/api/v1/review/pending", tags=["Step 3: HITL Review & Activation"])
    def review_pending(campaign_id: int | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return list_pending_videos(campaign_id=campaign_id)

    @app.get("/api/v1/review/summary", tags=["Step 3: HITL Review & Activation"])
    def review_summary(campaign_id: int | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return get_activation_summary(campaign_id=campaign_id)

    @app.post("/api/v1/videos/activate-batch", tags=["Step 3: HITL Review & Activation"])
    def videos_activate_batch(req: VideoBatchActivateRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return activate_batch(video_ids=req.video_ids, days_of_metrics=req.days_of_metrics)

    @app.get("/api/v1/videos/{video_id}", tags=["Step 3: HITL Review & Activation"])
    def videos_get(video_id: int, format: str | None = None) -> Any:
        svc.ensure_initialized()
        if format == "ux":
            res = svc.get_ux_video(video_id)
            if not res.get("id"):
                return JSONResponse(status_code=404, content=res)
            return res
        res = get_video_details(video_id=video_id)
        if res.get("status") == "error":
            return JSONResponse(status_code=404, content=res)
        return res

    @app.get("/api/v1/videos/{video_id}/properties", tags=["Step 3: HITL Review & Activation"])
    def videos_properties(video_id: int) -> Any:
        svc.ensure_initialized()
        res = svc.get_video_properties_by_id(video_id)
        if res.get("status") == "error":
            return JSONResponse(status_code=404, content=res)
        return res

    @app.get("/api/v1/videos/{video_id}/status", tags=["Step 3: HITL Review & Activation"])
    def videos_status(video_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return get_video_status(video_id=video_id)

    @app.post("/api/v1/videos/{video_id}/activate", tags=["Step 3: HITL Review & Activation"])
    def videos_activate(video_id: int, req: VideoActivateRequest | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        days = req.days_of_metrics if req else 30
        return activate_video(video_id=video_id, days_of_metrics=days)

    @app.post("/api/v1/videos/{video_id}/pause", tags=["Step 3: HITL Review & Activation"])
    def videos_pause(video_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return pause_video(video_id=video_id)

    @app.post("/api/v1/videos/{video_id}/archive", tags=["Step 3: HITL Review & Activation"])
    def videos_archive(video_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return archive_video(video_id=video_id)

    @app.post("/api/v1/videos/{video_id}/extend-metrics", tags=["Step 3: HITL Review & Activation"])
    def videos_extend_metrics(
        video_id: int, req: VideoExtendMetricsRequest | None = None
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        days = req.additional_days if req else 7
        return generate_additional_metrics(video_id=video_id, additional_days=days)

    @app.post("/api/v1/videos/{video_id}/edit", tags=["Step 3: HITL Review & Activation"])
    def videos_edit(video_id: int, req: VideoOmniEditRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.edit_video_omni(video_id, req)

    # Step 4: Analytics & Metrics
    @app.get("/api/v1/analytics/overview", tags=["Step 4: Analytics & Metrics"])
    def analytics_overview() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_analytics_overview()

    @app.get("/api/v1/analytics/top-ads", tags=["Step 4: Analytics & Metrics"])
    def analytics_top_ads(
        metric: str = "rpi", limit: int = 10, campaign_id: int | None = None
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_top_performing(metric=metric, limit=limit, campaign_id=campaign_id)

    @app.get("/api/v1/analytics/campaigns/compare", tags=["Step 4: Analytics & Metrics"])
    def analytics_compare_get(
        campaign_ids: str = Query(default="1,2,3,4", description="Comma-separated campaign IDs")
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        cids = [int(x.strip()) for x in campaign_ids.split(",") if x.strip().isdigit()]
        return compare_campaigns(campaign_ids=cids or [1, 2, 3, 4])

    @app.post("/api/v1/analytics/campaigns/compare", tags=["Step 4: Analytics & Metrics"])
    def analytics_compare_post(req: CampaignCompareRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return compare_campaigns(campaign_ids=req.campaign_ids)

    @app.get("/api/v1/analytics/campaigns/{campaign_id}/metrics", tags=["Step 4: Analytics & Metrics"])
    def analytics_campaign_metrics(campaign_id: int, days: int | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        kwargs = {"days": days} if days is not None else {}
        return get_campaign_metrics(campaign_id=campaign_id, **kwargs)

    @app.get("/api/v1/analytics/campaigns/{campaign_id}/insights", tags=["Step 4: Analytics & Metrics"])
    def analytics_campaign_insights(campaign_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return get_campaign_insights(campaign_id=campaign_id)

    @app.get("/api/v1/analytics/campaigns/{campaign_id}/creatives", tags=["Step 4: Analytics & Metrics"])
    def analytics_campaign_creatives(campaign_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return compare_creatives_within_campaign(campaign_id=campaign_id)

    @app.post(
        "/api/v1/analytics/campaigns/{campaign_id}/creatives/chart",
        tags=["Step 4: Analytics & Metrics"],
    )
    def analytics_campaign_chart(campaign_id: int) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.generate_campaign_chart(campaign_id)

    @app.post(
        "/api/v1/analytics/campaigns/{campaign_id}/visualizations",
        tags=["Step 4: Analytics & Metrics"],
    )
    def analytics_campaign_vis(
        campaign_id: int, req: VisualizationRequest | None = None
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.generate_campaign_infographic(campaign_id, req or VisualizationRequest())

    # Step 5: Geographic Intelligence & Maps
    @app.get("/api/v1/maps/campaigns", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_campaigns(campaign_ids: str | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        cids = (
            [int(x.strip()) for x in campaign_ids.split(",") if x.strip().isdigit()]
            if campaign_ids
            else None
        )
        return svc.get_campaign_map_data(campaign_ids=cids)

    @app.get("/api/v1/maps/locations", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_locations(campaign_id: int | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_campaign_locations_data(campaign_id=campaign_id)

    @app.get("/api/v1/maps/regions", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_regions() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_regional_comparison()

    @app.post("/api/v1/maps/static", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_static(req: StaticMapRequest) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.generate_static_map_url(req)

    @app.post("/api/v1/maps/visualizations", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_visualizations(req: VisualizationRequest | None = None) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.generate_map_infographic(req or VisualizationRequest())

    @app.get("/api/v1/maps/demographics", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_demographics(city: str = "Los Angeles", state: str = "CA") -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.get_location_demographics_data(city=city, state=state)

    @app.get("/api/v1/maps/nearby-stores", tags=["Step 5: Geographic Intelligence & Maps"])
    def maps_nearby_stores(
        city: str = "Los Angeles", state: str = "CA", store_type: str = "clothing_store"
    ) -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.search_nearby_stores_data(city=city, state=state, store_type=store_type)

    # Step 6: Scale What Works (Winning Formula)
    @app.get("/api/v1/optimization/winning-formula", tags=["Step 6: Scale What Works"])
    def optimization_winning_formula(
        video_id: int | None = None, campaign_id: int | None = None
    ) -> Any:
        svc.ensure_initialized()
        res = svc.get_winning_formula(video_id=video_id, campaign_id=campaign_id)
        if res["status"] != "success":
            return JSONResponse(status_code=404, content=res)
        return res

    @app.post("/api/v1/optimization/apply-winning-formula", tags=["Step 6: Scale What Works"])
    def optimization_apply_winning_formula(req: WinningFormulaApplyRequest) -> Any:
        svc.ensure_initialized()
        res = svc.apply_winning_formula(req)
        if res.get("status") != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    # Datasets Explorer
    @app.get("/api/v1/datasets", tags=["Datasets Explorer"])
    def datasets_list() -> dict[str, Any]:
        svc.ensure_initialized()
        return svc.list_datasets()

    @app.post("/api/v1/datasets/seed", tags=["Datasets Explorer"])
    def datasets_seed(req: DatasetSeedRequest) -> Any:
        res = svc.seed_or_reset_dataset(req, reset=False)
        if res["status"] != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.post("/api/v1/datasets/reset", tags=["Datasets Explorer"])
    def datasets_reset(req: DatasetSeedRequest) -> Any:
        res = svc.seed_or_reset_dataset(req, reset=True)
        if res["status"] != "success":
            return JSONResponse(status_code=400, content=res)
        return res

    @app.get("/api/v1/datasets/{dataset_name}", tags=["Datasets Explorer"])
    def datasets_get(
        dataset_name: str,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
        campaign_id: int | None = None,
        product_id: int | None = None,
        video_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        screen_id: int | None = None,
        days: int = 7,
    ) -> Any:
        svc.ensure_initialized()
        res = svc.get_dataset(
            dataset_name=dataset_name,
            limit=limit,
            offset=offset,
            q=q,
            campaign_id=campaign_id,
            product_id=product_id,
            video_id=video_id,
            status=status,
            category=category,
            state=state,
            screen_id=screen_id,
            days=days,
        )
        if res["status"] != "success":
            return JSONResponse(status_code=404, content=res)
        return res

    # Static Assets
    @app.get("/api/v1/assets/{bucket_dir}/{filename}", tags=["Media Assets"])
    def serve_asset(bucket_dir: str, filename: str, request: Request) -> Any:
        file_path, mime = svc.resolve_static_asset(bucket_dir, filename)
        if not file_path:
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(path=str(file_path), media_type=mime)

    return app


app = create_fastapi_app(gateway_service)


def run_stdlib_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the API Gateway using Python's built-in ThreadingHTTPServer (zero external deps)."""
    svc = APIGatewayService(auto_init_db=True)

    class _GatewayHTTPHandler(BaseHTTPRequestHandler):
        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            asset_match = re.match(r"^/api/v1/assets/([^/]+)/([^/]+)$", parsed.path)
            if method == "GET" and asset_match:
                file_path, mime = svc.resolve_static_asset(asset_match.group(1), asset_match.group(2))
                if not file_path:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"error","error":"Asset not found"}')
                    return
                data = file_path.read_bytes()
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            length = int(self.headers.get("Content-Length", "0") or "0")
            body_dict: dict[str, Any] = {}
            if length > 0:
                raw_body = self.rfile.read(length).decode("utf-8")
                try:
                    body_dict = json.loads(raw_body)
                except json.JSONDecodeError:
                    body_dict = {}

            query = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
            code, payload = svc.dispatch(method, parsed.path, query_params=query, body=body_dict)
            encoded = json.dumps(payload, default=str).encode("utf-8")

            self.send_response(code)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_PUT(self) -> None:
            self._handle("PUT")

        def do_PATCH(self) -> None:
            self._handle("PATCH")

    server = ThreadingHTTPServer((host, port), _GatewayHTTPHandler)
    print(f"API Gateway running on http://{host}:{port} (stdlib HTTP server)")
    server.serve_forever()


def main() -> None:
    """CLI entrypoint for launching the API Gateway server."""
    parser = argparse.ArgumentParser(description="Run the Video Ad Optimization Agent API Gateway.")
    parser.add_argument("--host", default=os.getenv("API_HOST", "0.0.0.0"), help="Bind host")
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")), help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (Uvicorn only)")
    args = parser.parse_args()

    try:
        import uvicorn

        uvicorn.run("app.api_gateway:app", host=args.host, port=args.port, reload=args.reload)
    except ModuleNotFoundError:
        run_stdlib_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
