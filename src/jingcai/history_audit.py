"""Deterministic coverage audit before any economic backtest is allowed."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from jingcai.point_in_time import select_last_snapshot


MARKETS = ("match_result", "handicap_result", "total_goals", "correct_score", "half_full")


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("time must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("time zone is required")
    return parsed


def audit_history_coverage(
    results: Iterable[Mapping[str, object]],
    points: Iterable[Mapping[str, object]],
    *,
    decision_offset_minutes: int = 105,
    max_snapshot_age_minutes: int = 30,
) -> dict[str, object]:
    """Measure decision-time coverage and quarantine unsafe historical points.

    The function does not compute ROI and cannot turn an incomplete series into
    a trusted data set. A result needs a timezone-aware ``kickoff`` field.
    """
    if decision_offset_minutes <= 0 or max_snapshot_age_minutes < 0:
        raise ValueError("invalid decision policy")
    matches: dict[str, datetime] = {}
    quarantined: list[dict[str, str]] = []
    for result in results:
        match_id = str(result.get("match_id", ""))
        try:
            kickoff = _time(result.get("kickoff"))
            if not match_id or match_id in matches:
                raise ValueError("missing or duplicate match_id")
        except ValueError as exc:
            quarantined.append({"match_id": match_id, "market": "result", "reason": str(exc)})
        else:
            matches[match_id] = kickoff
    valid_points: list[Mapping[str, object]] = []
    last_times: dict[tuple[str, str], datetime] = {}
    for point in points:
        match_id, market = str(point.get("match_id", "")), str(point.get("market", ""))
        try:
            published = _time(point.get("published_at"))
            if match_id not in matches or market not in MARKETS:
                raise ValueError("unknown match or market")
            if published > matches[match_id]:
                raise ValueError("published after kickoff")
            previous = last_times.get((match_id, market))
            if previous and published < previous:
                raise ValueError("non-monotonic published time")
            last_times[(match_id, market)] = published
            valid_points.append(point)
        except ValueError as exc:
            quarantined.append({"match_id": match_id, "market": market, "reason": str(exc)})
    coverage: dict[str, dict[str, int]] = {market: {"eligible_matches": len(matches), "covered_matches": 0} for market in MARKETS}
    missing: list[dict[str, str]] = []
    for match_id, kickoff in matches.items():
        decision_at = kickoff - timedelta(minutes=decision_offset_minutes)
        for market in MARKETS:
            selected = select_last_snapshot(
                valid_points, match_id=match_id, market=market, decision_at=decision_at,
                max_age_seconds=max_snapshot_age_minutes * 60,
            )
            if selected.snapshot is None:
                missing.append({"match_id": match_id, "market": market, "reason": selected.reason or "unknown"})
            else:
                coverage[market]["covered_matches"] += 1
    for stats in coverage.values():
        eligible = stats["eligible_matches"]
        stats["coverage_percent"] = round(100 * stats["covered_matches"] / eligible, 2) if eligible else 0.0
    return {
        "decision_offset_minutes": decision_offset_minutes,
        "max_snapshot_age_minutes": max_snapshot_age_minutes,
        "result_matches": len(matches), "coverage": coverage,
        "missing_at_decision": missing, "quarantined": quarantined,
        "safe_for_economic_backtest": not quarantined and bool(matches),
    }
