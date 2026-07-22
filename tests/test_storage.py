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

    def test_manifest_is_order_sensitive_and_stable(self) -> None:
        first = manifest_hash([{"b": 2, "a": 1}])
        second = manifest_hash([{"a": 1, "b": 2}])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

