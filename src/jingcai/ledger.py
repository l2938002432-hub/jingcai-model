"""Append-only model and personal ledgers with deterministic release freezing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from jingcai.storage import AppendOnlyJsonlStore


class LedgerKind(str, Enum):
    MODEL = "model"
    PERSONAL = "personal"


class LedgerEventType(str, Enum):
    RELEASED = "released"
    PURCHASE_CONFIRMED = "purchase_confirmed"
    CORRECTED = "corrected"
    RESULT_RECORDED = "result_recorded"
    SETTLED = "settled"
    SETTLEMENT_REVERSED = "settlement_reversed"


_ALLOWED_EVENTS = {
    LedgerKind.MODEL: {
        LedgerEventType.RELEASED,
        LedgerEventType.RESULT_RECORDED,
        LedgerEventType.SETTLED,
        LedgerEventType.SETTLEMENT_REVERSED,
    },
    LedgerKind.PERSONAL: {
        LedgerEventType.PURCHASE_CONFIRMED,
        LedgerEventType.CORRECTED,
        LedgerEventType.RESULT_RECORDED,
        LedgerEventType.SETTLED,
        LedgerEventType.SETTLEMENT_REVERSED,
    },
}


def _aware_iso(value: datetime, name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.isoformat()


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    idempotency_key: str
    published_at: datetime
    source_as_of: datetime
    snapshot_sha256: str
    model_version: str
    config_sha256: str
    rules_version: str
    git_sha: str
    candidates: tuple[Mapping[str, Any], ...]
    tickets: tuple[Mapping[str, Any], ...] = ()

    def to_record(self) -> dict[str, Any]:
        if not self.release_id or not self.idempotency_key:
            raise ValueError("release identifiers are required")
        for value, name in (
            (self.snapshot_sha256, "snapshot_sha256"),
            (self.config_sha256, "config_sha256"),
        ):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        record = asdict(self)
        record["published_at"] = _aware_iso(self.published_at, "published_at")
        record["source_as_of"] = _aware_iso(self.source_as_of, "source_as_of")
        record["candidates"] = [dict(item) for item in self.candidates]
        record["tickets"] = [dict(item) for item in self.tickets]
        return record


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    ledger_kind: LedgerKind
    event_type: LedgerEventType
    aggregate_id: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    reason: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ledger_kind": self.ledger_kind.value,
            "event_type": self.event_type.value,
            "aggregate_id": self.aggregate_id,
            "occurred_at": _aware_iso(self.occurred_at, "occurred_at"),
            "payload": dict(self.payload),
            "reason": self.reason,
        }


class Ledger:
    def __init__(self, path: str | Path, kind: LedgerKind) -> None:
        self.kind = kind
        self.store = AppendOnlyJsonlStore(path)

    def append_event(self, event: LedgerEvent, *, idempotency_key: str) -> str:
        if event.ledger_kind is not self.kind:
            raise ValueError("event cannot be written to a different ledger kind")
        if event.event_type not in _ALLOWED_EVENTS[self.kind]:
            raise ValueError(f"{event.event_type.value} is forbidden in {self.kind.value} ledger")
        return self.store.append_once(idempotency_key, event.to_record())

    def read_events(self) -> list[dict[str, Any]]:
        records = self.store.read_verified()
        if any(record.get("ledger_kind") != self.kind.value for record in records):
            raise ValueError("ledger contains an event from another ledger kind")
        return records


def deterministic_event_id(kind: LedgerKind, event_type: LedgerEventType, key: str) -> str:
    """Return a stable event identity suitable for retryable writers."""
    material = f"{kind.value}:{event_type.value}:{key}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def freeze_release(model_ledger: Ledger, manifest: ReleaseManifest) -> str:
    if model_ledger.kind is not LedgerKind.MODEL:
        raise ValueError("releases can only be frozen in the model ledger")
    payload = manifest.to_record()
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_id = hashlib.sha256(f"release:{stable}".encode("utf-8")).hexdigest()
    event = LedgerEvent(
        event_id=event_id,
        ledger_kind=LedgerKind.MODEL,
        event_type=LedgerEventType.RELEASED,
        aggregate_id=manifest.release_id,
        occurred_at=manifest.published_at,
        payload={"manifest": payload},
    )
    return model_ledger.append_event(
        event, idempotency_key=f"release:{manifest.idempotency_key}"
    )
