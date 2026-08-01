from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime, timedelta

from jingcai.data_contract import (
    CONTRACT_FIELDS,
    DataContractError,
    canonical_raw_hash,
    summarize_quality,
    with_provenance,
)


class DataContractTests(unittest.TestCase):
    def test_enriches_plain_legacy_record_without_changing_its_fields(self) -> None:
        raw = b'{"match":1}'
        record = with_provenance(
            {"match_id": "1001", "home_team": "A"},
            source="sporttery",
            source_record_id="1001",
            captured_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, 7, 59, tzinfo=UTC),
            raw_bytes=raw,
        )
        self.assertEqual("1001", record["match_id"])
        self.assertEqual("sporttery", record["source"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record["raw_hash"])
        self.assertTrue(all(field in record for field in CONTRACT_FIELDS))

    def test_rejects_untraceable_or_time_travelling_records(self) -> None:
        captured = datetime(2026, 8, 1, 8, tzinfo=UTC)
        common = {"source": "x", "source_record_id": "1", "captured_at": captured}
        with self.assertRaises(DataContractError):
            with_provenance({}, available_at=captured, **common)
        with self.assertRaises(DataContractError):
            with_provenance({}, available_at=captured + timedelta(seconds=1), raw_bytes=b"x", **common)

    def test_quality_summary_accepts_legacy_records_and_counts_each_problem(self) -> None:
        good = with_provenance(
            {"id": "good"}, source="official", source_record_id="good",
            captured_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, 8, tzinfo=UTC), raw_bytes=b"good",
        )
        malformed = dict(good, raw_hash="not-a-hash", captured_at="yesterday")
        summary = summarize_quality([good, {"id": "legacy"}, malformed])
        self.assertEqual(3, summary.record_count)
        self.assertEqual(1, summary.complete_record_count)
        self.assertEqual(1, summary.missing_by_field["source"])
        self.assertEqual(1, summary.invalid_by_field["raw_hash"])
        self.assertEqual(1, summary.invalid_by_field["captured_at"])
        self.assertEqual(2, summary.as_dict()["incomplete_record_count"])

    def test_canonical_hash_is_independent_of_mapping_order(self) -> None:
        self.assertEqual(canonical_raw_hash({"a": 1, "b": 2}), canonical_raw_hash({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
