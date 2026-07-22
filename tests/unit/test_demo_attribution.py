"""Tests for the Phase 10 ad-play attribution join (replaces test_demo_derive.py)."""

from datetime import date, datetime, timedelta

from app.demo_data.attribution import (
    expand_ad_plays,
    screens_for_campaign,
    slot_budget,
)

CID = 9001
D_FROM = date(2026, 6, 1)
D_TO = date(2026, 6, 7)


def _open_windows(video_ids, screens, active_from_date=D_FROM):
    return [
        {
            "video_id": vid,
            "screen_id": sid,
            "active_from": datetime.combine(active_from_date, datetime.min.time()),
            "active_to": None,
        }
        for vid in video_ids
        for sid in screens
    ]


class TestScreensRoster:
    def test_two_to_three_screens_decoupled_from_campaign_id(self):
        for cid in (1, 2, 3, 9001, 424242):
            screens = screens_for_campaign(cid)
            assert 2 <= len(screens) <= 3
            assert cid not in screens  # the 1:1 campaign-as-screen proxy is dead
            assert len(set(screens)) == len(screens)
            assert screens == screens_for_campaign(cid)  # deterministic

    def test_rosters_vary_in_size_across_campaigns(self):
        sizes = {len(screens_for_campaign(cid)) for cid in range(1, 40)}
        assert sizes == {2, 3}


class TestPlaySchedule:
    def test_slot_budget_band_and_determinism(self):
        for vid in (101, 102, 999):
            k = slot_budget(CID, vid, screens_for_campaign(CID)[0])
            assert 10 <= k <= 22
            assert k == slot_budget(CID, vid, screens_for_campaign(CID)[0])

    def test_plays_are_15min_aligned_within_open_hours(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_FROM)
        assert plays, "an open window must produce plays"
        for p in plays:
            assert p.ad_campaign_id == CID
            assert p.video_id == 101
            assert p.screen_id in screens
            assert p.end - p.start == timedelta(minutes=15)
            assert p.start.minute % 15 == 0
            assert 9 <= p.start.hour < 21

    def test_daily_play_count_matches_slot_budget(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_FROM)
        per_screen = {}
        for p in plays:
            per_screen[p.screen_id] = per_screen.get(p.screen_id, 0) + 1
        for sid in screens:
            assert per_screen[sid] == slot_budget(CID, 101, sid)

    def test_no_duplicate_slots_per_video_screen_day(self):
        screens = screens_for_campaign(CID)
        plays = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_TO)
        keys = [(p.screen_id, p.start) for p in plays]
        assert len(keys) == len(set(keys))

    def test_window_clamps_days(self):
        """Plays exist only on days the window covers."""
        screens = screens_for_campaign(CID)
        w = [
            {
                "video_id": 101,
                "screen_id": screens[0],
                "active_from": datetime.combine(D_FROM + timedelta(days=2), datetime.min.time()),
                "active_to": datetime.combine(D_FROM + timedelta(days=4), datetime.min.time()),
            }
        ]
        plays = expand_ad_plays(CID, w, D_FROM, D_TO)
        days = {p.start.date() for p in plays}
        assert days == {D_FROM + timedelta(days=2), D_FROM + timedelta(days=3), D_FROM + timedelta(days=4)}

    def test_schedule_is_absolute_per_video(self):
        """Adding a second video's windows never changes the first video's plays."""
        screens = screens_for_campaign(CID)
        solo = expand_ad_plays(CID, _open_windows([101], screens), D_FROM, D_TO)
        both = [
            p
            for p in expand_ad_plays(CID, _open_windows([101, 102], screens), D_FROM, D_TO)
            if p.video_id == 101
        ]
        assert solo == both
