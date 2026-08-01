import unittest
from datetime import UTC, datetime, timedelta

from jingcai.fixture_status import assess_fixtures, coverage_summary


class FixtureStatusTests(unittest.TestCase):
    def test_every_fixture_is_retained_and_classified(self):
        now = datetime(2026, 8, 1, 8, tzinfo=UTC)
        fixtures = [
            {"match_id": "approved", "competition_code": "A", "home_team": "H", "away_team": "A", "sale_cutoff": (now + timedelta(hours=2)).isoformat()},
            {"match_id": "research", "competition_code": "B", "home_team": "H", "away_team": "A", "sale_cutoff": (now + timedelta(hours=2)).isoformat()},
            {"match_id": "missing", "competition_code": "B", "home_team": "X", "away_team": "Y", "sale_cutoff": (now + timedelta(hours=2)).isoformat()},
        ]
        rows = assess_fixtures(fixtures, history_teams={"H", "A"}, acceptance={"A": {"approved": True, "markets": {"match_result": True}}}, now=now, data_fresh=True)
        self.assertEqual(["candidate_eligible", "research_observation", "data_insufficient"], [row["analysis_status"] for row in rows])
        self.assertEqual(3, coverage_summary(rows)["official_on_sale"])

    def test_stale_data_rejects_but_keeps_every_fixture(self):
        now = datetime(2026, 8, 1, 8, tzinfo=UTC)
        rows = assess_fixtures([{"match_id": "x", "home_team": "H", "away_team": "A", "sale_cutoff": (now + timedelta(hours=2)).isoformat()}], history_teams={"H", "A"}, acceptance={}, now=now, data_fresh=False)
        self.assertEqual("safety_rejected", rows[0]["analysis_status"])

