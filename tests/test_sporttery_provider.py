import unittest
from datetime import UTC, datetime
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

from jingcai.providers.sporttery import (
    SportteryError,
    fetch_sporttery_payload,
    normalize_fixed_bonus_history,
    normalize_payload,
    validate_payload,
)


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

    def test_rejects_malformed_match_groups(self) -> None:
        malformed_payloads = [
            {"success": True, "value": {"matchInfoList": [None]}},
            {"success": True, "value": {"matchInfoList": [{}]}},
            {"success": True, "value": {"matchInfoList": [{"subMatchList": [None]}]}},
        ]
        for payload in malformed_payloads:
            with self.subTest(payload=payload), self.assertRaises(SportteryError):
                validate_payload(payload)

    @patch("jingcai.providers.sporttery.subprocess.run")
    @patch("jingcai.providers.sporttery.urlopen", side_effect=OSError("TLS unavailable"))
    def test_curl_fallback_is_cross_platform_and_validates_payload(
        self, _urlopen: MagicMock, run: MagicMock
    ) -> None:
        run.return_value.stdout = (
            '{"success": true, "value": {"matchInfoList": []}}'
        )
        with patch("jingcai.providers.sporttery.os.name", "posix"):
            payload = fetch_sporttery_payload(timeout=2.5)
        self.assertTrue(payload["success"])
        command = run.call_args.args[0]
        self.assertEqual("curl", command[0])
        self.assertIn("--fail", command)
        self.assertEqual("2.5", command[command.index("--max-time") + 1])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    @patch("jingcai.providers.sporttery.subprocess.run")
    @patch("jingcai.providers.sporttery.urlopen", side_effect=OSError("TLS unavailable"))
    def test_windows_uses_curl_exe(
        self, _urlopen: MagicMock, run: MagicMock
    ) -> None:
        run.return_value.stdout = (
            '{"success": true, "value": {"matchInfoList": []}}'
        )
        with patch("jingcai.providers.sporttery.os.name", "nt"):
            fetch_sporttery_payload()
        self.assertEqual("curl.exe", run.call_args.args[0][0])

    @patch("jingcai.providers.sporttery.subprocess.run")
    @patch("jingcai.providers.sporttery.urlopen", side_effect=OSError("TLS unavailable"))
    def test_fallback_rejects_invalid_payload(
        self, _urlopen: MagicMock, run: MagicMock
    ) -> None:
        run.return_value.stdout = '{"success": true, "value": {}}'
        with self.assertRaisesRegex(SportteryError, "official Sporttery feed unavailable"):
            fetch_sporttery_payload()

    @patch("jingcai.providers.sporttery.subprocess.run")
    @patch("jingcai.providers.sporttery.urlopen", side_effect=OSError("TLS unavailable"))
    def test_fallback_reports_curl_failure_without_leaking_details(
        self, _urlopen: MagicMock, run: MagicMock
    ) -> None:
        run.side_effect = CalledProcessError(22, ["curl"], stderr="secret response")
        with self.assertRaisesRegex(SportteryError, "OSError") as raised:
            fetch_sporttery_payload()
        self.assertNotIn("secret response", str(raised.exception))

    def test_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(ValueError):
            fetch_sporttery_payload(timeout=0)

    def test_normalizes_each_historic_market_with_its_own_timestamp(self) -> None:
        payload = {"success": True, "value": {
            "had": [{"updateDate": "2026-07-20", "updateTime": "10:00:00", "h": "2.1", "d": "3.2", "a": "3.4"}],
            "hhad": [{"updateDate": "2026-07-20", "updateTime": "10:01:00", "goalLineValue": "-1", "h": "3.1", "d": "3.3", "a": "2.0"}],
            "ttg": [{"updateDate": "2026-07-20", "updateTime": "10:02:00", "s0": "9.0", "s7": "8.0"}],
            "crs": [{"updateDate": "2026-07-20", "updateTime": "10:03:00", "s00s00": "7.0", "s1sh": "10.0"}],
            "hafu": [{"updateDate": "2026-07-20", "updateTime": "10:04:00", "hh": "3.0", "aa": "4.0"}],
        }}
        rows = normalize_fixed_bonus_history(
            payload, match_id=42, ingested_at=datetime(2026, 7, 28, tzinfo=UTC)
        )
        self.assertEqual(5, len(rows))
        self.assertEqual({"match_result", "handicap_result", "total_goals", "correct_score", "half_full"}, {row["market"] for row in rows})
        handicap = next(row for row in rows if row["market"] == "handicap_result")
        self.assertEqual("-1", handicap["handicap"])
        self.assertEqual("2026-07-20T02:01:00+00:00", handicap["published_at"])
        self.assertEqual("2026-07-28T00:00:00+00:00", handicap["ingested_at"])

    def test_historic_bonus_refuses_missing_time_or_invalid_odds(self) -> None:
        no_time = {"success": True, "value": {"had": [{"h": "2.0"}]}}
        bad_odds = {"success": True, "value": {"had": [{
            "updateDate": "2026-07-20", "updateTime": "10:00:00", "h": "1.0"
        }]}}
        for payload in (no_time, bad_odds):
            with self.subTest(payload=payload), self.assertRaises(SportteryError):
                normalize_fixed_bonus_history(payload, match_id=1, ingested_at=datetime.now(UTC))


if __name__ == "__main__":
    unittest.main()
