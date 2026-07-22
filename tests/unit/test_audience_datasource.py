"""AudienceDataSource ABC: structure + reusable conformance battery (Phase 11a).

The battery (AudienceDataSourceContract) is deliberately subclass-pluggable:
Phase 11b's cached/live conformers add their own TestXxxConformance class
with a make_source() override and inherit every check for free.
"""

import inspect
from datetime import date, timedelta

import pytest

from app.audience.datasource import AudienceDataSource
from app.models.attribution import BlueZooVisitInterval

D_FROM = date(2026, 6, 1)
D_TO = date(2026, 6, 3)


class TestAbstractInterface:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            AudienceDataSource()

    def test_get_visit_intervals_is_abstract_and_keyword_only(self):
        assert "get_visit_intervals" in AudienceDataSource.__abstractmethods__
        sig = inspect.signature(AudienceDataSource.get_visit_intervals)
        params = list(sig.parameters.values())[1:]  # drop self
        assert [p.name for p in params] == ["screen_ids", "date_from", "date_to"]
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)


class AudienceDataSourceContract:
    """Conformance battery. Subclasses provide make_source() and screen ids."""

    # 2-3 screens of one demo campaign (ws10 convention: cid*100+k).
    SCREEN_IDS: list[int] = []

    def make_source(self) -> AudienceDataSource:
        raise NotImplementedError

    def test_returns_dto_instances(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        assert intervals, "expected at least one interval for a live demo screen"
        assert all(isinstance(iv, BlueZooVisitInterval) for iv in intervals)

    def test_respects_screen_filter(self):
        one = self.SCREEN_IDS[:1]
        intervals = self.make_source().get_visit_intervals(
            screen_ids=one, date_from=D_FROM, date_to=D_TO
        )
        assert intervals and {iv.screen_id for iv in intervals} == set(one)

    def test_respects_date_window(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_FROM
        )
        assert intervals
        assert {iv.timestamp.date() for iv in intervals} == {D_FROM}

    def test_deterministic_across_calls_and_instances(self):
        a = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        b = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS, date_from=D_FROM, date_to=D_TO
        )
        assert a == b

    def test_slot_grain_is_15_minutes(self):
        intervals = self.make_source().get_visit_intervals(
            screen_ids=self.SCREEN_IDS[:1], date_from=D_FROM, date_to=D_FROM
        )
        stamps = sorted(iv.timestamp for iv in intervals)
        assert len(stamps) == 48  # 09:00-21:00 at 15-min grain (seed.py contract)
        deltas = {b - a for a, b in zip(stamps, stamps[1:], strict=False)}
        assert deltas == {timedelta(minutes=15)}

    def test_unknown_screen_returns_empty_not_error(self):
        # A sensor the source doesn't know = no data, like a real sensor API.
        intervals = self.make_source().get_visit_intervals(
            screen_ids=[999_999_99], date_from=D_FROM, date_to=D_TO
        )
        assert intervals == []
