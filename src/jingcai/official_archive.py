"""Immutable archive for official payloads used in later historical replay."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from jingcai.storage import AppendOnlyJsonlStore


class ArchiveError(ValueError):
    """Raised when an archive path or record is unsafe."""


@dataclass(frozen=True)
class ArchiveReceipt:
    payload_sha256: str
    canonical_sha256: str
    relative_path: str
    index_event_hash: str


def _safe_segment(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ArchiveError("endpoint must be a short lowercase identifier")
    return value


class ImmutablePayloadArchive:
    """Content-addressed archive with append-only daily index.

    ``raw_bytes`` is preserved exactly when supplied. Mapping payloads are a
    normalized snapshot and are labelled as such; they are not claimed to be a
    byte-for-byte HTTP response.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def append(
        self,
        endpoint: str,
        *,
        request_params: Mapping[str, object],
        retrieved_at: datetime,
        raw_bytes: bytes | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> ArchiveReceipt:
        if retrieved_at.tzinfo is None:
            raise ArchiveError("retrieved_at must be timezone-aware")
        if (raw_bytes is None) == (payload is None):
            raise ArchiveError("provide exactly one of raw_bytes or payload")
        name = _safe_segment(endpoint)
        if raw_bytes is None:
            raw_bytes = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            representation = "normalized_json"
        else:
            representation = "wire_bytes"
        try:
            decoded = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchiveError("raw payload must be UTF-8 JSON") from exc
        canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_hash = hashlib.sha256(raw_bytes).hexdigest()
        canonical_hash = hashlib.sha256(canonical).hexdigest()
        day = retrieved_at.astimezone(UTC).date().isoformat()
        relative = Path(day) / name / f"{payload_hash}.json"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw_bytes:
                raise ArchiveError("content-addressed payload collision")
        else:
            with path.open("xb") as handle:
                handle.write(raw_bytes)
        params_hash = hashlib.sha256(
            json.dumps(request_params, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        record = {
            "endpoint": name, "request_params_sha256": params_hash,
            "payload_sha256": payload_hash, "canonical_sha256": canonical_hash,
            "retrieved_at": retrieved_at.astimezone(UTC).isoformat(),
            "relative_path": relative.as_posix(), "representation": representation,
        }
        key = f"{name}:{params_hash}:{payload_hash}"
        event_hash = AppendOnlyJsonlStore(self.root / day / "index.jsonl").append_once(key, record)
        return ArchiveReceipt(payload_hash, canonical_hash, relative.as_posix(), event_hash)
