"""APP_MODE → audience-source selection; Phase 6's fail-closed guard, built."""

import pytest

import app.config
from app.audience import (
    get_audience_datasource,
    register_datasource_for_tests,
    reset_audience_datasource,
)
from app.audience.synthetic import SyntheticAudienceDataSource
from app.config import AppMode


@pytest.fixture(autouse=True)
def _reset():
    reset_audience_datasource()
    yield
    reset_audience_datasource()


class TestDemoMode:
    def test_demo_resolves_to_synthetic(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        assert isinstance(get_audience_datasource(), SyntheticAudienceDataSource)

    def test_singleton_same_instance_across_calls(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        assert get_audience_datasource() is get_audience_datasource()


class TestConnectedFailsClosed:
    def test_connected_raises_specific_error(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)
        with pytest.raises(RuntimeError) as exc:
            get_audience_datasource()
        msg = str(exc.value)
        # Specific, actionable, honest — the Phase 6 deferred guard contract.
        assert "APP_MODE" in msg and "connected" in msg
        assert "Phase 11b" in msg
        assert "APP_MODE=demo" in msg

    def test_no_silent_fallback_to_demo(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)
        with pytest.raises(RuntimeError):
            get_audience_datasource()
        # And it stays closed on retry — no cached demo source snuck in.
        with pytest.raises(RuntimeError):
            get_audience_datasource()


class TestTestSeam:
    def test_override_bypasses_mode_resolution(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.CONNECTED)

        class _Fake(SyntheticAudienceDataSource):
            pass

        fake = _Fake()
        register_datasource_for_tests(fake)
        assert get_audience_datasource() is fake  # even in connected mode

    def test_reset_clears_override_and_singleton(self, monkeypatch):
        monkeypatch.setattr(app.config, "APP_MODE", AppMode.DEMO)
        first = get_audience_datasource()
        register_datasource_for_tests(SyntheticAudienceDataSource())
        reset_audience_datasource()
        assert get_audience_datasource() is not first  # fresh singleton
