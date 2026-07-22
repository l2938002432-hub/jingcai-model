import unittest

from jingcai.market_validation import validate_markets


def row(date, home, away, matrix, **extra):
    return {"date": date, "home_goals": home, "away_goals": away, "score_matrix": matrix, **extra}


class MarketValidationTests(unittest.TestCase):
    def test_scores_four_markets_and_marks_half_full_unavailable(self):
        rows = [
            row("2024-01-01", 1, 0, {(1, 0): 0.8, (0, 0): 0.1, (0, 1): 0.1}, handicap=-1),
            row("2024-01-02", 0, 1, {(0, 1): 0.8, (0, 0): 0.1, (1, 0): 0.1}, handicap=1),
        ]
        result = validate_markets(rows)
        for market in ("match_result", "handicap_result", "total_goals", "correct_score"):
            self.assertTrue(result[market].available)
            self.assertEqual(result[market].sample_count, 2)
            self.assertIsNotNone(result[market].improvement)
        self.assertFalse(result["half_full"].available)
        self.assertIn("must not", result["half_full"].reason)

    def test_half_full_requires_real_label_and_explicit_forecast(self):
        probabilities = {f"{half}_{full}": 1 / 9 for half in ("home", "draw", "away") for full in ("home", "draw", "away")}
        result = validate_markets([
            row("2024-01-01", 2, 0, {(2, 0): 1.0}, half_home_goals=1, half_away_goals=0,
                half_full_probabilities=probabilities)
        ])
        self.assertTrue(result["half_full"].available)
        self.assertEqual(result["half_full"].sample_count, 1)

    def test_same_timestamp_results_do_not_leak_into_baseline(self):
        matrix = {(1, 0): 1.0}
        result = validate_markets([
            row("2024-01-01", 1, 0, matrix),
            row("2024-01-01", 1, 0, matrix),
        ])
        # Both use the initial uniform 1X2 baseline, not 1/2 then 2/3.
        self.assertAlmostEqual(result["match_result"].baseline_log_loss, 1.0986122886681098)

    def test_handicap_is_unavailable_without_historical_line(self):
        result = validate_markets([row("2024-01-01", 1, 0, {(1, 0): 1.0})])
        self.assertFalse(result["handicap_result"].available)

    def test_baseline_can_be_seeded_only_with_prior_results(self):
        history = [{"home_goals": 1, "away_goals": 0} for _ in range(8)]
        result = validate_markets(
            [row("2024-01-02", 1, 0, {(1, 0): 1.0})], baseline_history=history
        )
        self.assertLess(result["match_result"].baseline_log_loss, 1.0986122886681098)

    def test_rejects_non_positive_smoothing(self):
        with self.assertRaises(ValueError):
            validate_markets([], smoothing=0)


if __name__ == "__main__":
    unittest.main()
