from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jingcai.providers.openfootball import load_champions_qualifiers


class OpenFootballTests(unittest.TestCase):
    def test_parses_normal_and_uses_regulation_score_for_extra_time(self) -> None:
        text = """= UEFA Champions League - Quali 2025/26
  Tue Jul 8 2025
    18:00  Olimpija Ljubljana (SVN) v FK Kairat (KAZ)          1-1 (0-0)
  Tue Jul 15
    19:00  KF Shkëndija 79 (MKD)   v The New Saints (WAL)     2-1 a.e.t. (1-1, 1-1)
    19:15  Slovan Bratislava (SVK) v FK Kairat (KAZ)          3-4 pen. 1-0 a.e.t. (1-0, 1-0)
"""
        with TemporaryDirectory() as folder:
            path = Path(folder) / "clq.txt"
            path.write_text(text, encoding="utf-8")
            rows = list(load_champions_qualifiers(path, season="2025-26"))
        self.assertEqual((rows[0]["home_team"], rows[0]["away_team"]), ("Olimpija Ljubljana", "FK Kairat"))
        self.assertEqual((rows[0]["home_goals"], rows[0]["away_goals"]), (1, 1))
        self.assertEqual((rows[1]["home_goals"], rows[1]["away_goals"]), (1, 1))
        self.assertEqual((rows[2]["home_goals"], rows[2]["away_goals"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
