import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from jingcai.data_contract import CONTRACT_FIELDS
from jingcai.snapshot_capture import capture_snapshot


class SnapshotCaptureTests(unittest.TestCase):
    def test_archives_each_prospective_observation_without_recommendation(self) -> None:
        payload = {"success": True, "value": {"matchInfoList": [{"subMatchList": [{
            "matchId": 1, "matchDate": "2026-07-28", "matchTime": "20:00:00", "matchStatus": "Selling", "homeTeamAbbName": "甲", "awayTeamAbbName": "乙",
            "had": {"h": "2.0", "d": "3.0", "a": "4.0"}, "hhad": {}, "crs": {}, "ttg": {}, "hafu": {},
        }]}]}}
        with tempfile.TemporaryDirectory() as directory:
            result = capture_snapshot(directory, payload=payload, observed_at=datetime(2026, 7, 28, 10, tzinfo=UTC))
            self.assertEqual(1, result["fixtures"])
            stored = json.loads(Path(str(result["path"])).read_text(encoding="utf-8"))
            self.assertIn("observed_at", stored)
            self.assertNotIn("candidate", str(stored))
            self.assertEqual(1, result["data_quality"]["complete_record_count"])
            self.assertEqual(1, stored["data_quality"]["provenance"]["record_count"])
            fixture = stored["fixtures"][0]
            self.assertTrue(all(field in fixture for field in CONTRACT_FIELDS))
            self.assertEqual("sporttery-public-calculator", fixture["source"])
            self.assertEqual(stored["data_quality"]["raw_hash"], fixture["raw_hash"])
            self.assertEqual("2026-07-28T10:00:00+00:00", fixture["available_at"])
