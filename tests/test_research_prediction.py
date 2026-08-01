import unittest

from jingcai.providers.club_elo_history import ClubEloHistory
from jingcai.research_prediction import ResearchEloBaseline, research_1x2


class ResearchPredictionTests(unittest.TestCase):
    def test_dated_elo_returns_normalized_research_probability(self):
        ratings = ClubEloHistory([
            {"date": "2026-01-01", "club": "Home", "country": "ENG", "elo": "1800"},
            {"date": "2026-01-01", "club": "Away", "country": "ENG", "elo": "1500"},
        ])
        result = research_1x2({"home_team": "Home", "away_team": "Away", "scheduled_start": "2026-08-01T12:00:00+00:00"}, ratings)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(1.0, sum(result.values()))
        self.assertGreater(result["home"], result["away"])

    def test_missing_team_is_not_invented(self):
        ratings = ClubEloHistory([{"date": "2026-01-01", "club": "Home", "country": "ENG", "elo": "1800"}])
        self.assertIsNone(research_1x2({"home_team": "Home", "away_team": "Missing", "scheduled_start": "2026-08-01T12:00:00+00:00"}, ratings))

    def test_baseline_is_serializable_and_records_point_in_time_inputs(self):
        ratings = ClubEloHistory([
            {"date": "2026-01-01", "club": "Home", "country": "ENG", "elo": "1800"},
            {"date": "2026-01-01", "club": "Away", "country": "ESP", "elo": "1500"},
        ])
        model = ResearchEloBaseline()
        restored = ResearchEloBaseline.from_dict(model.to_dict())
        prediction = restored.predict(
            {"home_team": "Home", "away_team": "Away", "scheduled_start": "2026-08-01T12:00:00+00:00"},
            ratings,
            as_of="2026-07-31T12:00:00+00:00",
        )
        self.assertIsNotNone(prediction)
        assert prediction is not None
        self.assertTrue(prediction["research_only"])
        self.assertEqual("2026-01-01", prediction["input_snapshots"]["home"]["date"])
        self.assertAlmostEqual(1.0, sum(prediction["result_1x2"].values()))
        self.assertAlmostEqual(1.0, sum(map(sum, prediction["score_matrix"])))

    def test_baseline_rejects_future_cutoff_and_timezone_less_cutoff(self):
        ratings = ClubEloHistory([
            {"date": "2026-01-01", "club": "Home", "country": "ENG", "elo": "1800"},
            {"date": "2026-01-01", "club": "Away", "country": "ENG", "elo": "1500"},
        ])
        fixture = {"home_team": "Home", "away_team": "Away", "scheduled_start": "2026-08-01T12:00:00+00:00"}
        with self.assertRaises(ValueError):
            ResearchEloBaseline().predict(fixture, ratings, as_of="2026-08-02T12:00:00+00:00")
        with self.assertRaises(ValueError):
            ResearchEloBaseline().predict(fixture, ratings, as_of="2026-07-31T12:00:00")
