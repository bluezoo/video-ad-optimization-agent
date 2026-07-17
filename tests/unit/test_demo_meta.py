"""Tests for the demo_meta table and demo anchor-date helpers."""

from datetime import datetime, timezone

from app.database.db import (
    get_db_cursor,
    get_demo_anchor_date,
    set_demo_anchor_date,
)


class TestDemoAnchor:
    def test_first_read_seeds_todays_utc_date(self, fresh_test_db):
        with get_db_cursor() as cursor:
            anchor = get_demo_anchor_date(cursor)
        assert anchor == datetime.now(timezone.utc).date().isoformat()

    def test_anchor_is_stable_across_reads(self, fresh_test_db):
        with get_db_cursor() as cursor:
            first = get_demo_anchor_date(cursor)
        with get_db_cursor() as cursor:
            second = get_demo_anchor_date(cursor)
        assert first == second

    def test_set_overwrites(self, fresh_test_db):
        with get_db_cursor() as cursor:
            set_demo_anchor_date(cursor, "2026-01-15")
        with get_db_cursor() as cursor:
            assert get_demo_anchor_date(cursor) == "2026-01-15"
        with get_db_cursor() as cursor:
            set_demo_anchor_date(cursor, "2026-02-01")
        with get_db_cursor() as cursor:
            assert get_demo_anchor_date(cursor) == "2026-02-01"
