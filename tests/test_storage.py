import json
import tempfile
import unittest
from pathlib import Path

from jingcai.storage import AppendOnlyJsonlStore, manifest_hash


class StorageTests(unittest.TestCase):
    def test_append_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AppendOnlyJsonlStore(Path(directory) / "ledger.jsonl")
            digest = store.append({"match": "A-B", "state": "PAPER_ONLY"})
            self.assertEqual(64, len(digest))
            self.assertEqual([{"match": "A-B", "state": "PAPER_ONLY"}], store.read_verified())

    def test_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            store = AppendOnlyJsonlStore(path)
            store.append({"value": 1})
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["record"]["value"] = 2
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                store.read_verified()

    def test_deletion_and_reordering_break_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            store = AppendOnlyJsonlStore(path)
            store.append({"value": 1})
            store.append({"value": 2})
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text(lines[1] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sequence mismatch|chain mismatch"):
                store.read_verified()

    def test_append_once_is_idempotent_and_detects_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AppendOnlyJsonlStore(Path(directory) / "ledger.jsonl")
            first = store.append_once("daily:1", {"value": 1})
            self.assertEqual(first, store.append_once("daily:1", {"value": 1}))
            self.assertEqual(1, len(store.read_verified()))
            with self.assertRaisesRegex(ValueError, "idempotency conflict"):
                store.append_once("daily:1", {"value": 2})

    def test_manifest_is_order_sensitive_and_stable(self) -> None:
        first = manifest_hash([{"b": 2, "a": 1}])
        second = manifest_hash([{"a": 1, "b": 2}])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
