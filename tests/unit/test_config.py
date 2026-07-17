"""Unit tests for media-model configuration (Phase 1: model currency fix)."""

import importlib

import pytest

import app.config as config_module


@pytest.fixture(autouse=True)
def _reload_config_after_test(monkeypatch):
    """Each test reloads app.config; re-reload under the restored env afterwards."""
    yield
    monkeypatch.undo()
    importlib.reload(config_module)


def test_media_model_defaults_are_ga_ids(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_GENERATION_MODEL", raising=False)
    monkeypatch.delenv("VIDEO_GEN_MODEL", raising=False)
    cfg = importlib.reload(config_module)
    assert cfg.MODEL == "gemini-3.5-flash"
    assert cfg.IMAGE_GENERATION == "gemini-3-pro-image"
    assert cfg.VIDEO_GEN_MODEL == "veo-3.1-generate-001"


def test_media_models_are_env_overridable(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "fake-agent-model-id")
    monkeypatch.setenv("IMAGE_GENERATION_MODEL", "fake-image-preview-id")
    monkeypatch.setenv("VIDEO_GEN_MODEL", "fake-video-preview-id")
    cfg = importlib.reload(config_module)
    assert cfg.MODEL == "fake-agent-model-id"
    assert cfg.IMAGE_GENERATION == "fake-image-preview-id"
    assert cfg.VIDEO_GEN_MODEL == "fake-video-preview-id"


def test_old_veo_model_name_is_gone():
    cfg = importlib.reload(config_module)
    assert not hasattr(cfg, "VEO_MODEL")


class TestCampaignCategoriesParity:
    """config.CAMPAIGN_CATEGORIES must stay in sync with the CHECK
    constraint on campaigns.category (app/database/db.py — source of truth)."""

    def test_all_config_categories_accepted_by_db(self, test_db):
        from app import config
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            for cat in config.CAMPAIGN_CATEGORIES:
                # Raises sqlite3.IntegrityError if cat violates the CHECK
                cursor.execute(
                    "INSERT INTO campaigns (name, city, state, category) "
                    "VALUES (?, ?, ?, ?)",
                    (f"parity-{cat}", "Los Angeles", "CA", cat),
                )

    def test_holiday_category_present(self):
        from app import config

        assert "holiday" in config.CAMPAIGN_CATEGORIES
