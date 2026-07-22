from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jingcai.providers.openfootball import load_champions_qualifiers


class OpenFootballSchemaTests(unittest.TestCase):
    def _parse(self, text: str) -> list[dict[str, object]]:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "clq.txt"
            path.write_text(text, encoding="utf-8")
            return list(load_champions_qualifiers(path, season="2025-26"))

    def test_preserves_date_without_inventing_utc_and_extracts_source_fields(self) -> None:
        rows = self._parse("""= UEFA Champions League - Quali 2025/26
  1. Round
  Tue Jul 8 2025
    18:00  Olimpija Ljubljana (SVN) v FK Kairat (KAZ)          1-1 (0-0)
  Tue Jul 15
    16:00  FK Kairat (KAZ) v Olimpija Ljubljana (SVN)          2-0 (2-0)
""")
        self.assertEqual(rows[0]["kickoff_date"], "2025-07-08")
        self.assertEqual(rows[0]["source_kickoff_time"], "18:00")
        self.assertIsNone(rows[0]["source_timezone"])
        self.assertIsNone(rows[0]["kickoff_utc"])
        self.assertEqual(rows[0]["round"], "1. Round")
        self.assertEqual(rows[0]["home_country_code"], "SVN")
        self.assertEqual(rows[0]["away_country_code"], "KAZ")
        self.assertEqual(rows[0]["tie_id"], rows[1]["tie_id"])
        self.assertEqual([row["leg"] for row in rows], [1, 2])

    def test_missing_source_values_are_not_guessed(self) -> None:
        rows = self._parse("""= UEFA Champions League - Quali 2025/26
  Tue Jul 8 2025
           Unknown FC v Other FC          1-0
""")
        row = rows[0]
        self.assertIsNone(row["source_kickoff_time"])
        self.assertIsNone(row["round"])
        self.assertIsNone(row["tie_id"])
        self.assertIsNone(row["leg"])
        self.assertIsNone(row["home_country_code"])
        self.assertIsNone(row["away_country_code"])

    def test_does_not_label_leg_when_pair_is_incomplete(self) -> None:
        rows = self._parse("""= UEFA Champions League - Quali 2025/26
  Play-offs
  Tue Aug 19 2025
    20:00  Celtic FC (SCO) v FK Kairat (KAZ)          0-0
""")
        self.assertEqual(rows[0]["round"], "Play-offs")
        self.assertIsNotNone(rows[0]["tie_id"])
        self.assertIsNone(rows[0]["leg"])


if __name__ == "__main__":
    unittest.main()
