import base64
import gzip
import hashlib
import json
import unittest

from jingcai.snapshot_relay import SnapshotRelayError, decode_snapshot, encode_snapshot


PAYLOAD = {
    "success": True,
    "value": {"lastUpdateTime": "2026-07-26T10:20:00+08:00", "matchInfoList": []},
}


class SnapshotRelayTests(unittest.TestCase):
    def test_round_trip_and_digest(self) -> None:
        encoded, digest = encode_snapshot(PAYLOAD)
        self.assertEqual(decode_snapshot(encoded, digest), PAYLOAD)
        self.assertLess(len(encoded), 60_000)

    def test_rejects_tampered_digest(self) -> None:
        encoded, _ = encode_snapshot(PAYLOAD)
        with self.assertRaisesRegex(SnapshotRelayError, "mismatch"):
            decode_snapshot(encoded, "0" * 64)

    def test_rejects_invalid_schema(self) -> None:
        raw = json.dumps({"success": False}).encode()
        encoded = base64.b64encode(gzip.compress(raw)).decode()
        with self.assertRaises(Exception):
            decode_snapshot(encoded, hashlib.sha256(raw).hexdigest())

    def test_rejects_oversized_encoded_input_before_decode(self) -> None:
        with self.assertRaisesRegex(SnapshotRelayError, "oversized"):
            decode_snapshot("A" * 60_001, "0" * 64)


if __name__ == "__main__":
    unittest.main()
