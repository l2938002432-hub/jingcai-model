import unittest
from datetime import UTC, datetime, timedelta

from jingcai.prospective_roi import freeze_candidates
from jingcai.prospective_settlement import settle_registry


class ProspectiveSettlementTests(unittest.TestCase):
    def test_counts_only_official_finished_results(self) -> None:
        now = datetime(2026, 7, 29, 7, tzinfo=UTC)
        frozen = freeze_candidates([{"match_id": "m1", "market": "match_result", "outcome": "home", "decimal_odds": 2.0, "probability": .55, "odds_as_of": now.isoformat(), "sale_cutoff": (now + timedelta(hours=1)).isoformat()}], frozen_at=now)
        report = settle_registry(frozen, [{"match_id": "m1", "status": "finished", "home_score": 1, "away_score": 0}], stake=2)
        self.assertEqual((1, 0, 2.0), (report["summary"]["bets"], report["pending"], report["summary"]["profit"]))
