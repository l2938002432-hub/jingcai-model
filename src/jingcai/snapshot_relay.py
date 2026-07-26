"""Bounded codec for relaying a public Sporttery snapshot through workflow_dispatch."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from typing import Any, Mapping

from jingcai.providers.sporttery import validate_payload

MAX_BASE64_BYTES = 60_000
MAX_COMPRESSED_BYTES = 45_000
MAX_JSON_BYTES = 1_000_000


class SnapshotRelayError(ValueError):
    """The relayed snapshot failed a size, integrity, or schema check."""


def encode_snapshot(payload: Mapping[str, Any]) -> tuple[str, str]:
    validate_payload(payload)
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if len(raw) > MAX_JSON_BYTES:
        raise SnapshotRelayError("snapshot JSON exceeds the 1 MB safety limit")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise SnapshotRelayError("compressed snapshot exceeds the workflow relay limit")
    encoded = base64.b64encode(compressed).decode("ascii")
    if len(encoded) > MAX_BASE64_BYTES:
        raise SnapshotRelayError("encoded snapshot exceeds the workflow input limit")
    return encoded, hashlib.sha256(raw).hexdigest()


def decode_snapshot(encoded: str, expected_sha256: str) -> dict[str, Any]:
    if not encoded or len(encoded) > MAX_BASE64_BYTES:
        raise SnapshotRelayError("missing or oversized encoded snapshot")
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise SnapshotRelayError("snapshot SHA-256 is missing or malformed")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise SnapshotRelayError("snapshot is not valid base64") from exc
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise SnapshotRelayError("compressed snapshot exceeds the safety limit")
    try:
        raw = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise SnapshotRelayError("snapshot is not valid gzip data") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise SnapshotRelayError("expanded snapshot exceeds the 1 MB safety limit")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise SnapshotRelayError("snapshot SHA-256 mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotRelayError("snapshot is not valid UTF-8 JSON") from exc
    validate_payload(payload)
    return payload
