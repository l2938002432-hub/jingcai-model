"""Import CC0 OpenFootball Champions League qualifier text files."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


class OpenFootballError(ValueError):
    pass


_DATE = re.compile(r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
_MATCH = re.compile(
    r"^\s*(?:(\d{1,2}:\d{2})\s+)?(.+?)\s+v\s+(.+?)\s{2,}(.+?)\s*$"
)
_TEAM = re.compile(r"^(.*?)\s+\(([A-Z]{3})\)$")
_SCORE = re.compile(r"(\d+)-(\d+)")


def _team(value: str) -> str:
    match = _TEAM.match(value.strip())
    return match.group(1).strip() if match else value.strip()


def _regulation_score(value: str) -> tuple[int, int]:
    # For extra-time/penalty matches OpenFootball puts the 90-minute score first
    # inside parentheses, e.g. ``2-1 a.e.t. (1-1, 1-1)``.
    if "a.e.t." in value or "pen." in value:
        parenthesized = re.search(r"\((\d+)-(\d+)", value)
        if parenthesized:
            return int(parenthesized.group(1)), int(parenthesized.group(2))
    scores = _SCORE.search(value)
    if not scores:
        raise OpenFootballError(f"missing score: {value!r}")
    return int(scores.group(1)), int(scores.group(2))


def load_champions_qualifiers(path: str | Path, *, season: str) -> Iterator[dict[str, object]]:
    """Yield normalized completed 90-minute matches from an OpenFootball clq.txt."""
    year = int(season[:4])
    current_date = None
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        date_match = _DATE.match(line)
        if date_match:
            month, day, explicit_year = date_match.groups()
            match_year = int(explicit_year) if explicit_year else year
            current_date = datetime.strptime(f"{match_year} {month} {day}", "%Y %b %d").date()
            continue
        match = _MATCH.match(line)
        if not match:
            continue
        if current_date is None:
            raise OpenFootballError(f"line {line_number}: match before date")
        raw_time, raw_home, raw_away, raw_score = match.groups()
        home, away = _team(raw_home), _team(raw_away)
        home_goals, away_goals = _regulation_score(raw_score)
        kickoff = datetime.combine(
            current_date,
            datetime.strptime(raw_time or "12:00", "%H:%M").time(),
            tzinfo=UTC,
        )
        yield {
            "provider_match_id": f"openfootball:UCLQ:{season}:{current_date}:{home}:{away}",
            "competition": "UCLQ",
            "season": season,
            "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
            "home_team": home,
            "away_team": away,
            "home_goals": home_goals,
            "away_goals": away_goals,
        }
