"""Strict offline JSON and CSV fallback importers."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from .football_data import MATCH_FIELDS


class ManualImportError(ValueError):
    """Raised when manually supplied data violates the match contract."""


def _normalize(record: Mapping[str, object], index: int) -> dict[str, object]:
    missing = [field for field in MATCH_FIELDS if field not in record or record[field] in (None, "")]
    if missing:
        raise ManualImportError(f"record {index}: missing fields: {', '.join(missing)}")
    unknown = set(record) - set(MATCH_FIELDS)
    if unknown:
        raise ManualImportError(f"record {index}: unknown fields: {', '.join(sorted(unknown))}")
    result = {field: record[field] for field in MATCH_FIELDS}
    try:
        parsed = datetime.fromisoformat(str(result["kickoff_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManualImportError(f"record {index}: invalid kickoff_utc") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ManualImportError(f"record {index}: kickoff_utc must explicitly be UTC")
    result["kickoff_utc"] = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        result["home_goals"] = int(str(result["home_goals"]))
        result["away_goals"] = int(str(result["away_goals"]))
    except ValueError as exc:
        raise ManualImportError(f"record {index}: goals must be integers") from exc
    if result["home_goals"] < 0 or result["away_goals"] < 0:
        raise ManualImportError(f"record {index}: goals cannot be negative")
    for field in ("provider_match_id", "competition", "season", "home_team", "away_team"):
        result[field] = str(result[field]).strip()
        if not result[field]:
            raise ManualImportError(f"record {index}: {field} cannot be blank")
    return result


def normalize_manual_records(records: Iterable[Mapping[str, object]]) -> Iterator[dict[str, object]]:
    for index, record in enumerate(records, start=1):
        yield _normalize(record, index)


def load_manual_json(path: str | Path) -> Iterator[dict[str, object]]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ManualImportError("JSON root must be a list of match objects")
    yield from normalize_manual_records(payload)


def load_manual_csv(path: str | Path) -> Iterator[dict[str, object]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ManualImportError("CSV has no header")
        yield from normalize_manual_records(reader)
