"""Safe, machine-readable runtime health derived from retained artifacts.

This module is intentionally read-only.  It never promotes a model, starts a
job, or treats a missing artifact as evidence of a successful run.  Consumers
(a workflow monitor, an API, or a future page) can use the returned mapping
without having to know the layout of the daily-report or relay artifacts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


STANDARD_MARKETS = (
    "match_result",
    "handicap_result",
    "correct_score",
    "total_goals",
    "half_full",
)
UNKNOWN_MODEL_STATE = "UNKNOWN"


def build_health_report(
    daily_dir: str | Path,
    *,
    relay_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build a non-throwing health DTO from the newest readable artifacts.

    ``daily_dir`` is the directory containing ``report-*.json`` outputs.
    ``relay_dir`` optionally contains the local ``last-success.json`` written
    by ``run_relay_task.ps1``.  Corrupt, absent, or timestamp-less files are
    exposed as unavailable inputs rather than raising an exception.
    """
    observed_at = _utc(now or datetime.now(UTC))
    daily_path, daily_report = _latest_daily_report(Path(daily_dir))
    relay_path = Path(relay_dir) / "last-success.json" if relay_dir is not None else None
    relay_record = _read_mapping(relay_path)

    source_as_of = _timestamp(daily_report.get("source_as_of")) if daily_report else None
    source_age_seconds = (
        max(0, int((observed_at - source_as_of).total_seconds()))
        if source_as_of is not None else None
    )
    model_state = str(daily_report.get("model_state", UNKNOWN_MODEL_STATE)) if daily_report else UNKNOWN_MODEL_STATE
    fixtures = _fixture_list(daily_report)
    quality = _fixture_market_quality(fixtures)

    daily_generated = _timestamp(daily_report.get("generated_at")) if daily_report else None
    relay_completed = _timestamp(relay_record.get("completed_at")) if relay_record else None
    warnings: list[str] = []
    if daily_report is None:
        warnings.append("daily_report_unavailable")
    if relay_dir is not None and relay_record is None:
        warnings.append("relay_last_success_unavailable")
    if source_as_of is None:
        warnings.append("source_timestamp_unavailable")
    if quality["fixture_count"] == 0:
        warnings.append("fixture_markets_unavailable")

    input_state = "available" if daily_report is not None else "unavailable"
    status = "healthy" if not warnings else "degraded" if daily_report is not None else "unavailable"
    return {
        "schema_version": 1,
        "generated_at": observed_at.isoformat(),
        "status": status,
        "current_model_status": {"value": model_state, "source": "daily_report" if daily_report else "unavailable"},
        "last_success": {
            "daily_report": daily_generated.isoformat() if daily_generated else None,
            "relay": relay_completed.isoformat() if relay_completed else None,
        },
        "source_age_seconds": source_age_seconds,
        "fixture_market_quality": quality,
        "inputs": {
            "daily_report": {"status": input_state, "path": str(daily_path) if daily_path else None},
            "relay_last_success": {
                "status": "available" if relay_record is not None else "unavailable",
                "path": str(relay_path) if relay_path is not None else None,
            },
        },
        "warnings": warnings,
    }


def _latest_daily_report(directory: Path) -> tuple[Path | None, Mapping[str, Any] | None]:
    if not directory.is_dir():
        return None, None
    candidates: list[tuple[datetime, Path, Mapping[str, Any]]] = []
    for path in directory.glob("report-*.json"):
        record = _read_mapping(path)
        if record is None:
            continue
        # ``generated_at`` is preferred so copying an artifact does not make it
        # look newer; modification time is only a stable fallback.
        timestamp = _timestamp(record.get("generated_at"))
        if timestamp is None:
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        candidates.append((timestamp, path, record))
    if not candidates:
        return None, None
    _, path, record = max(candidates, key=lambda item: (item[0], item[1].name))
    return path, record


def _fixture_list(report: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if report is None:
        return []
    fixtures = report.get("fixture_details")
    return [item for item in fixtures if isinstance(item, Mapping)] if isinstance(fixtures, list) else []


def _fixture_market_quality(fixtures: list[Mapping[str, Any]]) -> dict[str, object]:
    present = {market: 0 for market in STANDARD_MARKETS}
    any_market = complete = 0
    for fixture in fixtures:
        odds = fixture.get("odds")
        odds = odds if isinstance(odds, Mapping) else {}
        available = [market for market in STANDARD_MARKETS if isinstance(odds.get(market), Mapping) and odds[market]]
        if available:
            any_market += 1
        if len(available) == len(STANDARD_MARKETS):
            complete += 1
        for market in available:
            present[market] += 1
    count = len(fixtures)
    return {
        "fixture_count": count,
        "fixtures_with_any_market": any_market,
        "fixtures_with_all_standard_markets": complete,
        "market_coverage": {
            market: {"available_fixtures": present[market], "missing_fixtures": count - present[market]}
            for market in STANDARD_MARKETS
        },
    }


def _read_mapping(path: Path | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed) if parsed.tzinfo is not None else None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("health report timestamps must be timezone-aware")
    return value.astimezone(UTC)
