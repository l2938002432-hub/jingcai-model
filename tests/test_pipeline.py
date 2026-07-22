import math
import unittest
from datetime import UTC, datetime, timedelta

from jingcai.pipeline import build_paper_candidates, predict_all_markets, walk_forward_1x2


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

    def test_paper_candidates_choose_positive_conservative_ev_only(self) -> None:
        fixtures = [
            {
                "match_id": "m1",
                "home_team": "A",
                "away_team": "B",
                "handicap": 0,
                "odds_as_of": "2026-07-22T10:00:00+00:00",
                "sale_cutoff": "2026-07-22T12:00:00+00:00",
                "odds": {"match_result": {"home": 10.0, "draw": 10.0, "away": 10.0}},
            }
        ]
        candidates = build_paper_candidates(
            synthetic_matches(),
            fixtures,
            safety_margin=0.03,
            prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
        )
        self.assertEqual(1, len(candidates))
        self.assertGreater(candidates[0]["conservative_ev"], 0)
        self.assertIn("market_probability", candidates[0])

    def test_paper_candidates_allow_empty_best_action(self) -> None:
        fixtures = [
            {
                "match_id": "m1",
                "home_team": "A",
                "away_team": "B",
                "odds_as_of": "2026-07-22T10:00:00+00:00",
                "sale_cutoff": "2026-07-22T12:00:00+00:00",
                "odds": {"match_result": {"home": 1.01, "draw": 1.01, "away": 1.01}},
            }
        ]
        self.assertEqual(
            [],
            build_paper_candidates(
                synthetic_matches(),
                fixtures,
                prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
            ),
        )

    def test_paper_candidates_reject_stale_or_future_information(self) -> None:
        fixture = {
            "match_id": "m1",
            "home_team": "A",
            "away_team": "B",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 2.0, "draw": 3.0, "away": 4.0}},
        }
        self.assertEqual(
            [],
            build_paper_candidates(
                synthetic_matches(), [fixture], prediction_time=datetime(2026, 7, 22, 13, tzinfo=UTC)
            ),
        )
        future = dict(fixture, odds_as_of="2026-07-22T11:30:00+00:00")
        with self.assertRaisesRegex(ValueError, "odds_as_of"):
            build_paper_candidates(
                synthetic_matches(), [future], prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC)
            )


if __name__ == "__main__":
    unittest.main()
