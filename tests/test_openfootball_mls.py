from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jingcai.providers.openfootball_mls import load_mls_matches


class OpenFootballMLSTests(unittest.TestCase):
    def test_explicit_dates_override_matchday_order_and_year_is_inherited(self) -> None:
        # Extracted in the same layout as OpenFootball's MLS Football.TXT files.
        # The second fixture represents a rescheduled/makeup game placed under a
        # Matchday outline: its explicit date, not outline order, is authoritative.
        text = """= Major League Soccer 2024

▪ Matchday 3
  Sat Mar 2 2024
    19:30  Inter Miami CF       v Orlando City SC       5-0 (3-0)

▪ Matchday 16
  Sat Jun 1
    19:30  Inter Miami CF       v St. Louis City SC     3-3 (2-2)
"""
        with TemporaryDirectory() as folder:
            path = Path(folder) / "mls.txt"
            path.write_text(text, encoding="utf-8")
            rows = list(load_mls_matches(path, season="2024"))

        self.assertEqual([row["kickoff_date"] for row in rows], ["2024-03-02", "2024-06-01"])
        self.assertEqual(rows[0], {
            "competition": "USA",
            "season": "2024",
            "home_team": "Inter Miami CF",
            "away_team": "Orlando City SC",
            "home_goals": 5,
            "away_goals": 0,
            "kickoff_date": "2024-03-02",
        })
        self.assertNotIn("kickoff_utc", rows[1])

    def test_match_before_any_date_is_rejected(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "mls.txt"
            path.write_text("  Team One  v Team Two  1-0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "match before date"):
                list(load_mls_matches(path, season="2024"))


if __name__ == "__main__":
    unittest.main()
