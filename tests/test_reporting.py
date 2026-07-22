import unittest
from datetime import UTC, datetime

from jingcai.reporting import render_daily_report, render_probability_report


class ReportingTests(unittest.TestCase):
    def test_paper_only_never_labels_candidate_as_live(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC),
            model_state="PAPER_ONLY",
            data_fresh=True,
            candidates=[{"label": "A-B", "play": "主胜", "probability": 0.6, "conservative_ev": 0.1}],
        )
        self.assertIn("观察/模拟", report)
        self.assertNotIn("<td>候选</td>", report)

    def test_stale_data_hides_recommendation(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC),
            model_state="LIVE",
            data_fresh=False,
            candidates=[{"label": "A-B", "play": "主胜", "probability": 0.6, "conservative_ev": 0.1}],
        )
        self.assertIn("数据过期", report)
        self.assertIn("观察/模拟", report)

    def test_probability_report_contains_five_markets_and_research_warning(self) -> None:
        report = render_probability_report(
            {
                "home_team": "A",
                "away_team": "B",
                "state": "RESEARCH",
                "model": "test",
                "generated_at": "now",
                "handicap": -1,
                "match_result": {"home": 0.5, "draw": 0.3, "away": 0.2},
                "handicap_result": {"home": 0.3, "draw": 0.3, "away": 0.4},
                "total_goals": {"2": 1.0},
                "correct_score": {"1:1": 1.0},
                "half_full": {"DD": 1.0},
            }
        )
        for title in ("胜平负", "让球胜平负", "总进球", "比分", "半全场"):
            self.assertIn(title, report)
        self.assertIn("不构成正式投注建议", report)


if __name__ == "__main__":
    unittest.main()
