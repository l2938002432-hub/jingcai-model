import unittest
from datetime import UTC, datetime

from jingcai.reporting import render_daily_report


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


if __name__ == "__main__":
    unittest.main()
