import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from jingcai.ledger import (
    Ledger,
    LedgerEvent,
    LedgerEventType,
    LedgerKind,
    ReleaseManifest,
    freeze_release,
)


NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)


def manifest(*, release_id: str = "release-1", candidate_probability: float = 0.6):
    return ReleaseManifest(
        release_id=release_id,
        idempotency_key="snapshot-model-config",
        published_at=NOW,
        source_as_of=NOW,
        snapshot_sha256="a" * 64,
        model_version="model-v1",
        config_sha256="b" * 64,
        rules_version="rules-v1",
        git_sha="abc123",
        candidates=({"selection": "home", "probability": candidate_probability},),
    )


class LedgerTests(unittest.TestCase):
    def test_freeze_release_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "model.jsonl", LedgerKind.MODEL)
            first = freeze_release(ledger, manifest())
            second = freeze_release(ledger, manifest())
            self.assertEqual(first, second)
            self.assertEqual(1, len(ledger.read_events()))

    def test_same_release_key_with_changed_content_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "model.jsonl", LedgerKind.MODEL)
            freeze_release(ledger, manifest())
            with self.assertRaisesRegex(ValueError, "idempotency conflict"):
                freeze_release(ledger, manifest(candidate_probability=0.7))

    def test_model_and_personal_events_cannot_cross_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Ledger(Path(directory) / "model.jsonl", LedgerKind.MODEL)
            personal = Ledger(Path(directory) / "personal.jsonl", LedgerKind.PERSONAL)
            purchase = LedgerEvent(
                "event-1", LedgerKind.PERSONAL, LedgerEventType.PURCHASE_CONFIRMED,
                "ticket-1", NOW, {"release_id": "release-1"},
            )
            with self.assertRaisesRegex(ValueError, "different ledger"):
                model.append_event(purchase, idempotency_key="purchase:1")
            personal.append_event(purchase, idempotency_key="purchase:1")
            with self.assertRaisesRegex(ValueError, "model ledger"):
                freeze_release(personal, manifest())

    def test_personal_purchase_is_forbidden_in_model_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Ledger(Path(directory) / "model.jsonl", LedgerKind.MODEL)
            event = LedgerEvent(
                "event-1", LedgerKind.MODEL, LedgerEventType.PURCHASE_CONFIRMED,
                "ticket-1", NOW, {},
            )
            with self.assertRaisesRegex(ValueError, "forbidden"):
                model.append_event(event, idempotency_key="purchase:1")


if __name__ == "__main__":
    unittest.main()
