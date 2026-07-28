import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts.archive_sporttery_history import archive_batch
from scripts.audit_sporttery_history import main as audit_main
from scripts.enrich_official_kickoffs import main as enrich_main


class ArchiveSportteryHistoryTests(unittest.TestCase):
    def test_archives_and_normalizes_offline_batch_without_network(self) -> None:
        results = {"success": True, "value": {"matchList": [{
            "matchId": 1, "matchDate": "2026-07-28", "matchTime": "20:00:00",
            "sectionsNo999": "1:0", "sectionsNo1": "0:0",
        }]}}
        bonuses = {"1": {"success": True, "value": {"had": [{
            "updateDate": "2026-07-28", "updateTime": "10:00:00", "h": "2.0", "d": "3.0", "a": "4.0"
        }]}}}
        with tempfile.TemporaryDirectory() as directory:
            summary = archive_batch(
                results_payload=results, bonus_payloads=bonuses, root=Path(directory),
                ingested_at=datetime(2026, 7, 28, tzinfo=UTC),
            )
            self.assertEqual({"results": 1, "bonus_points": 1, "root": directory}, summary)
            self.assertTrue((Path(directory) / "normalized-results.json").exists())
            self.assertTrue((Path(directory) / "raw").exists())
            with patch("sys.argv", ["audit", "--input-dir", directory, "--output", str(Path(directory) / "coverage.json")]):
                self.assertEqual(0, audit_main())
            self.assertTrue((Path(directory) / "coverage.json").exists())

    def test_enriches_only_match_id_found_in_offline_official_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results.json").write_text('[{"match_id":"1"}]', encoding="utf-8")
            (root / "page.json").write_text('{"success":true,"value":{"matchInfoList":[{"subMatchList":[{"matchId":1,"matchDate":"2026-07-28","matchTime":"20:00"}]}]}}', encoding="utf-8")
            output = root / "enriched.json"
            with patch("sys.argv", ["enrich", "--input", str(root / "results.json"), "--output", str(output), "--offline-page", str(root / "page.json")]):
                self.assertEqual(0, enrich_main())
            self.assertIn("kickoff", output.read_text(encoding="utf-8"))
