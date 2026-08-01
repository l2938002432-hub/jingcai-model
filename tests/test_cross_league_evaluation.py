import unittest

from jingcai.cross_league_evaluation import evaluate_cross_league_1x2


def record(index, *, competition="A", coverage=1.0, kickoff="2026-01-01T12:00:00+00:00", predicted="2026-01-01T10:00:00+00:00"):
    actual = ("home", "draw", "away")[index % 3]
    probabilities = {"home": 0.2, "draw": 0.3, "away": 0.5}
    return {
        "prediction_id": f"p-{index}", "kickoff_utc": kickoff, "predicted_at": predicted,
        "competition_code": competition, "data_coverage": coverage,
        "probabilities": probabilities, "actual": actual,
    }


class CrossLeagueEvaluationTests(unittest.TestCase):
    def test_reports_metrics_by_competition_and_data_coverage(self):
        rows = [
            record(0, competition="BRA", coverage=1.0),
            record(1, competition="BRA", coverage=0.7),
            record(2, competition="NOR", coverage=0.2, kickoff="2026-01-02T12:00:00+00:00"),
        ]
        report = evaluate_cross_league_1x2(rows, input_manifest_sha256="a" * 64)
        self.assertEqual(3, report.overall.sample_count)
        self.assertEqual(2, report.overall.kickoff_batches)
        self.assertEqual({"BRA", "NOR"}, set(report.by_competition))
        self.assertEqual({"complete", "partial", "sparse"}, set(report.by_data_coverage))
        self.assertIn("不得推断", report.market_comparison["reason"])
        self.assertEqual("RESEARCH_ONLY", report.admission_status)
        self.assertIn("3 场", report.confidence_note)

    def test_rejects_post_kickoff_forecasts(self):
        with self.assertRaisesRegex(ValueError, "after kickoff"):
            evaluate_cross_league_1x2([record(0, predicted="2026-01-01T13:00:00+00:00")])

    def test_rejects_missing_or_incomplete_probability_distribution(self):
        row = record(0)
        row["probabilities"] = {"home": 1.0}
        with self.assertRaisesRegex(ValueError, "exactly home"):
            evaluate_cross_league_1x2([row])

    def test_serialised_report_keeps_market_unavailable_status(self):
        output = evaluate_cross_league_1x2([record(0)]).to_dict()
        self.assertEqual("UNAVAILABLE", output["market_comparison"]["status"])
        self.assertIn("top_label_ece", output["overall"])


if __name__ == "__main__":
    unittest.main()
