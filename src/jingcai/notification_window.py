"""Select candidates that are timely enough for a human PAPER_ONLY decision."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any


def _parse_aware(value: object, *, field: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def select_notification_candidates(candidates: Iterable[Mapping[str, Any]], *, observed_at: datetime, minimum_minutes_before_cutoff: int = 60, maximum_minutes_before_cutoff: int = 120, maximum_odds_age_minutes: int = 35) -> list[dict[str, Any]]:
    """Keep only candidates with fresh odds in the pre-cutoff decision window."""
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    if not 0 <= minimum_minutes_before_cutoff <= maximum_minutes_before_cutoff:
        raise ValueError("invalid notification decision window")
    if maximum_odds_age_minutes < 0:
        raise ValueError("maximum_odds_age_minutes must not be negative")
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            cutoff = _parse_aware(candidate["sale_cutoff"], field="sale_cutoff")
            odds_as_of = _parse_aware(candidate["odds_as_of"], field="odds_as_of")
        except (KeyError, TypeError, ValueError):
            continue
        minutes = (cutoff - observed_at).total_seconds() / 60
        odds_age = (observed_at - odds_as_of).total_seconds() / 60
        if minimum_minutes_before_cutoff <= minutes <= maximum_minutes_before_cutoff and 0 <= odds_age <= maximum_odds_age_minutes:
            selected.append(dict(candidate))
    return selected
