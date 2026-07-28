import unittest

from jingcai.history_audit import audit_history_coverage


class HistoryAuditTests(unittest.TestCase):
    def test_reports_decision_coverage_and_rejects_post_kickoff_points(self) -> None:
        results = [{"match_id": "1", "kickoff": "2026-07-28T12:00:00+00:00"}]
        points = [{
            "match_id": "1", "market": market,
            "published_at": "2026-07-28T10:10:00+00:00", "odds": {"h": 2.0},
        } for market in ("match_result", "handicap_result", "total_goals", "correct_score", "half_full")]
        report = audit_history_coverage(results, points)
        self.assertTrue(report["safe_for_economic_backtest"])
        self.assertEqual(100.0, report["coverage"]["match_result"]["coverage_percent"])
        unsafe = audit_history_coverage(results, points + [{
            "match_id": "1", "market": "match_result", "published_at": "2026-07-28T12:01:00+00:00", "odds": {"h": 2.0},
        }])
        self.assertFalse(unsafe["safe_for_economic_backtest"])
        self.assertIn("published after kickoff", [row["reason"] for row in unsafe["quarantined"]])

    def test_does_not_count_future_or_stale_snapshots_as_coverage(self) -> None:
        results = [{"match_id": "1", "kickoff": "2026-07-28T12:00:00+00:00"}]
        report = audit_history_coverage(results, [{
            "match_id": "1", "market": "match_result", "published_at": "2026-07-28T09:44:00+00:00", "odds": {"h": 2.0},
        }])
        self.assertEqual(0, report["coverage"]["match_result"]["covered_matches"])
        self.assertEqual("snapshot_stale", report["missing_at_decision"][0]["reason"])
