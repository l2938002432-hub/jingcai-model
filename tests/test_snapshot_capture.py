import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

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
            stored = Path(str(result["path"])).read_text(encoding="utf-8")
            self.assertIn("observed_at", stored)
            self.assertNotIn("candidate", stored)
