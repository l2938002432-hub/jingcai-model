"""Deterministic integrity checks for historical football fixtures.

This module deliberately never guesses whether a numeric date is day-first or
month-first.  A trusted, independent schedule must identify the fixture before
its kickoff can be corrected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from jingcai.identity import TeamAliases


Record = Mapping[str, object]


@dataclass(frozen=True)
class QuarantinedMatch:
    record: dict[str, object]
    reason: str
    candidate_count: int


@dataclass(frozen=True)
class ReconciliationResult:
    corrected: tuple[dict[str, object], ...]
    quarantined: tuple[QuarantinedMatch, ...]


def ambiguous_numeric_date(raw_date: str) -> bool:
    """Return true when ``a/b/yyyy`` admits two distinct valid interpretations."""
    parts = raw_date.strip().split()[0].replace("-", "/").split("/")
    if len(parts) != 3 or len(parts[0]) == 4:
        return False
    try:
        first, second, year = map(int, parts)
        day_first = datetime(year, second, first)
        month_first = datetime(year, first, second)
    except ValueError:
        return False
    return day_first.date() != month_first.date()


def detect_date_risks(records: Iterable[Record]) -> tuple[dict[str, object], ...]:
    """Return records whose retained raw date is vulnerable to day/month mixing."""
    risky = []
    for record in records:
        raw = record.get("source_match_date") or record.get("raw_match_date")
        if raw is not None and ambiguous_numeric_date(str(raw)):
            risky.append(dict(record))
    return tuple(sorted(risky, key=_stable_record_key))


def reconcile_with_schedule(
    history: Iterable[Record],
    schedule: Iterable[Record],
    *,
    aliases: TeamAliases | None = None,
) -> ReconciliationResult:
    """Correct history kickoffs only where a trusted schedule matches uniquely.

    Identity is deliberately strict: competition, season, ordered teams and the
    90-minute score must all agree. Missing and duplicate schedule matches are
    quarantined instead of guessed.
    """
    index: dict[tuple[str, ...], list[Record]] = {}
    for reference in schedule:
        index.setdefault(_identity(reference, aliases), []).append(reference)

    corrected: list[dict[str, object]] = []
    quarantined: list[QuarantinedMatch] = []
    for source in sorted((dict(row) for row in history), key=_stable_record_key):
        candidates = index.get(_identity(source, aliases), [])
        if len(candidates) != 1:
            reason = "schedule_match_not_found" if not candidates else "schedule_match_ambiguous"
            quarantined.append(QuarantinedMatch(source, reason, len(candidates)))
            continue
        reference = candidates[0]
        kickoff_utc = reference.get("kickoff_utc")
        kickoff_date = reference.get("kickoff_date")
        if not kickoff_utc and not kickoff_date:
            quarantined.append(QuarantinedMatch(source, "schedule_kickoff_missing", 1))
            continue
        fixed = dict(source)
        if kickoff_utc:
            fixed["kickoff_utc"] = str(kickoff_utc)
            fixed.pop("kickoff_date", None)
        else:
            fixed["kickoff_date"] = str(kickoff_date)
            fixed.pop("kickoff_utc", None)
        fixed["date_integrity"] = "cross_checked"
        fixed["date_reference_id"] = str(reference.get("provider_match_id", ""))
        corrected.append(fixed)

    corrected.sort(
        key=lambda row: (str(row.get("kickoff_utc") or row.get("kickoff_date")), _stable_record_key(row))
    )
    quarantined.sort(key=lambda item: (_stable_record_key(item.record), item.reason))
    return ReconciliationResult(tuple(corrected), tuple(quarantined))


def _identity(record: Record, aliases: TeamAliases | None = None) -> tuple[str, ...]:
    required = ("competition", "season", "home_team", "away_team", "home_goals", "away_goals")
    missing = [name for name in required if record.get(name) is None]
    if missing:
        raise ValueError(f"record missing identity fields: {', '.join(missing)}")
    return (
        _text(record["competition"]),
        _text(record["season"]),
        _text(aliases.canonical(str(record["home_team"])) if aliases else record["home_team"]),
        _text(aliases.canonical(str(record["away_team"])) if aliases else record["away_team"]),
        str(int(record["home_goals"])),
        str(int(record["away_goals"])),
    )


def _text(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _stable_record_key(record: Record) -> tuple[str, ...]:
    return (
        str(record.get("provider_match_id", "")),
        str(record.get("competition", "")),
        str(record.get("season", "")),
        str(record.get("home_team", "")),
        str(record.get("away_team", "")),
        str(record.get("home_goals", "")),
        str(record.get("away_goals", "")),
    )
