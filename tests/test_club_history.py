import tempfile
import unittest
from pathlib import Path

from jingcai.providers.club_history import ClubHistoryError, load_club_history_csv


class ClubHistoryTests(unittest.TestCase):
    def test_streams_and_filters_normalized_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.csv"
            path.write_text(
                "Division,MatchDate,MatchTime,HomeTeam,AwayTeam,FTHome,FTAway\n"
                "BRA,2024-06-01,20:00:00,Flamengo,Botafogo,2,1\n"
                "E0,2020-01-01,12:00:00,A,B,0,0\n", encoding="utf-8"
            )
            rows = list(load_club_history_csv(path, divisions={"BRA"}, since="2023-01-01"))
            self.assertEqual(1, len(rows))
            self.assertEqual("Flamengo", rows[0]["home_team"])

    def test_rejects_bad_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("x,y\n1,2\n", encoding="utf-8")
            with self.assertRaises(ClubHistoryError):
                list(load_club_history_csv(path))

    def test_skips_scheduled_rows_with_both_scores_blank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.csv"
            path.write_text(
                "Division,MatchDate,MatchTime,HomeTeam,AwayTeam,FTHome,FTAway\n"
                "BRA,2026-07-24,20:00:00,A,B,,\n"
                "BRA,2026-07-20,20:00:00,C,D,1,0\n",
                encoding="utf-8",
            )
            rows = list(load_club_history_csv(path, divisions={"BRA"}))
            self.assertEqual(["C"], [row["home_team"] for row in rows])

    def test_preserves_half_time_labels_and_pre_match_elo_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.csv"
            path.write_text(
                "Division,MatchDate,MatchTime,HomeTeam,AwayTeam,FTHome,FTAway,HTHome,HTAway,HomeElo,AwayElo\n"
                "BRA,2026-07-20,20:00:00,A,B,2,1,1,0,1512.5,1490\n",
                encoding="utf-8",
            )
            row = list(load_club_history_csv(path))[0]
            self.assertEqual((1, 0), (row["half_home_goals"], row["half_away_goals"]))
            self.assertEqual((1512.5, 1490.0), (row["home_elo"], row["away_elo"]))


if __name__ == "__main__":
    unittest.main()
