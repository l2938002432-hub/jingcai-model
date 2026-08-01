import math
import unittest

from jingcai.market_baseline import ONE_X_TWO_OUTCOMES, prematch_1x2_market_baseline


class Prematch1X2MarketBaselineTests(unittest.TestCase):
    def test_removes_overround_proportionally_and_preserves_diagnostics(self):
        baseline = prematch_1x2_market_baseline({"home": 2.0, "draw": 3.0, "away": 4.0})

        self.assertEqual(ONE_X_TWO_OUTCOMES, tuple(baseline.probabilities))
        self.assertAlmostEqual(13 / 12, baseline.diagnostics.implied_probability_total)
        self.assertAlmostEqual(1 / 12, baseline.diagnostics.margin)
        self.assertEqual("overround", baseline.diagnostics.price_shape)
        self.assertEqual("multiplicative", baseline.diagnostics.normalization)
        self.assertAlmostEqual(6 / 13, baseline.probabilities["home"])
        self.assertAlmostEqual(4 / 13, baseline.probabilities["draw"])
        self.assertAlmostEqual(3 / 13, baseline.probabilities["away"])
        self.assertAlmostEqual(1.0, sum(baseline.probabilities.values()))

    def test_marks_underround_without_mislabeling_it_as_margin(self):
        baseline = prematch_1x2_market_baseline({"home": 3.5, "draw": 4.0, "away": 4.5})

        self.assertLess(baseline.diagnostics.margin, 0)
        self.assertEqual("underround", baseline.diagnostics.price_shape)
        self.assertAlmostEqual(1.0, sum(baseline.probabilities.values()))

    def test_rejects_missing_unknown_and_invalid_prices(self):
        invalid_inputs = (
            {"home": 2.0, "draw": 3.0},
            {"home": 2.0, "draw": 3.0, "away": 4.0, "other": 8.0},
            {"home": 1.0, "draw": 3.0, "away": 4.0},
            {"home": math.inf, "draw": 3.0, "away": 4.0},
            {"home": True, "draw": 3.0, "away": 4.0},
        )
        for decimal_odds in invalid_inputs:
            with self.subTest(decimal_odds=decimal_odds):
                with self.assertRaises(ValueError):
                    prematch_1x2_market_baseline(decimal_odds)

    def test_output_mappings_cannot_be_mutated_after_creation(self):
        baseline = prematch_1x2_market_baseline({"home": 2.0, "draw": 3.0, "away": 4.0})
        with self.assertRaises(TypeError):
            baseline.probabilities["home"] = 1.0


if __name__ == "__main__":
    unittest.main()
