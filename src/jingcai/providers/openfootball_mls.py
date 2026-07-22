"""Parse OpenFootball MLS schedules as an independent date reference."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator


class OpenFootballMLSError(ValueError):
    pass


_WEEKDAY = r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE = re.compile(
    rf"^\s*(?:{_WEEKDAY},?\s+)?(?P<month>{_MONTH})[\s/]+(?P<day>\d{{1,2}})(?:,?\s+(?P<year>\d{{4}}))?\s*$",
    re.IGNORECASE,
)
_MATCH = re.compile(
    r"^\s*(?:(?P<time>\d{1,2}:\d{2})\s+)?(?P<home>.+?)\s{1,}v\s{1,}(?P<away>.+?)\s{2,}(?P<score>\d+\s*-\s*\d+)(?:\s+.*)?$",
    re.IGNORECASE,
)


def _season_year(season: str) -> int:
    match = re.match(r"^(\d{4})", season.strip())
    if not match:
        raise OpenFootballMLSError(f"invalid season: {season!r}")
    return int(match.group(1))


def load_mls_matches(path: str | Path, *, season: str) -> Iterator[dict[str, object]]:
    """Yield completed MLS matches from a Football.TXT schedule.

    Date headers, rather than Matchday order, are authoritative.  OpenFootball
    often states the year only on the first date header; later headers inherit
    that year.  The source contains wall-clock times without a timezone, so this
    date-reference importer deliberately emits no UTC timestamp.
    """

    inherited_year = _season_year(season)
    current_date = None
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        # Comments and outlines can contain date-like text, but are not date
        # headers.  In particular, never infer a date from Matchday ordering.
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "=", "▪", "::")):
            continue

        date_match = _DATE.fullmatch(line)
        if date_match:
            if date_match.group("year"):
                inherited_year = int(date_match.group("year"))
            try:
                current_date = datetime.strptime(
                    f"{inherited_year} {date_match.group('month')[:3]} {date_match.group('day')}",
                    "%Y %b %d",
                ).date()
            except ValueError as exc:
                raise OpenFootballMLSError(f"line {line_number}: invalid date") from exc
            continue

        match = _MATCH.fullmatch(line)
        if not match:
            continue
        if current_date is None:
            raise OpenFootballMLSError(f"line {line_number}: match before date")

        home_goals, away_goals = (
            int(value.strip()) for value in match.group("score").split("-", 1)
        )
        yield {
            "competition": "USA",
            "season": season,
            "home_team": match.group("home").strip(),
            "away_team": match.group("away").strip(),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "kickoff_date": current_date.isoformat(),
        }

