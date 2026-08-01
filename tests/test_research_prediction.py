import unittest

from jingcai.providers.club_elo_history import ClubEloHistory
from jingcai.research_prediction import research_1x2


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
