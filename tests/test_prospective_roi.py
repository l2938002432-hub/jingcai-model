import unittest
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from jingcai.prospective_roi import freeze_candidates, prospective_return_summary, settle_frozen_candidates
from scripts.report_prospective_roi import main as report_main


class ProspectiveRoiTests(unittest.TestCase):
    def _candidate(self):
        now = datetime(2026, 7, 28, 10, tzinfo=UTC)
        return {"match_id": "1", "market": "match_result", "outcome": "home", "decimal_odds": 2.5, "probability": 0.5, "odds_as_of": now.isoformat(), "sale_cutoff": (now + timedelta(hours=1)).isoformat()}

    def test_freezes_then_settles_only_against_finished_official_sample(self) -> None:
        now = datetime(2026, 7, 28, 10, tzinfo=UTC)
        frozen = freeze_candidates([self._candidate()], frozen_at=now)
        rows = settle_frozen_candidates(frozen, [{"match_id": "1", "result_status": "finished", "home_score": 2, "away_score": 1}])
        self.assertEqual(("won", 3.0), (rows[0]["settlement_status"], rows[0]["profit"]))
        self.assertEqual(1, prospective_return_summary(rows)["bets"])

    def test_pending_results_and_late_freezes_are_rejected(self) -> None:
        now = datetime(2026, 7, 28, 10, tzinfo=UTC)
        frozen = freeze_candidates([self._candidate()], frozen_at=now)
        self.assertEqual("pending", settle_frozen_candidates(frozen, [])[0]["settlement_status"])
        with self.assertRaises(ValueError):
            freeze_candidates([self._candidate()], frozen_at=now + timedelta(hours=2))

    def test_report_cli_excludes_pending_from_return_metrics(self) -> None:
        now = datetime(2026, 7, 28, 10, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen_path, samples_path, output_path = root / "frozen.json", root / "samples.json", root / "report.json"
            frozen_path.write_text(json.dumps(freeze_candidates([self._candidate()], frozen_at=now)), encoding="utf-8")
            samples_path.write_text(json.dumps([]), encoding="utf-8")
            with patch("sys.argv", ["report", "--frozen", str(frozen_path), "--samples", str(samples_path), "--output", str(output_path)]):
                self.assertEqual(0, report_main())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(("PAPER_ONLY", 1, 0), (report["model_state"], report["pending"], report["summary"]["bets"]))
