"""Pure point-in-time guards for historical fixed-bonus replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SnapshotSelection:
    snapshot: dict[str, object] | None
    reason: str | None


def select_last_snapshot(
    snapshots: Iterable[Mapping[str, object]],
    *,
    match_id: str,
    market: str,
    decision_at: datetime,
    max_age_seconds: int = 1800,
) -> SnapshotSelection:
    """Select the final published snapshot at or before the decision time.

    ``ingested_at`` is deliberately ignored: historic payloads may be obtained
    after a match, but only the official point timestamp can be used in replay.
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at must be timezone-aware")
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    candidates: list[tuple[datetime, dict[str, object]]] = []
    for source in snapshots:
        if str(source.get("match_id")) != match_id or str(source.get("market")) != market:
            continue
        raw_time = source.get("published_at")
        if not isinstance(raw_time, str):
            return SnapshotSelection(None, "published_at_missing")
        published_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            return SnapshotSelection(None, "published_at_timezone_missing")
        odds = source.get("odds")
        if not isinstance(odds, Mapping) or not odds:
            continue
        if published_at <= decision_at:
            candidates.append((published_at, dict(source)))
    if not candidates:
        return SnapshotSelection(None, "no_snapshot_before_decision")
    candidates.sort(key=lambda item: item[0])
    selected_at, selected = candidates[-1]
    if (decision_at - selected_at).total_seconds() > max_age_seconds:
        return SnapshotSelection(None, "snapshot_stale")
    return SnapshotSelection(selected, None)
