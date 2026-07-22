import math
import unittest

from jingcai.models import CalibratedModel, DixonColesModel, EloModel, HalfFullModel, OutcomeCalibrator, PoissonModel
from jingcai.models.poisson import match_timestamp


MATCHES = [
    {"date": "2024-01-03", "home": "A", "away": "B", "home_goals": 2, "away_goals": 0},
    {"date": "2024-01-01", "home": "B", "away": "A", "home_goals": 0, "away_goals": 1},
    {"date": "2024-01-05", "home": "A", "away": "C", "home_goals": 1, "away_goals": 1},
    {"date": "2024-01-08", "home": "C", "away": "B", "home_goals": 0, "away_goals": 0},
    {"date": "2024-01-10", "home": "B", "away": "C", "home_goals": 3, "away_goals": 1},
    {"date": "2024-01-12", "home": "C", "away": "A", "home_goals": 1, "away_goals": 2},
]


def assert_matrix(test, matrix, size=None):
    if size is not None:
        test.assertEqual((len(matrix), len(matrix[0])), size)
    values = [value for row in matrix for value in row]
    test.assertTrue(all(math.isfinite(value) and value >= 0 for value in values))
    test.assertAlmostEqual(sum(values), 1.0, places=12)


class ModelTests(unittest.TestCase):
    def test_match_timestamp_supports_explicit_date_and_utc_fields(self) -> None:
        self.assertLess(
            match_timestamp({"kickoff_date": "2024-01-01"}),
            match_timestamp({"kickoff_utc": "2024-01-02T00:00:00Z"}),
        )

    def test_elo_rejects_matches_without_time_instead_of_trusting_input_order(self) -> None:
        with self.assertRaises(ValueError):
            EloModel().fit([{"home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0}])

    def test_poisson_is_normalized_and_supports_unseen_teams(self):
        model = PoissonModel().fit(MATCHES)
        assert_matrix(self, model.predict_score_matrix("A", "NEW", 8), (9, 9))

    def test_poisson_half_life_none_preserves_existing_fit(self):
        original = PoissonModel().fit(MATCHES)
        explicit = PoissonModel().fit(MATCHES, half_life_days=None)
        self.assertEqual(original.expected_goals("A", "B"), explicit.expected_goals("A", "B"))

    def test_poisson_as_of_excludes_future_matches(self):
        future = {"date": "2025-01-01", "home": "A", "away": "B", "home_goals": 20, "away_goals": 0}
        cutoff = PoissonModel().fit(MATCHES, as_of="2024-01-12")
        with_future = PoissonModel().fit(MATCHES + [future], as_of="2024-01-12")
        self.assertEqual(cutoff.expected_goals("A", "B"), with_future.expected_goals("A", "B"))

    def test_poisson_time_decay_gives_recent_matches_more_weight(self):
        rows = [
            {"date": "2024-01-01", "home": "A", "away": "B", "home_goals": 8, "away_goals": 0},
            {"date": "2024-02-01", "home": "A", "away": "B", "home_goals": 0, "away_goals": 0},
        ]
        unweighted = PoissonModel().fit(rows)
        decayed = PoissonModel().fit(rows, as_of="2024-02-01", half_life_days=7)
        self.assertLess(decayed.home_mean, unweighted.home_mean)

    def test_dixon_coles_decay_filters_future_matches(self):
        future = {"date": "2025-01-01", "home": "A", "away": "B", "home_goals": 0, "away_goals": 0}
        expected = DixonColesModel().fit(MATCHES, as_of="2024-01-12", half_life_days=30)
        actual = DixonColesModel().fit(MATCHES + [future], as_of="2024-01-12", half_life_days=30)
        self.assertEqual(expected.expected_goals("A", "B"), actual.expected_goals("A", "B"))
        self.assertEqual(expected.rho, actual.rho)

    def test_dixon_coles_changes_low_scores_and_normalizes(self):
        poisson = PoissonModel().fit(MATCHES).predict_score_matrix("A", "B")
        model = DixonColesModel(rho=-0.1).fit(MATCHES)
        corrected = model.predict_score_matrix("A", "B")
        assert_matrix(self, corrected, (11, 11))
        self.assertNotAlmostEqual(poisson[0][0], corrected[0][0])

    def test_elo_updates_in_timestamp_order(self):
        model = EloModel().fit(MATCHES[:2])
        self.assertEqual([item[0] for item in model.history], ["2024-01-01", "2024-01-03"])
        self.assertGreater(model.ratings["A"], model.ratings["B"])
        assert_matrix(self, model.predict_score_matrix("A", "B"))

    def test_calibrator_requires_fit_and_normalizes(self):
        calibrator = OutcomeCalibrator()
        with self.assertRaises(RuntimeError):
            calibrator.transform((0.4, 0.3, 0.3))
        calibrator.fit([(0.4, 0.3, 0.3), (0.6, 0.2, 0.2)], [0, 1])
        self.assertAlmostEqual(sum(calibrator.transform((0.4, 0.3, 0.3))), 1.0)

    def test_calibrated_model_uses_holdout_and_normalizes(self):
        model = CalibratedModel(PoissonModel(), calibration_fraction=0.33).fit(MATCHES)
        assert_matrix(self, model.predict_score_matrix("A", "B"))

    def test_half_full_has_nine_probabilities(self):
        model = HalfFullModel(PoissonModel()).fit(MATCHES)
        matrix = model.predict_score_matrix("A", "B", 7)
        assert_matrix(self, matrix, (3, 3))
        probabilities = model.predict_proba("A", "B", 7)
        self.assertEqual(len(probabilities), 9)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
