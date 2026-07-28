import unittest
from datetime import UTC, datetime, timedelta

from jingcai.notification_window import select_notification_candidates


class NotificationWindowTests(unittest.TestCase):
    def test_only_fresh_candidates_in_one_to_two_hour_window_are_selected(self) -> None:
        now = datetime(2026, 7, 28, 10, tzinfo=UTC)
        def candidate(match_id: str, cutoff_minutes: int, odds_minutes: int = 0):
            return {"match_id": match_id, "sale_cutoff": (now + timedelta(minutes=cutoff_minutes)).isoformat(), "odds_as_of": (now - timedelta(minutes=odds_minutes)).isoformat()}
        rows = select_notification_candidates([candidate("yes", 90, 30), candidate("early", 121), candidate("late", 59), candidate("stale", 90, 36), {"match_id": "missing"}], observed_at=now)
        self.assertEqual(["yes"], [row["match_id"] for row in rows])

    def test_requires_aware_observation_time(self) -> None:
        with self.assertRaises(ValueError):
            select_notification_candidates([], observed_at=datetime(2026, 7, 28, 10))
