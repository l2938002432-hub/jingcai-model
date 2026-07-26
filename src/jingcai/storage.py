from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


GENESIS_HASH = "0" * 64


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()


def _event_hash(sequence: int, previous_hash: str, record: Mapping[str, Any]) -> str:
    body = {"sequence": sequence, "previous_hash": previous_hash, "record": dict(record)}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


class AppendOnlyJsonlStore:
    """Versioned hash-chain JSONL store.

    Version 2 envelopes link every record to its predecessor, so deletion,
    insertion, reordering and modification are detected. Legacy version 1
    files remain readable, but must be migrated before appending.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _verified_envelopes(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        envelopes: list[dict[str, Any]] = []
        expected_previous = GENESIS_HASH
        version: int | None = None
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                envelope = json.loads(line)
                record = envelope["record"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid envelope at line {line_number}") from exc
            current_version = int(envelope.get("schema_version", 1))
            if version is None:
                version = current_version
            if current_version != version:
                raise ValueError("mixed ledger envelope versions are forbidden")
            if current_version == 1:
                if _record_hash(record) != envelope.get("sha256"):
                    raise ValueError(f"checksum mismatch at line {line_number}")
            elif current_version == 2:
                sequence = envelope.get("sequence")
                previous_hash = envelope.get("previous_hash")
                if sequence != line_number:
                    raise ValueError(f"sequence mismatch at line {line_number}")
                if previous_hash != expected_previous:
                    raise ValueError(f"chain mismatch at line {line_number}")
                actual = _event_hash(sequence, previous_hash, record)
                if actual != envelope.get("event_hash"):
                    raise ValueError(f"checksum mismatch at line {line_number}")
                expected_previous = actual
            else:
                raise ValueError(f"unsupported envelope version at line {line_number}")
            envelopes.append(envelope)
        return envelopes

    def append(self, record: Mapping[str, Any]) -> str:
        envelopes = self._verified_envelopes()
        if envelopes and int(envelopes[0].get("schema_version", 1)) != 2:
            raise ValueError("legacy ledger must be migrated before appending")
        sequence = len(envelopes) + 1
        previous_hash = envelopes[-1]["event_hash"] if envelopes else GENESIS_HASH
        event_hash = _event_hash(sequence, previous_hash, record)
        envelope = {
            "schema_version": 2,
            "sequence": sequence,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
            "record": dict(record),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
        return event_hash

    def append_once(self, idempotency_key: str, record: Mapping[str, Any]) -> str:
        """Append once, returning the original hash on an identical retry."""
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        candidate = dict(record)
        candidate["idempotency_key"] = idempotency_key
        matches = [
            envelope for envelope in self._verified_envelopes()
            if envelope["record"].get("idempotency_key") == idempotency_key
        ]
        if len(matches) > 1:
            raise ValueError(f"duplicate idempotency key in ledger: {idempotency_key}")
        if matches:
            existing = matches[0]
            if _canonical(existing["record"]) != _canonical(candidate):
                raise ValueError(f"idempotency conflict: {idempotency_key}")
            return str(existing.get("event_hash") or existing.get("sha256"))
        return self.append(candidate)

    def read_verified(self) -> list[dict[str, Any]]:
        return [dict(envelope["record"]) for envelope in self._verified_envelopes()]


def manifest_hash(records: Iterable[Mapping[str, Any]]) -> str:
    canonical = "\n".join(_canonical(item) for item in records)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
