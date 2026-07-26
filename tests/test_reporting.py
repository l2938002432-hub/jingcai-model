import unittest
from datetime import UTC, datetime
import json
import re

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

    def test_estimated_cutoff_is_explicit(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC), model_state="LIMITED_LIVE",
            data_fresh=True, candidates=[{
                "label": "A-B", "play": "主胜", "probability": 0.6,
                "conservative_ev": 0.1, "sale_cutoff": "2026-07-22T12:00:00+08:00",
                "sale_cutoff_estimated": True,
            }],
        )
        self.assertIn("估算，非官方停售时间", report)

    def test_daily_report_maps_internal_market_to_chinese(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC), model_state="LIMITED_LIVE",
            data_fresh=True, candidates=[{
                "match_id": "1", "label": "主队 vs 客队", "play": "match_result:home",
                "market": "match_result", "outcome": "home", "probability": 0.6,
                "market_probability": 0.5, "decimal_odds": 2.1, "conservative_ev": 0.1,
            }],
        )
        self.assertIn("胜平负 · 主胜", report)
        self.assertNotIn(">match_result:home<", report)

    def test_daily_report_has_responsive_cards_and_budget_calculator(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC), model_state="PAPER_ONLY",
            data_fresh=True, candidates=[{
                "match_id": "1", "label": "主队 vs 客队", "market": "match_result",
                "outcome": "home", "probability": 0.6, "decimal_odds": 2.1,
                "conservative_ev": 0.1,
            }],
        )
        for text in ("竞彩决策驾驶舱", "模拟总预算", "实际模拟投入", "全错最大损失", "match-card"):
            self.assertIn(text, report)
        self.assertIn("@media(max-width:760px)", report)
        self.assertIn('id="budget"', report)
        self.assertIn("金额只在当前页面内计算，不保存、不上传", report)

    def test_candidate_json_cannot_break_out_of_script(self) -> None:
        hostile = "</script><script>alert(1)</script>"
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC), model_state="PAPER_ONLY",
            data_fresh=True, candidates=[{
                "match_id": "1", "label": hostile, "market": "match_result",
                "outcome": "home", "probability": 0.6, "decimal_odds": 2.1,
                "conservative_ev": 0.1,
            }],
        )
        self.assertNotIn("<script>alert(1)</script>", report)
        match = re.search(r'<script id="candidate-data" type="application/json">(.*?)</script>', report, re.S)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        self.assertEqual(hostile, payload[0]["label"])
        self.assertNotIn("</script>", match.group(1))

    def test_empty_report_has_no_advice_and_explains_no_bet(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC),
            model_state="LIVE", data_fresh=True, candidates=[],
        )
        self.assertIn("今日无符合标准的正式投注建议", report)
        self.assertIn("不投注也是正式结论", report)
        self.assertIn("当前没有带参考奖金的候选", report)

    def test_report_contains_historical_report_warning(self) -> None:
        report = render_daily_report(
            generated_at=datetime(2026, 7, 22, tzinfo=UTC),
            model_state="PAPER_ONLY", data_fresh=True, candidates=[],
        )
        self.assertIn('id="history-alert"', report)
        self.assertIn("你正在查看历史报告", report)


if __name__ == "__main__":
    unittest.main()
