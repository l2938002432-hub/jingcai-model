import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jingcai.ledger import (
    Ledger,
    LedgerEvent,
    LedgerEventType,
    LedgerKind,
    ReleaseManifest,
    freeze_release,
)
from scripts.settle_ledgers import ResultRevision, replay_ledger
from jingcai.domain import ResultStatus


NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)


def ticket(ticket_id="ticket-1", odds=2.0):
    return {
        "ticket_id": ticket_id,
        "selections": [{
            "prediction_id": "prediction-1", "match_id": "match-1",
            "market": "match_result", "outcome": "home", "decimal_odds": odds,
        }],
        "stake": 2,
        "created_at": NOW.isoformat(),
        "sale_cutoffs": {"match-1": (NOW + timedelta(hours=1)).isoformat()},
    }


def result(revision="1", home=2, away=1):
    return ResultRevision(
        "match-1", revision, "official", NOW + timedelta(hours=int(revision)),
        ResultStatus.FINISHED, home, away,
    )


class SettlementReplayTests(unittest.TestCase):
    def _model(self, path):
        ledger = Ledger(path, LedgerKind.MODEL)
        freeze_release(ledger, ReleaseManifest(
            "release-1", "release-key", NOW, NOW, "a" * 64, "model-v1",
            "b" * 64, "rules-v1", "git", (), (ticket(),),
            {"allowed": True, "strategy_id": "test-v1", "evidence_sha256": "c" * 64},
        ))
        return ledger

    def _personal(self, path):
        ledger = Ledger(path, LedgerKind.PERSONAL)
        event = LedgerEvent(
            "purchase-1", LedgerKind.PERSONAL, LedgerEventType.PURCHASE_CONFIRMED,
            "ticket-1", NOW, {"release_id": "release-1", "ticket": ticket(odds=2.5)},
        )
        ledger.append_event(event, idempotency_key="purchase:ticket-1")
        return ledger

    def test_model_and_personal_settle_independently_at_frozen_odds(self):
        with tempfile.TemporaryDirectory() as directory:
            model = self._model(Path(directory) / "model.jsonl")
            personal = self._personal(Path(directory) / "personal.jsonl")
            replay_ledger(model, [result()], occurred_at=NOW, rules_version="rules-v1")
            replay_ledger(personal, [result()], occurred_at=NOW, rules_version="rules-v1")
            model_settlement = [
                e for e in model.read_events() if e["event_type"] == "settled"
            ][0]["payload"]
            personal_settlement = [
                e for e in personal.read_events() if e["event_type"] == "settled"
            ][0]["payload"]
            self.assertEqual(4.0, model_settlement["payout"])
            self.assertEqual(5.0, personal_settlement["payout"])

    def test_duplicate_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._model(Path(directory) / "model.jsonl")
            first = replay_ledger(ledger, [result()], occurred_at=NOW, rules_version="rules-v1")
            event_count = len(ledger.read_events())
            second = replay_ledger(ledger, [result()], occurred_at=NOW, rules_version="rules-v1")
            self.assertEqual((first.settled, second.settled), (1, 0))
            self.assertEqual(event_count, len(ledger.read_events()))

    def test_result_revision_appends_reversal_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._model(Path(directory) / "model.jsonl")
            replay_ledger(ledger, [result()], occurred_at=NOW, rules_version="rules-v1")
            summary = replay_ledger(
                ledger, [result("2", home=0, away=1)],
                occurred_at=NOW + timedelta(hours=3), rules_version="rules-v1",
            )
            types = [event["event_type"] for event in ledger.read_events()]
            self.assertEqual(1, summary.reversed)
            self.assertEqual(2, types.count("settled"))
            self.assertEqual(1, types.count("settlement_reversed"))
            latest = [e for e in ledger.read_events() if e["event_type"] == "settled"][-1]
            self.assertEqual("lost", latest["payload"]["status"])

    def test_missing_and_conflicting_results_remain_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._model(Path(directory) / "model.jsonl")
            missing = replay_ledger(
                ledger, [], occurred_at=NOW, rules_version="rules-v1"
            )
            conflict = replay_ledger(
                ledger,
                [
                    ResultRevision(
                        "match-1", "x", "one", NOW, ResultStatus.FINISHED, 1, 0
                    ),
                    ResultRevision(
                        "match-1", "y", "two", NOW, ResultStatus.FINISHED, 0, 1
                    ),
                ],
                occurred_at=NOW, rules_version="rules-v1",
            )
            self.assertEqual(("ticket-1",), missing.pending)
            self.assertEqual(("ticket-1",), conflict.pending)
            self.assertEqual(("match-1",), conflict.conflicts)
            self.assertFalse(any(
                event["event_type"] == "settled" for event in ledger.read_events()
            ))


if __name__ == "__main__":
    unittest.main()
