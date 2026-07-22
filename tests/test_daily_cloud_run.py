import unittest
from scripts.daily_cloud_run import format_summary


class DailyCloudRunTests(unittest.TestCase):
    def test_summary_counts_complete_markets_and_limits_output(self) -> None:
        fixtures = [{"match_num": f"周三{i:03d}", "home_team": "主队", "away_team": "客队", "kickoff": "2026-07-22T19:30:00+08:00", "odds": {str(j): {} for j in range(5)}} for i in range(16)]
        summary = format_summary(fixtures)
        self.assertIn("在售比赛：16 场", summary)
        self.assertIn("五玩法完整：16 场", summary)
        self.assertIn("另有 1 场", summary)
        self.assertIn("不保证中奖或盈利", summary)


if __name__ == "__main__":
    unittest.main()
