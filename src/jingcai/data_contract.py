"""Record-level provenance contract and non-blocking data quality summaries.

The project has multiple providers and historical imports.  This module gives
their *consumable* records one common, minimal lineage envelope without forcing
callers to migrate all existing files in one change.  New writers should use
``with_provenance``; readers can use ``summarize_quality`` to safely expose
missing contract fields in a health report.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping


CONTRACT_FIELDS = (
    "source",
    "source_record_id",
    "captured_at",
    "available_at",
    "raw_hash",
    "schema_version",
)
DEFAULT_SCHEMA_VERSION = "1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DataContractError(ValueError):
    """Raised when a newly-produced record cannot meet the provenance contract."""


@dataclass(frozen=True)
class DataQualitySummary:
    """A deterministic, non-throwing quality report for a record collection."""

    record_count: int
    complete_record_count: int
    missing_by_field: Mapping[str, int]
    invalid_by_field: Mapping[str, int]

    @property
    def incomplete_record_count(self) -> int:
        return self.record_count - self.complete_record_count

    def as_dict(self) -> dict[str, object]:
        return {
            "record_count": self.record_count,
            "complete_record_count": self.complete_record_count,
            "incomplete_record_count": self.incomplete_record_count,
            "missing_by_field": dict(self.missing_by_field),
            "invalid_by_field": dict(self.invalid_by_field),
        }


def with_provenance(
    record: Mapping[str, Any],
    *,
    source: str,
    source_record_id: str,
    captured_at: datetime,
    available_at: datetime,
    raw_bytes: bytes | None = None,
    raw_hash: str | None = None,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return a copy of ``record`` enriched with the required provenance fields.

    Either the original wire bytes or a precomputed SHA-256 must be retained.
    This deliberately returns a plain dict, preserving compatibility with the
    project's existing provider and JSON contracts.
    """
    if (raw_bytes is None) == (raw_hash is None):
        raise DataContractError("provide exactly one of raw_bytes or raw_hash")
    captured = _timestamp(captured_at, "captured_at")
    available = _timestamp(available_at, "available_at")
    if available > captured:
        raise DataContractError("available_at cannot be after captured_at")
    values = {
        "source": _required_text(source, "source"),
        "source_record_id": _required_text(source_record_id, "source_record_id"),
        "captured_at": captured,
        "available_at": available,
        "raw_hash": hashlib.sha256(raw_bytes).hexdigest() if raw_bytes is not None else _hash(raw_hash),
        "schema_version": _required_text(schema_version, "schema_version"),
    }
    enriched = dict(record)
    enriched.update(values)
    return enriched


def summarize_quality(records: Iterable[Mapping[str, Any]]) -> DataQualitySummary:
    """Summarize missing/invalid provenance without rejecting legacy records."""
    missing = Counter({field: 0 for field in CONTRACT_FIELDS})
    invalid = Counter({field: 0 for field in CONTRACT_FIELDS})
    total = complete = 0
    for record in records:
        total += 1
        record_complete = True
        for field in CONTRACT_FIELDS:
            value = record.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing[field] += 1
                record_complete = False
            elif not _valid_field(field, value):
                invalid[field] += 1
                record_complete = False
        if record_complete:
            complete += 1
    return DataQualitySummary(total, complete, dict(missing), dict(invalid))


def canonical_raw_hash(payload: Any) -> str:
    """SHA-256 of deterministic JSON for sources where wire bytes are unavailable."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: datetime, name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataContractError(f"{name} must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _required_text(value: str, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise DataContractError(f"{name} is required")
    return text


def _hash(value: str) -> str:
    text = _required_text(value, "raw_hash").lower()
    if not _SHA256.fullmatch(text):
        raise DataContractError("raw_hash must be a lowercase SHA-256 hex digest")
    return text


def _valid_field(field: str, value: object) -> bool:
    if field == "raw_hash":
        return isinstance(value, str) and bool(_SHA256.fullmatch(value.lower()))
    if field in {"captured_at", "available_at"}:
        if not isinstance(value, str):
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    return isinstance(value, str) and bool(value.strip())
