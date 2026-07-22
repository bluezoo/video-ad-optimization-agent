# Workstream 09: Prompt & Agent Generalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any product category generates category-appropriate ad videos via a deterministic archetype template registry (Option B, owner-approved); all agent instructions, descriptions, campaign text, and maps tools lose hardcoded fashion framing; the integration eval suite becomes able to fail and gains non-fashion cases.

**Architecture:** A new `app/tools/prompt_archetypes.py` maps product category → archetype (`wearable` / `consumable-hero` / `staged-product` / `product-hero`), with `CreativeVariation.presentation_mode` as an override knob. The three prompt builders in `prompt_builders.py` become dispatchers: `wearable` keeps the existing fashion body (byte-identical for explicit-ethnicity inputs, golden-pinned); the other archetypes route to new product-centric builders that use only the generic variation fields. `video_tools.py`'s active pipeline branches its reference-image preamble by archetype and fails loudly on malformed variation input.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Google ADK, existing repo conventions.

## Global Constraints

- **Wearable regression bar:** `build_scene_image_prompt` / `build_creative_prompt` output for product 1 with `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")` must be **byte-identical before and after** every task (goldens captured in Task 1 from unmodified code).
- The default-"diverse" wording **changes deliberately** (non-reductive rewrite) — the exact new string is fixed in Task 3 and asserted directly, never golden-compared against old output.
- New-archetype prompts must contain **none of**: `fashion`, `garment`, `wearing`, `she is`, `model wearing` (case-insensitive).
- A PostToolUse hook runs `make test-unit` after every `app/**/*.py` edit — each task must land its test updates in the **same task** as the code change (goldens/tests first where possible) so the hook never loops red.
- No `Co-Authored-By`/AI-attribution trailers in commits. `README.md` and `DEMO_GUIDE.md` untouched.
- Run `make lint` before each commit; ruff must be clean.
- All file:line anchors below verified 2026-07-21 against `version_2` @ 170dcbc.

---

### Task 1: Re-baseline the golden prompt tests (explicit ethnicity) — code untouched

**Files:**
- Modify: `tests/unit/test_product_adapter.py:46-72` (TestGoldenPrompts)
- Create: `tests/unit/data/golden_scene_prompt_product1_asian.txt`, `tests/unit/data/golden_creative_prompt_product1_asian.txt`
- Delete: `tests/unit/data/golden_scene_prompt_product1.txt`, `tests/unit/data/golden_creative_prompt_product1.txt`

**Interfaces:**
- Produces: the two `*_asian.txt` golden files + tests pinning `build_scene_image_prompt(product1, VAR_ASIAN)` and `build_creative_prompt(product1, VAR_ASIAN)` where `VAR_ASIAN = CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")`. Every later task must keep these green.
- Rationale (from kickoff DISCOVERY 1): the old goldens pin the bare-default variation whose output contains "a beautiful woman" — the exact text Task 3 rewrites. Replacement, not exclusion.

- [ ] **Step 1: Capture new goldens from UNMODIFIED code**

```bash
.venv/bin/python - << 'EOF'
from app.database.db import get_product
from app.models.variation import CreativeVariation
from app.tools.prompt_builders import build_scene_image_prompt, build_creative_prompt
import tests.conftest  # noqa: F401  # not needed if get_product works on the real db copy
p = get_product(1)
v = CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")
open("tests/unit/data/golden_scene_prompt_product1_asian.txt", "w").write(build_scene_image_prompt(p, v))
open("tests/unit/data/golden_creative_prompt_product1_asian.txt", "w").write(build_creative_prompt(p, v))
print("captured")
EOF
```

(If `get_product(1)` needs a DB, run once after `make reset-db`-style repopulation, or construct the product inline exactly as `tests/unit/test_product_adapter.py` does today — copy its product-1 fixture approach verbatim.)

- [ ] **Step 2: Verify the captured files** contain `a graceful Asian woman with sleek dark hair` and do NOT contain `a beautiful woman`.

- [ ] **Step 3: Rewrite TestGoldenPrompts** — replace the variation construction at `tests/unit/test_product_adapter.py:52` and `:58` with `CreativeVariation(name="golden-baseline-asian", model_ethnicity="asian")` and point the two file paths at the `*_asian.txt` names. Delete the two old golden files. Leave `test_null_style_falls_back_to_category` (:62-72) untouched for now — Task 3 rewrites it.

- [ ] **Step 4: Run** `pytest tests/unit/test_product_adapter.py -v` → all pass. Then `make test-unit` → green.

- [ ] **Step 5: Commit** `test: re-baseline golden prompts on explicit asian ethnicity (ws09 Task 1)`

---

### Task 2: `presentation_mode` + Optional human-model fields on CreativeVariation

**Files:**
- Modify: `app/models/variation.py` (fields at :44-48, :104; class only)
- Test: `tests/unit/test_video_tools.py` (TestCreativeVariation) + new assertions

