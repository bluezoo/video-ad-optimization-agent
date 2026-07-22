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
