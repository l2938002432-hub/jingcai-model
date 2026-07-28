import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from jingcai.official_archive import ArchiveError, ImmutablePayloadArchive


class OfficialArchiveTests(unittest.TestCase):
    def test_normalized_payload_is_idempotent_and_hash_chained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = ImmutablePayloadArchive(directory)
            when = datetime(2026, 7, 28, 10, tzinfo=UTC)
            first = archive.append("fixed_bonus", request_params={"match_id": "1"}, retrieved_at=when, payload={"success": True})
            second = archive.append("fixed_bonus", request_params={"match_id": "1"}, retrieved_at=when, payload={"success": True})
            self.assertEqual(first, second)
            self.assertTrue((Path(directory) / first.relative_path).exists())
            self.assertTrue((Path(directory) / "2026-07-28" / "index.jsonl").exists())

    def test_wire_bytes_are_preserved_and_unsafe_paths_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = ImmutablePayloadArchive(directory)
            receipt = archive.append("results", request_params={}, retrieved_at=datetime.now(UTC), raw_bytes=b'{"a": 1}')
            self.assertEqual(b'{"a": 1}', (Path(directory) / receipt.relative_path).read_bytes())
            with self.assertRaises(ArchiveError):
                archive.append("../escape", request_params={}, retrieved_at=datetime.now(UTC), payload={"a": 1})
            with self.assertRaises(ArchiveError):
                archive.append("results", request_params={}, retrieved_at=datetime.now(UTC), payload={"a": 1}, raw_bytes=b"{}")
