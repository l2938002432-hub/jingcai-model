import tempfile
import unittest
from pathlib import Path

from jingcai.identity import TeamAliases
from jingcai.providers.club_elo_history import ClubEloHistory, ClubEloHistoryError


ROWS = [
    {"date": "2024-01-01", "club": "Alpha FC", "country": "ENG", "elo": "1500"},
    {"date": "2024-02-01", "club": "Alpha FC", "country": "ENG", "elo": "1540"},
    {"date": "2024-01-15", "club": "Beta", "country": "ENG", "elo": "1400"},
    {"date": "2024-01-01", "club": "Gamma", "country": "ESP", "elo": "1600"},
]


class ClubEloHistoryTests(unittest.TestCase):
    def test_strictly_uses_snapshot_before_date_and_aliases(self):
        history = ClubEloHistory(ROWS, TeamAliases({"Alpha FC": ["阿尔法"]}))
        self.assertEqual(1500, history.rating_before("阿尔法", "2024-02-01"))
        self.assertEqual(1540, history.rating_before("阿尔法", "2024-02-02"))

    def test_association_mean_uses_each_clubs_latest_visible_rating(self):
        history = ClubEloHistory(ROWS)
        self.assertEqual({"ENG": 1450, "ESP": 1600}, history.association_priors("2024-01-20"))
        self.assertEqual(1470, history.association_priors("2024-02-02")["ENG"])

    def test_provider_prefers_team_then_falls_back_to_association(self):
        history = ClubEloHistory(ROWS)
        match = {"date": "2024-01-20"}
        self.assertEqual(1500, history.prior_provider(match, "Alpha FC", "ENG"))
        self.assertEqual(1450, history.prior_provider(match, "New Club", "ENG"))

    def test_missing_history_and_future_only_observation_fail_closed(self):
        history = ClubEloHistory(ROWS)
        with self.assertRaises(ClubEloHistoryError):
            history.rating_before("Alpha FC", "2024-01-01")
        with self.assertRaises(ClubEloHistoryError):
            history.prior_provider({"date": "2023-12-31"}, "New Club", "ENG")
        with self.assertRaises(ClubEloHistoryError):
            history.prior_provider({"date": "2024-01-20"}, "New Club", "ITA")

    def test_duplicate_same_day_and_missing_values_are_rejected(self):
        with self.assertRaises(ClubEloHistoryError):
            ClubEloHistory([ROWS[0], dict(ROWS[0], elo="1501")])
        with self.assertRaises(ClubEloHistoryError):
            ClubEloHistory([dict(ROWS[0], country="")])

    def test_csv_header_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("date,club,elo\n2024-01-01,A,1500\n", encoding="utf-8")
            with self.assertRaises(ClubEloHistoryError):
                ClubEloHistory.from_csv(path)


if __name__ == "__main__":
    unittest.main()
