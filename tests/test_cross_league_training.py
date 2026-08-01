import unittest

from jingcai.cross_league_training import build_cross_league_training_rows
from jingcai.identity import TeamAliases
from jingcai.providers.club_elo_history import ClubEloHistory


class CrossLeagueTrainingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.elo = ClubEloHistory(
            [
                {"date": "2024-01-01", "club": "A", "country": "ENG", "elo": "1500"},
                {"date": "2024-01-01", "club": "B", "country": "ENG", "elo": "1400"},
                {"date": "2024-01-01", "club": "C", "country": "ESP", "elo": "1600"},
                {"date": "2024-01-01", "club": "D", "country": "ESP", "elo": "1450"},
                {"date": "2024-01-10", "club": "A", "country": "ENG", "elo": "1900"},
            ]
        )

    def test_rows_use_only_before_kickoff_elo_and_prior_results(self) -> None:
        result = build_cross_league_training_rows(
            [
                {"provider_match_id": "one", "competition": "ENG1", "season": "2024", "kickoff_utc": "2024-01-05T12:00:00Z", "home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 0},
                {"provider_match_id": "two", "competition": "INT", "season": "2024", "kickoff_utc": "2024-01-06T12:00:00Z", "home_team": "C", "away_team": "A", "home_goals": 1, "away_goals": 1},
            ],
            elo_history=self.elo,
        )
        self.assertEqual(2, len(result.rows))
        first, second = result.rows
        self.assertEqual(0, first["home_history"]["prior_matches"])
        self.assertEqual(1, second["away_history"]["prior_matches"])
        self.assertEqual(2.0, second["away_history"]["prior_goals_for_per_match"])
        self.assertEqual("2024-01-01", second["away_elo_snapshot_date"])
        self.assertEqual(1500.0, second["away_elo"])

    def test_same_kickoff_results_do_not_leak_between_rows(self) -> None:
        rows = [
            {"provider_match_id": "one", "competition": "ENG1", "kickoff_utc": "2024-01-05T12:00:00Z", "home_team": "A", "away_team": "B", "home_goals": 4, "away_goals": 0},
            {"provider_match_id": "two", "competition": "ESP1", "kickoff_utc": "2024-01-05T12:00:00Z", "home_team": "C", "away_team": "D", "home_goals": 1, "away_goals": 0},
        ]
        result = build_cross_league_training_rows(rows, elo_history=self.elo)
        self.assertEqual([0, 0], [row["home_history"]["prior_matches"] for row in result.rows])
        self.assertEqual([0, 0], [row["away_history"]["prior_matches"] for row in result.rows])

    def test_missing_or_same_day_elo_is_rejected_and_counted(self) -> None:
        result = build_cross_league_training_rows(
            [
                {"provider_match_id": "same-day", "competition": "ENG1", "kickoff_utc": "2024-01-01T12:00:00Z", "home_team": "A", "away_team": "B", "home_goals": 0, "away_goals": 0},
                {"provider_match_id": "unknown", "competition": "ENG1", "kickoff_utc": "2024-01-05T12:00:00Z", "home_team": "Unknown", "away_team": "B", "home_goals": 0, "away_goals": 0},
            ],
            elo_history=self.elo,
        )
        self.assertEqual([], list(result.rows))
        self.assertEqual({"home_elo_missing_before_kickoff": 2}, result.coverage["rejected_by_reason"])
        self.assertEqual(0.0, result.coverage["coverage_rate"])

    def test_date_only_kickoff_is_rejected_before_history_features(self) -> None:
        result = build_cross_league_training_rows(
            [{"provider_match_id": "unknown-time", "competition": "ENG1", "kickoff_utc": "2024-01-05T12:00:00Z", "kickoff_precision": "date_only", "home_team": "A", "away_team": "B", "home_goals": 0, "away_goals": 0}],
            elo_history=self.elo,
        )
        self.assertEqual([], list(result.rows))
        self.assertEqual({"kickoff_time_unknown": 1}, result.coverage["rejected_by_reason"])

    def test_day_frozen_mode_is_research_only_and_never_orders_same_day_results(self) -> None:
        result = build_cross_league_training_rows(
            [
                {"provider_match_id": "unknown-time", "competition": "ENG1", "kickoff_utc": "2024-01-05T12:00:00Z", "kickoff_precision": "date_only", "home_team": "A", "away_team": "B", "home_goals": 3, "away_goals": 0},
                {"provider_match_id": "exact", "competition": "ESP1", "kickoff_utc": "2024-01-05T22:00:00Z", "kickoff_precision": "exact", "home_team": "C", "away_team": "D", "home_goals": 1, "away_goals": 0},
            ],
            elo_history=self.elo,
            date_only_policy="freeze_utc_day",
        )
        self.assertEqual(2, len(result.rows))
        self.assertEqual([0, 0], [row["home_history"]["prior_matches"] for row in result.rows])
        by_id = {row["provider_match_id"]: row for row in result.rows}
        self.assertEqual("date_only", by_id["unknown-time"]["time_precision"])
        self.assertEqual("2024-01-05T00:00:00Z", by_id["exact"]["history_cutoff_utc"])
        self.assertFalse(result.coverage["safe_for_economic_validation"])

    def test_aliases_normalize_history_and_elo_join(self) -> None:
        aliases = TeamAliases({"Alpha": ["A"]})
        elo = ClubEloHistory(
            [
                {"date": "2024-01-01", "club": "Alpha", "country": "ENG", "elo": "1500"},
                {"date": "2024-01-01", "club": "B", "country": "ENG", "elo": "1400"},
            ], aliases,
        )
        result = build_cross_league_training_rows(
            [{"provider_match_id": "alias", "competition": "ENG1", "kickoff_utc": "2024-01-02T12:00:00Z", "home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0}],
            elo_history=elo,
            aliases=aliases,
        )
        self.assertEqual("Alpha", result.rows[0]["home_team"])


if __name__ == "__main__":
    unittest.main()
