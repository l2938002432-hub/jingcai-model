import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jingcai.frozen_registry import freeze_new_candidates


class FrozenRegistryTests(unittest.TestCase):
    def test_only_the_first_match_market_prediction_is_frozen(self) -> None:
        now = datetime(2026, 7, 29, 7, tzinfo=UTC)
        candidate = {"match_id": "m1", "market": "match_result", "outcome": "home", "decimal_odds": 2.0, "probability": .55, "odds_as_of": now.isoformat(), "sale_cutoff": (now + timedelta(hours=1)).isoformat()}
        replacement = dict(candidate, outcome="away", decimal_odds=4.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.jsonl"
            first = freeze_new_candidates(path, [candidate], frozen_at=now)
            second = freeze_new_candidates(path, [replacement], frozen_at=now + timedelta(minutes=5))
        self.assertEqual((1, []), (len(first), second))
