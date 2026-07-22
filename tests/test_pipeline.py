import math
import unittest
from datetime import UTC, datetime, timedelta

from jingcai.pipeline import predict_all_markets, walk_forward_1x2


def synthetic_matches(count: int = 24) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    teams = ("A", "B", "C", "D")
    rows = []
    for index in range(count):
        home = teams[index % 4]
        away = teams[(index + 1 + index // 4) % 4]
        if home == away:
            away = teams[(index + 2) % 4]
        rows.append(
            {
                "kickoff_utc": (start + timedelta(days=index)).isoformat(),
                "home_team": home,
                "away_team": away,
                "home_goals": (index * 3) % 4,
                "away_goals": (index * 2 + 1) % 3,
            }
        )
    return rows


class PipelineTests(unittest.TestCase):
    def test_walk_forward_compares_model_and_baseline_without_roi_claim(self) -> None:
        result = walk_forward_1x2(synthetic_matches(), min_train=12)
        self.assertEqual(12, result.evaluated_matches)
        self.assertTrue(math.isfinite(result.model_log_loss))
        self.assertTrue(math.isfinite(result.baseline_log_loss))
        self.assertIn("UNAVAILABLE", result.roi_status)

    def test_predict_all_five_markets(self) -> None:
        result = predict_all_markets(synthetic_matches(), home_team="A", away_team="B", handicap=-1)
        for market in ("match_result", "handicap_result", "total_goals", "correct_score", "half_full"):
            self.assertAlmostEqual(1.0, sum(result[market].values()), places=9)
        self.assertEqual("RESEARCH", result["state"])
        self.assertEqual(9, len(result["half_full"]))


if __name__ == "__main__":
    unittest.main()
