import unittest

from jingcai.providers.sporttery import SportteryError, normalize_payload, validate_payload


class SportteryProviderTests(unittest.TestCase):
    def test_normalizes_all_five_markets(self) -> None:
        match = {
            "matchId": 7, "matchNumStr": "周三001", "matchDate": "2026-07-23",
            "matchTime": "01:00:00", "leagueAbbName": "测试", "homeTeamAbbName": "甲",
            "awayTeamAbbName": "乙", "matchStatus": "Selling",
            "had": {"h": "2.0", "d": "3.0", "a": "4.0"},
            "hhad": {"h": "3.0", "d": "3.2", "a": "2.0", "goalLineValue": "-1.00"},
            "crs": {"s01s00": "7.0", "s1sh": "9.0"},
            "ttg": {"s0": "8.0", "s7": "10.0"},
            "hafu": {"hh": "3.0", "aa": "4.0"},
        }
        payload = {"success": True, "value": {"matchInfoList": [{"subMatchList": [match]}]}}
        row = normalize_payload(payload)[0]
        self.assertEqual(-1, row["handicap"])
        self.assertEqual({"match_result", "handicap_result", "correct_score", "total_goals", "half_full"}, set(row["odds"]))
        self.assertIn("other_home", row["odds"]["correct_score"])
        self.assertTrue(row["sale_cutoff_estimated"])

    def test_rejects_unexpected_payload(self) -> None:
        with self.assertRaises(SportteryError):
            validate_payload({"success": False})


if __name__ == "__main__":
    unittest.main()
