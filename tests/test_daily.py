import unittest
from datetime import UTC, datetime, timedelta

from jingcai.daily import DailyLiveError, build_live_candidates, canonicalize_teams, parse_official_update
from tests.test_pipeline import synthetic_matches


class DailyLiveTests(unittest.TestCase):
    def test_parses_naive_official_time_as_china_time(self) -> None:
        payload = {"value": {"lastUpdateTime": "2026-07-22 20:30:00"}}
        self.assertEqual("2026-07-22T12:30:00+00:00", parse_official_update(payload).isoformat())

    def test_stale_snapshot_is_strictly_rejected(self) -> None:
        now = datetime(2026, 7, 22, 13, tzinfo=UTC)
        with self.assertRaisesRegex(DailyLiveError, "过期"):
            build_live_candidates(
                synthetic_matches(), [], source_as_of=now - timedelta(minutes=31), now=now
            )

    def test_all_unknown_teams_reject_report(self) -> None:
        now = datetime(2026, 7, 22, 11, tzinfo=UTC)
        fixture = {
            "match_id": "x", "home_team": "A", "away_team": "未知队",
            "odds_as_of": now.isoformat(),
            "sale_cutoff": (now + timedelta(hours=1)).isoformat(),
            "sale_cutoff_estimated": True,
            "odds": {"match_result": {"home": 2.0, "draw": 3.0, "away": 4.0}},
        }
        with self.assertRaisesRegex(DailyLiveError, "缺少可信历史"):
            build_live_candidates(synthetic_matches(), [fixture], source_as_of=now, now=now)

    def test_aliases_canonicalize_history_and_fixture(self) -> None:
        history, fixtures = canonicalize_teams(
            [{"home_team": "Ham-Kam", "away_team": "Viking"}],
            [{"home_team": "汉坎", "away_team": "维京"}],
            {"HamKam": ["Ham-Kam", "汉坎"], "Viking": ["维京"]},
        )
        self.assertEqual(history[0]["home_team"], fixtures[0]["home_team"])
        self.assertEqual(history[0]["away_team"], fixtures[0]["away_team"])
