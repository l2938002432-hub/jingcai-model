import math
import unittest

from jingcai.models import CalibratedModel, DixonColesModel, EloModel, HalfFullModel, OutcomeCalibrator, PoissonModel


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
    def test_poisson_is_normalized_and_supports_unseen_teams(self):
        model = PoissonModel().fit(MATCHES)
        assert_matrix(self, model.predict_score_matrix("A", "NEW", 8), (9, 9))

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
