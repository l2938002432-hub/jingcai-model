import json
import tempfile
import unittest
from pathlib import Path

from jingcai.prospective_validation import attach_official_results, load_captured_fixtures


class ProspectiveValidationTests(unittest.TestCase):
    def test_loads_only_pre_match_fixtures_and_attaches_finished_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "normalized" / "2026-07-28" / "one.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"observed_at": "2026-07-28T10:00:00+00:00", "fixtures": [{"match_id": "1", "kickoff": "2026-07-28T12:00:00+00:00", "odds": {}}]}), encoding="utf-8")
            fixtures = load_captured_fixtures(directory)
            rows = attach_official_results(fixtures, [{"match_id": "1", "status": "finished", "home_score": 2, "away_score": 1, "revision": "r1"}])
            self.assertEqual("finished", rows[0]["result_status"])
            self.assertEqual((2, 1), (rows[0]["home_score"], rows[0]["away_score"]))

    def test_conflicting_results_are_not_silently_settled(self) -> None:
        rows = attach_official_results([{"match_id": "1"}], [
            {"match_id": "1", "status": "finished", "home_score": 1, "away_score": 0},
            {"match_id": "1", "status": "finished", "home_score": 0, "away_score": 1},
        ])
        self.assertEqual("conflict", rows[0]["result_status"])
