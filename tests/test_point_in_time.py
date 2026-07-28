import unittest
from datetime import UTC, datetime, timedelta

from jingcai.point_in_time import select_last_snapshot


class PointInTimeTests(unittest.TestCase):
    def test_selects_last_snapshot_before_decision_not_the_future(self) -> None:
        decision = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
        rows = [
            {"match_id": "1", "market": "match_result", "published_at": (decision - timedelta(minutes=20)).isoformat(), "odds": {"h": 2.0}},
            {"match_id": "1", "market": "match_result", "published_at": (decision - timedelta(minutes=5)).isoformat(), "odds": {"h": 2.1}},
            {"match_id": "1", "market": "match_result", "published_at": (decision + timedelta(seconds=1)).isoformat(), "odds": {"h": 9.9}},
        ]
        result = select_last_snapshot(rows, match_id="1", market="match_result", decision_at=decision)
        self.assertIsNone(result.reason)
        self.assertEqual(2.1, result.snapshot["odds"]["h"])

    def test_rejects_stale_future_and_naive_decisions(self) -> None:
        decision = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
        stale = [{"match_id": "1", "market": "match_result", "published_at": (decision - timedelta(minutes=31)).isoformat(), "odds": {"h": 2.0}}]
        result = select_last_snapshot(stale, match_id="1", market="match_result", decision_at=decision)
        self.assertEqual("snapshot_stale", result.reason)
        future = [{"match_id": "1", "market": "match_result", "published_at": (decision + timedelta(seconds=1)).isoformat(), "odds": {"h": 2.0}}]
        self.assertEqual("no_snapshot_before_decision", select_last_snapshot(future, match_id="1", market="match_result", decision_at=decision).reason)
        with self.assertRaises(ValueError):
            select_last_snapshot([], match_id="1", market="match_result", decision_at=datetime(2026, 7, 28, 10, 0))