**Interfaces:**
- Produces: `CreativeVariation.presentation_mode: Optional[str] = None` (values: `None`/"auto", `"with_model"`, `"product_only"`); `model_ethnicity: Optional[str] = "diverse"`, `model_description: Optional[str] = ""`, `activity: Optional[str] = "walking"` — **types become Optional, defaults are RETAINED** (deliberate deviation from the phase doc's step-3 letter: changing defaults to None would alter wearable output and break Task 1's goldens; product-centric builders ignore these fields entirely, which satisfies the step's intent). Wearable builders (Task 3) guard None via `variation.model_ethnicity or "diverse"` etc.
- `get_summary()` (:137) keeps working: `self.model_ethnicity != "diverse"` is True for None — acceptable only because defaults are retained; add a `or "diverse"` guard anyway (see Step 1).

- [ ] **Step 1: Edit `app/models/variation.py`:**

```python
# after the name field, before model_ethnicity:
    presentation_mode: Optional[str] = Field(
        default=None,
        description="How the product is presented: None/'auto' (archetype registry decides "
                    "by product category), 'with_model' (human model — wearable products only), "
                    "'product_only' (product-centric shot, no human)"
    )
```

Change the three field annotations (defaults unchanged): `model_ethnicity: Optional[str] = Field(default="diverse", ...)`, `model_description: Optional[str] = Field(default="", ...)`, `activity: Optional[str] = Field(default="walking", ...)`. Add `Optional` to the existing `typing` import if missing. In `get_summary()` change the ethnicity line to `if (self.model_ethnicity or "diverse") != "diverse":`.

- [ ] **Step 2: Add tests** to `tests/unit/test_video_tools.py::TestCreativeVariation`:

```python
    def test_presentation_mode_defaults_to_none(self):
        from app.models.variation import CreativeVariation
        v = CreativeVariation(name="t")
        assert v.presentation_mode is None

    def test_presentation_mode_accepts_product_only(self):
        from app.models.variation import CreativeVariation
        v = CreativeVariation.model_validate({"name": "t", "presentation_mode": "product_only"})
        assert v.presentation_mode == "product_only"

    def test_human_fields_accept_none(self):
        from app.models.variation import CreativeVariation
        v = CreativeVariation.model_validate(
            {"name": "t", "model_ethnicity": None, "activity": None, "model_description": None})
        assert v.model_ethnicity is None
        assert v.get_summary()  # must not raise
```

- [ ] **Step 3: Run** `pytest tests/unit/test_video_tools.py tests/unit/test_product_adapter.py -v` → pass (goldens unaffected: defaults retained). `make test-unit` green.
- [ ] **Step 4: Commit** `feat: add presentation_mode + Optional human-model fields to CreativeVariation (ws09 Task 2)`

---

### Task 3: Archetype registry + product-centric prompt builders + diverse-wording fix

**Files:**
- Create: `app/tools/prompt_archetypes.py`
- Modify: `app/tools/prompt_builders.py`
- Test: `tests/unit/test_prompt_archetypes.py` (new), `tests/unit/test_product_adapter.py`

**Interfaces:**
- Consumes: `Product` (app/models/product.py), `CreativeVariation` incl. `presentation_mode` (Task 2).
- Produces:
  - `prompt_archetypes.ARCHETYPE_BY_CATEGORY: dict[str, str]`
  - `prompt_archetypes.resolve_archetype(product, variation) -> str` — returns one of `"wearable" | "consumable-hero" | "staged-product" | "product-hero"`; raises `ValueError` for `with_model` on a non-wearable category.
  - The three public builders keep their exact names/signatures and dispatch on the archetype. Task 4 imports `resolve_archetype`.
- New "diverse" wording (fixed here, asserted directly): **`"a confident, radiant woman with a warm, engaging presence"`** — replaces BOTH the map entry (`:64`, `:297`) and the `.get()` miss-fallback (`:66`, `:299`).

- [ ] **Step 1: Write failing tests first** — `tests/unit/test_prompt_archetypes.py`:

```python
"""Tests for the archetype registry and product-centric prompt builders (ws09)."""
import pytest
from app.models.product import Product
from app.models.variation import CreativeVariation

BANNED = ("fashion", "garment", "wearing", "she is", "model wearing")

def _beverage():
    return Product(name="aurora-cold-brew-330ml", category="beverage",
                   description="Smooth cold brew coffee in a 330ml can",
                   image_filename="aurora-cold-brew-330ml.png",
                   attributes={"roast": "medium", "size": "330ml"})

def _electronics():
    return Product(name="pulse-anc-wireless-earbuds", category="electronics",
                   description="Active noise cancelling wireless earbuds",
                   image_filename="pulse-anc-wireless-earbuds.png", attributes={})

def _unknown():
    return Product(name="vendor-demo-trail-shoe-wax", category="outdoor-gear",
                   description="Waterproofing wax for trail shoes",
                   image_filename="x.png", attributes={})

class TestResolveArchetype:
    def test_fashion_category_is_wearable(self):
        from app.tools.prompt_archetypes import resolve_archetype
        p = Product(name="d", category="dress", description="", image_filename="d.png")
        assert resolve_archetype(p, CreativeVariation(name="t")) == "wearable"

    def test_beverage_is_consumable_hero(self):
        from app.tools.prompt_archetypes import resolve_archetype
        assert resolve_archetype(_beverage(), CreativeVariation(name="t")) == "consumable-hero"

    def test_electronics_is_staged_product(self):
        from app.tools.prompt_archetypes import resolve_archetype
        assert resolve_archetype(_electronics(), CreativeVariation(name="t")) == "staged-product"

    def test_unknown_category_is_product_hero(self):
        from app.tools.prompt_archetypes import resolve_archetype
        assert resolve_archetype(_unknown(), CreativeVariation(name="t")) == "product-hero"

    def test_product_only_forces_product_path_for_wearable(self):
        from app.tools.prompt_archetypes import resolve_archetype
        p = Product(name="d", category="dress", description="", image_filename="d.png")
        v = CreativeVariation(name="t", presentation_mode="product_only")
        assert resolve_archetype(p, v) == "product-hero"

    def test_with_model_on_non_wearable_raises(self):
        from app.tools.prompt_archetypes import resolve_archetype
        v = CreativeVariation(name="t", presentation_mode="with_model")
        with pytest.raises(ValueError, match="with_model"):
            resolve_archetype(_beverage(), v)

class TestProductCentricPrompts:
    @pytest.mark.parametrize("maker", [_beverage, _electronics, _unknown])
    def test_scene_prompt_has_no_fashion_language(self, maker):
        from app.tools.prompt_builders import build_scene_image_prompt
        out = build_scene_image_prompt(maker(), CreativeVariation(name="t")).lower()
        for banned in BANNED:
            assert banned not in out, f"banned term {banned!r} in prompt"
        assert "none" not in out.split()  # no literal None leakage

    @pytest.mark.parametrize("builder_name", ["build_scene_image_prompt",
                                              "build_video_animation_prompt",
                                              "build_creative_prompt"])
    def test_all_builders_clean_for_beverage(self, builder_name):
        import app.tools.prompt_builders as pb
        out = getattr(pb, builder_name)(_beverage(), CreativeVariation(name="t")).lower()
        for banned in BANNED:
            assert banned not in out

    def test_beverage_prompt_mentions_product_and_appetite_cues(self):
        from app.tools.prompt_builders import build_scene_image_prompt
        out = build_scene_image_prompt(_beverage(), CreativeVariation(name="t"))
        assert "Aurora Cold Brew" in out
        assert "condensation" in out.lower()

    def test_prompts_are_deterministic(self):
        from app.tools.prompt_builders import build_scene_image_prompt
        a = build_scene_image_prompt(_beverage(), CreativeVariation(name="t"))
        b = build_scene_image_prompt(_beverage(), CreativeVariation(name="t"))
        assert a == b

class TestDiverseWordingFix:
    def test_new_diverse_wording_in_scene_prompt(self):
        from app.tools.prompt_builders import build_scene_image_prompt
        p = Product(name="black-high-waist-trousers", category="pants",
                    description="High waist trousers", image_filename="t.png",
                    attributes={"style": "tailored wide-leg trousers"})
        out = build_scene_image_prompt(p, CreativeVariation(name="t"))  # default diverse
        assert "a beautiful woman" not in out
        assert "a confident, radiant woman with a warm, engaging presence" in out

    def test_unknown_ethnicity_gets_new_fallback_not_reductive(self):
        from app.tools.prompt_builders import build_scene_image_prompt
        p = Product(name="black-high-waist-trousers", category="pants",
                    description="High waist trousers", image_filename="t.png",
                    attributes={"style": "tailored wide-leg trousers"})
        out = build_scene_image_prompt(p, CreativeVariation(name="t", model_ethnicity="martian"))
        assert "a beautiful woman" not in out
```

Run: `pytest tests/unit/test_prompt_archetypes.py -v` → FAIL (module missing).

- [ ] **Step 2: Create `app/tools/prompt_archetypes.py`:**

```python
"""Archetype registry: maps product categories to prompt archetypes (ws09, Option B).

An archetype decides which prompt template family a product uses. Adding a new
vertical = one entry in ARCHETYPE_BY_CATEGORY (or nothing at all — unknown
categories fall back to the generic "product-hero"). Phase 15 may layer an LLM
prompt-writer behind the same resolve_archetype() seam for vendor onboarding.
"""
from ..models.product import Product
from ..models.variation import CreativeVariation

WEARABLE = "wearable"
CONSUMABLE_HERO = "consumable-hero"
STAGED_PRODUCT = "staged-product"
PRODUCT_HERO = "product-hero"

ARCHETYPE_BY_CATEGORY: dict[str, str] = {
    # fashion catalog (with-model path, preserved from the fashion-only era)
    "dress": WEARABLE, "top": WEARABLE, "pants": WEARABLE,
    "skirt": WEARABLE, "outerwear": WEARABLE, "footwear": WEARABLE,
    # retail core test set verticals (ws08)
    "beverage": CONSUMABLE_HERO, "qsr-menu-item": CONSUMABLE_HERO,
    "electronics": STAGED_PRODUCT, "furniture": STAGED_PRODUCT,
    "home-appliance": STAGED_PRODUCT,
}


def resolve_archetype(product: Product, variation: CreativeVariation) -> str:
    """Resolve which prompt archetype a (product, variation) pair uses.

    presentation_mode overrides the registry: "product_only" forces a
    product-centric shot even for wearables; "with_model" is only valid for
    wearable categories (person-using-product for other verticals is future
    work — see 09 phase doc exit criteria).
    """
    mapped = ARCHETYPE_BY_CATEGORY.get(product.category, PRODUCT_HERO)
    mode = variation.presentation_mode
    if mode in (None, "auto"):
        return mapped
    if mode == "product_only":
        return mapped if mapped != WEARABLE else PRODUCT_HERO
    if mode == "with_model":
        if mapped != WEARABLE:
            raise ValueError(
                f"presentation_mode 'with_model' is not supported for category "
                f"'{product.category}' (archetype '{mapped}') — only wearable "
                f"products support human-model shots in this version"
            )
        return WEARABLE
    raise ValueError(
        f"Invalid presentation_mode '{mode}' — valid values: auto, with_model, product_only"
    )
```

- [ ] **Step 3: Refactor `app/tools/prompt_builders.py`:**

1. Rename the existing three function bodies to `_build_wearable_scene_prompt`, `_build_wearable_animation_prompt`, `_build_wearable_creative_prompt` (bodies unchanged except the guards and wording fix below). Public names become dispatchers:

```python
def build_scene_image_prompt(product: Product, variation: CreativeVariation) -> str:
    """Build a prompt for generating a scene-ready first frame image."""
    archetype = resolve_archetype(product, variation)
    if archetype == WEARABLE:
        return _build_wearable_scene_prompt(product, variation)
    return _build_product_scene_prompt(product, variation, archetype)
```

(same pattern for the animation and creative builders; import `resolve_archetype`, `WEARABLE`, `CONSUMABLE_HERO` from `.prompt_archetypes`).

2. In BOTH wearable ethnicity maps: `"diverse": "a confident, radiant woman with a warm, engaging presence"`, and the `.get()` fallback second argument becomes the same string. Add None guards preserving byte-identity for explicit inputs: `ethnicity_map.get(variation.model_ethnicity or "diverse", ...)`, `pose_map.get(variation.activity or "walking", ...)` in the scene builder, `activity_animation.get(variation.activity or "walking", ...)` in the animation builder, `activity_map.get(variation.activity or "walking", ...)` in the creative builder, and `variation.model_description or ethnicity_map.get(...)` stays as-is (empty string and None are both falsy). While here, collapse the dead identical if/else at :48-51 into a single assignment (output-identical, reviewer-noted).

3. Add the product-centric builders (module-private), driven only by generic variation fields:

```python
_ARCHETYPE_SCENE_FLAVOR = {
    CONSUMABLE_HERO: (
        "Appetizing hero shot. Emphasize freshness and appetite appeal: "
        "condensation on cold surfaces, gentle steam on hot items, vivid "
        "natural textures of the ingredients."
    ),
    STAGED_PRODUCT: (
        "Styled environment staging. Place the product in a realistic, "
        "aspirational setting that shows how it lives in a customer's space, "
        "with supporting props kept subtle and out of focus."
    ),
    PRODUCT_HERO: (
        "Clean product hero shot. The product is the sole subject, centered, "
        "with generous negative space and a premium, minimal backdrop."
    ),
}

_PRODUCT_SETTING_MAP = {
    "studio": "on a minimalist studio pedestal with a seamless backdrop",
    "cafe": "on a rustic wooden cafe table with soft ambient depth behind it",
    "urban": "against a stylish urban backdrop with modern architectural lines",
    "beach": "on sun-warmed driftwood with the shoreline softly blurred behind",
    "rooftop": "on a rooftop terrace ledge overlooking a city skyline",
    "garden": "on a stone surface amid lush greenery and blooming flowers",
    "street": "on a bistro table along a charming cobblestone street",
    "luxury-interior": "on a marble surface in an opulent interior",
    "nature": "on natural stone in a serene landscape",
    "park": "on a picnic table in a sunlit park",
}


def _render_attributes(product: Product) -> str:
    if not product.attributes:
        return ""
    details = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(product.attributes.items()))
    return f"Product details: {details}."


def _build_product_scene_prompt(product: Product, variation: CreativeVariation, archetype: str) -> str:
    product_title = product.name.replace("-", " ").title()
    setting_desc = _PRODUCT_SETTING_MAP.get(
        variation.setting, f"in a {variation.setting} setting")
    time_map = {
        "golden-hour": "during golden hour with warm, soft light",
        "sunrise": "at sunrise with soft pink and orange morning light",
        "day": "in bright natural daylight",
        "sunset": "at sunset with warm orange and purple hues",
        "dusk": "at dusk with purple twilight ambiance",
        "night": "at night with atmospheric city lights and ambient glow",
        "morning": "in soft morning light",
    }
    time_desc = time_map.get(variation.time_of_day, "")
    lighting_map = {
        "natural": "Natural, soft lighting",
        "studio": "Professional studio lighting with soft shadows",
        "dramatic": "Dramatic contrast lighting with deep shadows",
        "soft": "Soft, diffused ethereal lighting",
        "golden": "Warm golden hour lighting",
        "neon": "Atmospheric neon lighting with colorful accents",
        "moody": "Moody, atmospheric low-key lighting",
    }
    lighting_desc = lighting_map.get(variation.lighting, f"{variation.lighting} lighting")
    style_map = {
        "cinematic": "Cinematic commercial product photography",
        "editorial": "High-end editorial product photography",
        "commercial": "Polished commercial advertising photography",
        "artistic": "Artistic still-life product photography",
        "documentary": "Natural documentary-style product photography",
    }
    style_desc = style_map.get(variation.visual_style, "Professional commercial product photography")
    key_features = product.description or "its signature design details"

    return f"""{style_desc} of {product_title}, presented {setting_desc} {time_desc}.

{_ARCHETYPE_SCENE_FLAVOR[archetype]}

{lighting_desc}. The product is clearly visible with all its details: {key_features}.
{_render_attributes(product)}

CRITICAL - PRODUCT PRESERVATION:
- The product must match the reference EXACTLY - same shape, colors, materials, branding, and label design
- Do NOT alter, modify, or reinterpret the product design, packaging, or logo in any way

QUALITY REQUIREMENTS:
- The product is the clear hero of the frame, sharply in focus
- Professional advertisement quality with a {variation.mood} mood
- Vertical 9:16 aspect ratio composition
- The scene should look like the perfect first frame of a premium video ad

Style: Premium retail campaign, magazine-quality, aspirational."""


def _build_product_animation_prompt(product: Product, variation: CreativeVariation, archetype: str) -> str:
    camera_map = {
        "orbit": "Camera slowly orbits around the product",
        "pan": "Camera pans smoothly across the scene",
        "dolly": "Camera dollies in slowly toward the product",
        "static": "Camera holds steady with subtle breathing movement",
        "tracking": "Camera glides alongside the product",
        "crane": "Camera sweeps with elegant crane movement",
        "handheld": "Camera has subtle natural handheld movement",
    }
    camera_desc = camera_map.get(variation.camera_movement, "Camera moves smoothly")
    motion_flavor = {
        CONSUMABLE_HERO: "condensation droplets glistening, gentle steam or fizz, "
                         "ingredients settling naturally",
        STAGED_PRODUCT: "ambient light shifting across surfaces, subtle environmental "
                        "movement around the product",
        PRODUCT_HERO: "light sweeping slowly across the product's surfaces",
    }[archetype]
    energy_map = {
        "calm": "slow, graceful, meditative pace",
        "moderate": "smooth, elegant movement",
        "dynamic": "energetic, fluid motion",
        "high-energy": "vibrant, dynamic, fast-paced movement",
    }
    energy_desc = energy_map.get(variation.energy, "smooth, elegant movement")
    product_title = product.name.replace("-", " ").title()

    return f"""{camera_desc}, showcasing {product_title} from its most appealing angles.

The scene has {motion_flavor}. The movement is {energy_desc}.

CRITICAL - PRODUCT & QUALITY PRESERVATION:
- Maintain the product's exact appearance from the first frame throughout the video
- Branding, labels, and materials stay crisp and unaltered
- Smooth, professional camera work
- High-end retail advertisement aesthetic

8 seconds. Vertical 9:16. Cinematic quality. Professional product video ad."""


def _build_product_creative_prompt(product: Product, variation: CreativeVariation, archetype: str) -> str:
    scene = _build_product_scene_prompt(product, variation, archetype)
    motion = _build_product_animation_prompt(product, variation, archetype)
    return f"{scene}\n\n{motion}"
```

4. **Rewrite `test_null_style_falls_back_to_category`** in `tests/unit/test_product_adapter.py` — it currently pins the cold-brew-dress fallback. New version:

```python
    def test_null_style_beverage_routes_to_product_prompt(self):
        """ws08 pinned the fashion fallback for style-less products; ws09 replaces it:
        a beverage now gets a product-centric prompt, never a garment prompt."""
        product = Product(name="test-beverage", category="beverage",
                          description="A refreshing drink", image_filename="b.png",
                          attributes={})
        prompt = build_scene_image_prompt(product, CreativeVariation(name="t"))
        assert "wearing" not in prompt.lower()
        assert "Test Beverage" in prompt
        assert "None" not in prompt
```

- [ ] **Step 4: Run** `pytest tests/unit/test_prompt_archetypes.py tests/unit/test_product_adapter.py -v` → ALL pass (goldens byte-identical proves wearable preservation). `make test-unit` green, `make lint` clean.
- [ ] **Step 5: Commit** `feat: archetype registry + product-centric prompt builders + non-reductive diverse wording (ws09 Task 3)`

---

### Task 4: video_tools.py active-path generalization

**Files:**
- Modify: `app/tools/video_tools.py` (:20, :141, :156, :194-196, :233, :265-268, :486-504, :522-534, :1854-1922)
- Test: `tests/unit/test_video_tools.py`

**Interfaces:**
- Consumes: `resolve_archetype` (Task 3), `presentation_mode` (Task 2).
- Produces: `generate_scene_image(..., archetype: str = "wearable")`; `generate_video_from_product` returns a structured error on malformed variation dicts and surfaces `reference_image_used` in its result; `generate_video_with_variation(..., presentation_mode: str = None)`.

- [ ] **Step 1: Reference-image preamble branch.** `generate_scene_image` gains a keyword param `archetype: str = "wearable"`. At :233 replace the hardcoded string:

```python
            if archetype == "wearable":
                reference_instruction = ("Use this product image as reference for the garment. "
                                         "Generate a scene with a model wearing this exact garment:\n")
            else:
                reference_instruction = ("Use this product image as the exact visual reference for the product. "
                                         "Generate a scene featuring this exact product — same shape, colors, "
                                         "branding, and label design:\n")
            contents = [reference_instruction, image_part, "\n" + scene_prompt]
```

The caller inside `generate_video_from_product` computes `archetype = resolve_archetype(product, variation_obj)` once (right after variation resolution) and passes it to `generate_scene_image` (and uses it for Step 4's naming). Wrap the `resolve_archetype` call: a `ValueError` (invalid/with_model-on-non-wearable) returns `{"status": "error", "error": str(e)}` from the tool.

- [ ] **Step 2: Loud variation validation.** Replace the silent salvage at :492-499:

```python
    elif isinstance(variation, dict):
        try:
            variation_obj = CreativeVariation.model_validate({"name": "custom", **variation})
        except Exception as e:
            return {
                "status": "error",
                "error": f"Invalid variation parameters: {e}",
                "hint": "Valid fields: " + ", ".join(CreativeVariation.model_fields.keys()),
            }
```

(Keep the None → `get_default_variation()` and CreativeVariation-passthrough branches; the final `else` also becomes a structured error instead of a silent default.) Note: today `model_validate(variation)` fails when the LLM omits `name` — the `{"name": "custom", **variation}` merge preserves that convenience while making REAL field errors loud.

- [ ] **Step 3: Surface missing reference image.** At :522-534, keep behavior (generation proceeds) but record it: set `reference_image_used = product_image_bytes is not None` and include in the tool's success payload: `"reference_image_used": reference_image_used`, plus when False a `"warning": f"No product image found for {product.name} — scene generated from text description only"`. 

- [ ] **Step 4: `generate_video_with_variation`** gains `presentation_mode: str = None` (docstring documents auto/with_model/product_only); passes it into the `CreativeVariation(...)` construction. Product-centric naming in `generate_video_from_product` after archetype resolution:

```python
    if archetype != "wearable" and variation_obj.name.startswith(f"{variation_obj.model_ethnicity}-"):
        variation_obj.name = f"{product.category}-{variation_obj.setting}-{variation_obj.mood}"
```

- [ ] **Step 5: Stale-text cleanups (same file):** module docstring :20 (drop "fashion"/model-name staleness → "Stage 1: Scene Image (configured image model)"); `analyze_video` prompt :141 "Analyze this fashion video advertisement" → "Analyze this retail video advertisement" and :156 "garment visibility" → "product visibility"; `generate_scene_image`/`animate_scene_with_veo` docstrings :194-196/:265-268 say `product: dict` → `product: Product`. Do NOT touch legacy-path strings (:63-90, :807-812, :1481, `generate_video_variation` modifiers) — accepted-legacy per working doc.

- [ ] **Step 6: Tests** (add to `tests/unit/test_video_tools.py`):

```python
class TestVariationValidationLoud:
    @pytest.mark.asyncio
    async def test_malformed_variation_returns_structured_error(self, test_db):
        from app.tools.video_tools import generate_video_from_product
        result = await generate_video_from_product(
            campaign_id=1, product_id=1, variation={"model_ethnicity": ["not", "a", "string"]})
        assert result.get("status") == "error"
        assert "Invalid variation parameters" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_with_model_on_beverage_errors(self, test_db):
        from app.tools.video_tools import generate_video_from_product
        from app.database.db import get_product_by_name
        p = get_product_by_name("aurora-cold-brew-330ml")
        result = await generate_video_from_product(
            campaign_id=1, product_id=p.id, variation={"presentation_mode": "with_model"})
        assert result.get("status") == "error"
        assert "with_model" in result.get("error", "")
```

(Both error paths return before any model call — no mocking needed. If campaign/product mismatch guards fire first, create the campaign in the test via `create_campaign` exactly as `tests/unit/test_retail_products.py::TestSelfServiceOnTheFly` does.)

- [ ] **Step 7: Run** `pytest tests/unit/test_video_tools.py -v`, `make test-unit`, `make lint` → green/clean.
- [ ] **Step 8: Commit** `feat: archetype-aware video pipeline, loud variation errors, reference-image surfacing (ws09 Task 4)`

---

### Task 5: Agent instructions, descriptions, APP_DESCRIPTION, campaign description text

**Files:**
- Modify: `app/agent.py` (:124, :182, :291, :402, :502 openers; :128, :147, :151-154, :186, :190, :193-197, :204, :212-213, :217, :227-228, :261, :353, :508, :524-525, :551-552 bodies; :165, :261, :381, :480 description=), `app/config.py:106`, `app/tools/campaign_tools.py:103-111`
- Test: `tests/unit/test_agent_instructions.py` (new), `tests/unit/test_campaign_tools.py`

**Interfaces:**
- Consumes: `presentation_mode` semantics (Tasks 2-4) — the Media instruction must teach it or the LLM never uses it.
- Produces: zero "fashion retail company" strings; non-numeric catalog references.

- [ ] **Step 1: Exact opener replacements** (all five instructions; keep surrounding text flow):
  - `You are the Campaign Management Agent for a fashion retail company.` → `You are the Campaign Management Agent for an in-store retail media network that runs video ad campaigns on store screens.`
  - `You are the Media Generation Agent for a fashion retail company.` → `You are the Media Generation Agent for an in-store retail media network.`
  - `You are the Analytics Agent for a fashion retail company's in-store media network.` → `You are the Analytics Agent for an in-store retail media network.`
  - `You are the Video Review and Activation Agent for a fashion retail company.` → `You are the Video Review and Activation Agent for an in-store retail media network.`
  - `You are the Ad Campaign Management Coordinator for a fashion retail company.` → `You are the Ad Campaign Management Coordinator for an in-store retail media network.`

- [ ] **Step 2: Body edits (rules, applied per research inventory):**
  - Product counts (`:186 "22"`, `:193 "28 pre-loaded products…"`, `:261`, `:524`): replace numeric counts with `the product catalog (fashion plus multi-vertical retail: beverages, QSR menu items, electronics, furniture, home appliances — and any vendor-onboarded product)`.
  - `:190` `fashion metadata (legacy)` → `product metadata (legacy)`.
  - `:193-197` product-library lines: keep `list_products(category="dress")` example, ADD `list_products(category="beverage")` beside it.
  - `:204` `scene-ready first frame with model wearing product` → `scene-ready first frame (a model wearing the product for wearables; a product-centric hero shot for other categories — automatic by product category)`.
  - `:212-213`/`:227-228` variation examples: document the new knob — add a line: `presentation_mode: "auto" (default — decided by product category), "product_only" (no human model), "with_model" (wearables only)`. `:217` ethnicity list gains suffix ` (applies to wearable products only)`.
  - `:353` and Analytics mirror: `Fashion styles performance by geography` → `Product category performance by geography` (same edit lands in maps_tools.py:873 in Task 6 — keep the two strings textually identical).
  - Campaign/Coordinator examples (`:128`, `:147`, `:151-154`, `:508`, `:524-525`, `:551-552`): keep the four pre-loaded fashion campaign names (they ARE the seeded data — factual), but where an example query says only dresses, add one beverage example (`"Create a campaign for the Aurora cold brew at Target Downtown in Austin"`).
  - `description=` params (`:165`, `:261`, `:381`, `:480`): remove "fashion"/"22 products"/"model ethnicity"; e.g. media agent → `Browses the multi-vertical product catalog and generates ad videos (product-centric shots, or human-model shots for wearables) using the two-stage pipeline`.
  - `app/config.py:106` APP_DESCRIPTION → `"Retail ad campaign management agent with video generation for in-store media networks"`.

- [ ] **Step 3: campaign_tools.py:103-111** — close the color-no-style hole:

```python
    if not description:
        style = product.attributes.get("style")
        color = product.attributes.get("color")
        if style:
            in_color = f" in {color}" if color else ""
            description = f"Campaign for {style}{in_color} at {store_name}, {city}."
        else:
            product_title = product.name.replace("-", " ").title()
            description = f"Campaign for {product_title} at {store_name}, {city}."
```

NOTE: for style-present products this changes output ONLY when color is missing (was `in classic`, now no color clause) — all 22 fashion products have both style and color, so seeded-demo descriptions are unchanged. Add test:

```python
    def test_color_without_style_uses_product_name_not_fashion_item(self, fresh_test_db):
        from app.tools.campaign_tools import create_campaign
        from app.models.product import Product
        from app.database.db import insert_product
        p = insert_product(Product(name="crimson-travel-mug", category="drinkware",
                                   description="Insulated mug", image_filename="m.png",
                                   attributes={"color": "crimson"}))
        result = create_campaign(product_id=p.id, store_name="Test Store", city="Austin", state="TX")
        assert result["status"] == "success"
        assert "fashion item" not in result["campaign"]["description"]
        assert "Crimson Travel Mug" in result["campaign"]["description"]
```

- [ ] **Step 4: New `tests/unit/test_agent_instructions.py`** — the anti-drift net:

```python
"""ws09: agent instructions/descriptions must not carry hardcoded fashion framing."""


def test_no_fashion_retail_company_framing():
    import app.agent as agent_module
    import inspect
    source = inspect.getsource(agent_module)
    assert "fashion retail company" not in source

def test_app_description_not_fashion_specific():
    from app.config import APP_DESCRIPTION
    assert "fashion" not in APP_DESCRIPTION.lower()

def test_media_instruction_teaches_presentation_mode():
    from app.agent import MEDIA_AGENT_INSTRUCTION
    assert "presentation_mode" in MEDIA_AGENT_INSTRUCTION

def test_no_stale_product_counts():
    import app.agent as agent_module
    import inspect
    source = inspect.getsource(agent_module)
    assert "22 pre-loaded products" not in source
    assert "28 pre-loaded products" not in source
```

(Adjust the import name if the media instruction constant differs — check `app/agent.py`; if instructions are inline literals rather than module constants, grep the module source as in the first test.)

- [ ] **Step 5: Run** `pytest tests/unit/test_agent_instructions.py tests/unit/test_campaign_tools.py -v`, `make test-unit`, `make lint`. Also run `pytest tests/e2e -v` (agent wiring smoke).
- [ ] **Step 6: Commit** `feat: generalize agent instructions, descriptions, APP_DESCRIPTION, campaign copy (ws09 Task 5)`

---

### Task 6: maps_tools.py generalization

**Files:**
- Modify: `app/tools/maps_tools.py` (:144+:147+:154, :249-292, :761+:773, :873, :1121-1164, :1179, :1206)
- Test: `tests/unit/test_maps_tools.py`

**Interfaces:** self-contained; keep tool names/signatures identical (only defaults, key names, and prompt text change).

- [ ] **Step 1: Edits, exact:**
  - `:144` `business_type: str = "fashion store"` → `business_type: str = "retail store"`; update docstring mentions (:147, :154).
  - `get_location_demographics` (:249-292): rename key `fashion_market_index` → `retail_market_index` in all per-city dicts (:249, :256, :263, :270), the fallback (:292), and the insight text (:283-284: `fashion market` → `retail market`).
  - `:1179` consumer: `demo.get('fashion_market_index', 50)` → `demo.get('retail_market_index', 50)`; `:1206` comment `fashion market index` → `retail market index`.
  - `:761` `Editorial fashion magazine aesthetic` → `Editorial magazine aesthetic`; `:773` `Fashion-forward visual language` → `Design-forward visual language`.
  - `:873` docstring: `category_by_region: Fashion styles performance by geography` → `category_by_region: Product category performance by geography` (identical string to agent.py:353's Task 5 edit).
  - Infographic block (:1121-1164): `:1125` `- {cat.title()} Fashion:` → `- {cat.title()}:`; `:1129` `which fashion categories` → `which product categories`; `:1132` `Theme: Fashion retail performance by location` → `Theme: Retail performance by location`; `:1139-1143` icon lines → `product category icons per city`; `:1153-1154` hardcoded insights → `- "Top categories vary by region"` / `- "Performance concentrated in flagship locations"`; `:1158` `Fashion-forward, editorial aesthetic` → `Clean, editorial aesthetic`; `:1161` `category icons (dress, blazer, sweater)` → `simple product category icons`; `:1164` `visualization for fashion retail strategy` → `visualization for retail strategy`.

- [ ] **Step 2: Tests** — in `tests/unit/test_maps_tools.py` add:

```python
def test_demographics_uses_retail_market_index(test_db):
    from app.tools.maps_tools import get_location_demographics
    result = get_location_demographics(city="Austin", state="TX")
    demo = result.get("demographics", result)
    flat = str(result)
    assert "fashion_market_index" not in flat
    assert "retail_market_index" in flat
```

(Match the actual return shape of the existing `test_get_location_demographics` at :316 — mirror its access pattern.) Existing `test_search_nearby_stores_with_mock` passes `business_type` explicitly, unaffected.

- [ ] **Step 3: Run** `pytest tests/unit/test_maps_tools.py -v`, `make test-unit`, `make lint`.
- [ ] **Step 4: Commit** `feat: generalize maps tools defaults, demographics index, infographic prompts (ws09 Task 6)`

---

### Task 7: Integration evals — narrow the xfail, add non-fashion cases

**Files:**
- Modify: `tests/integration/test_agents.py` (:73-75, :90-91, :106-107, :122-123, :138-139, :157-158), `tests/integration/eval_sets/media_agent.test.json`, `tests/integration/eval_sets/campaign_agent.test.json`
- Test: this task IS tests; verified by deliberate-break.

**Interfaces:** none downstream; unblocks the phase doc's step 7 (kickoff DISCOVERY 3: the ws02 narrowing never happened).

- [ ] **Step 1: Narrow the catch.** Add module-level helper in `test_agents.py`:

```python
_INFRA_MARKERS = (
    "credential", "permission denied", "quota", "resource_exhausted", "429",
    "unavailable", "503", "deadline", "connection", "getaddrinfo",
)

def _xfail_if_infrastructure(e: Exception):
    """xfail ONLY on infrastructure errors; real eval failures must fail the test."""
    msg = str(e).lower()
    if isinstance(e, (ConnectionError, TimeoutError)) or any(m in msg for m in _INFRA_MARKERS):
        pytest.xfail(f"Integration infrastructure unavailable: {e}")
    raise e
```

Replace all six `except Exception as e: pytest.xfail(f"Integration test failed (may need config): {e}")` blocks with `except AssertionError: raise` + `except Exception as e: _xfail_if_infrastructure(e)` (assertion failures from AgentEvaluator propagate; keep the existing loud-ImportError handling from ws01 untouched).

- [ ] **Step 2: Add non-fashion cases to EXISTING eval-set files** (auto-covered by the existing per-agent tests; new files would need new test functions — research surprise #7). Copy the exact JSON schema of a neighboring case in each file:
  - `media_agent.test.json`: new case `list-products-beverage` — query `List the beverage products`, expected tool `list_products` with `{"category": "beverage"}`, reference response mentioning Aurora Cold Brew.
  - `campaign_agent.test.json`: new case `create-campaign-beverage` — query `Create a campaign for the Aurora cold brew at Target Downtown in Austin, Texas`, expected tool `create_campaign`, reference response confirming creation (category always-on).

- [ ] **Step 3: Verify the suite can now fail:** temporarily corrupt one expected tool name in `media_agent.test.json` (e.g. `list_productsX`), run `pytest tests/integration/test_agents.py -k media -v` with `app/.env` sourced → must FAIL (not xfail). Revert the corruption. Then run `make test-integration` → all pass for real.
- [ ] **Step 4: Commit** `test: narrow integration xfail to infrastructure errors + non-fashion eval cases (ws09 Task 7)`

---

### Task 8: Demo scenario F5.2 + phase-doc bookkeeping

**Files:**
- Modify: `docs/demo-scenarios/fashion.md` (append Scene F5.2 under Scenario F5), `.docs/version2-plan/09-prompt-and-agent-generalization.md` (mark folded xfail item done via provenance note), `SETUP_INSTRUCTIONS.md` (only if any setup-facing behavior changed — expected: none)

**Interfaces:** consumed by verifying-with-demo-scenarios (F1 scenes 1-2 regression + F5.1 + new F5.2, sequential verifiers).

- [ ] **Step 1: Append Scene F5.2 to `docs/demo-scenarios/fashion.md`:**

```markdown
### Scene F5.2 — non-fashion video generation (workstream 09)

**Query:** "Generate a video for the Aurora cold brew using a studio setting"

**Expected tool calls:**
- `generate_video_from_product` or `generate_video_with_variation` for the
  aurora-cold-brew-330ml product (campaign resolved from F5.1's campaign or
  created on the fly). Stage 1 + Stage 2 run (~1-4 min).

**Pass criteria (check the trace, not prose):**
- The scene/creative prompt visible in the trace (or the tool's debug output)
  contains NONE of: "fashion", "garment", "wearing", "model wearing",
  "she is" (case-insensitive) — it must read as a product-centric hero shot
  (condensation/appetite cues for the beverage archetype).
- The tool response surfaces `reference_image_used: false` with a warning that
  no product image exists (retail SKUs ship without images until Phase 14a/15)
  — generation still succeeds from the text description.
- Video registered with status generated/pending review; filename derives from
  a product-centric variation name (e.g. `beverage-studio-elegant`), NOT an
  ethnicity-prefixed name.
- FAIL if: a human model appears in the prompt text, any exception in the
  trace, or the old fashion preamble ("model wearing this exact garment")
  appears anywhere.
```

- [ ] **Step 2:** Add a one-line provenance note under the 09 doc's step 7 that the xfail narrowing landed in this workstream (closing DISCOVERY 3's loop).
- [ ] **Step 3:** `make test-unit && make test-e2e` green. Commit `docs: add Scene F5.2 (non-fashion video generation) + 09 provenance (ws09 Task 8)`

---

## Execution notes (controller)

- **Order matters:** Task 1 MUST run first (goldens from unmodified code). Tasks 2→3→4 are sequential (each consumes the previous interface). Tasks 5 and 6 are independent of each other (after 4). Task 7 independent after 5 (instruction text affects eval routing). Task 8 last.
- Per the owner's instruction, execution ends with a **stabilize loop-until-green** phase: run full `make test` (and `make test-integration` with env sourced), fix, repeat until clean — max 4 rounds, then escalate.
- Verification (verifying-with-demo-scenarios): F1 scenes 1-2 (fashion regression), F5.1 (ws08 regression), new F5.2 — sequential verifiers, port 8501, fresh DB (`make reset-db` first).

## Self-review (writing-plans checklist)

- Spec coverage: doc steps 1-7 + all three kickoff discoveries + owner's Option B + test-update-and-run instruction → Tasks 1-8 + stabilize. Legacy strings and PRESET_VARIATIONS explicitly out of scope per working doc.
- Placeholder scan: none — every step carries code, exact strings, or exact replacement rules with file:line anchors.
- Type consistency: `resolve_archetype(product, variation) -> str` used identically in Tasks 3/4; `presentation_mode: Optional[str] = None` consistent across Tasks 2/3/4/5; archetype constant names consistent.
