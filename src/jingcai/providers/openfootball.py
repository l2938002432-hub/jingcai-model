"""Import CC0 OpenFootball Champions League qualifier text files."""

from __future__ import annotations

import re
from datetime import datetime
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
_ROUND = re.compile(r"(?:^|[^A-Za-z])(?P<round>\d+\.\s*Round|Play-offs)\s*$", re.IGNORECASE)


def _team(value: str) -> tuple[str, str | None]:
    match = _TEAM.match(value.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return value.strip(), None


def _tie_id(season: str, round_name: str, home: str, away: str) -> str:
    teams = sorted((home, away), key=str.casefold)
    return f"openfootball:UCLQ:{season}:{round_name}:{teams[0]}:{teams[1]}"


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
    """Yield normalized completed 90-minute matches from an OpenFootball clq.txt.

    OpenFootball's qualifier files contain a calendar date and, sometimes, a
    wall-clock time, but no timezone.  Consequently ``kickoff_utc`` is kept as
    ``None`` rather than inventing UTC timestamps.  Consumers should use
    ``kickoff_date`` for chronological date-level processing.
    """
    year = int(season[:4])
    current_date = None
    current_round = None
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        round_match = _ROUND.search(line.strip())
        if round_match:
            raw_round = round_match.group("round")
            current_round = "Play-offs" if raw_round.casefold() == "play-offs" else re.sub(r"\s+", " ", raw_round)
            continue
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
        home, home_country = _team(raw_home)
        away, away_country = _team(raw_away)
        home_goals, away_goals = _regulation_score(raw_score)
        round_name = current_round
        tie_id = _tie_id(season, round_name, home, away) if round_name else None
        rows.append({
            "provider_match_id": f"openfootball:UCLQ:{season}:{current_date}:{home}:{away}",
            "competition": "UCLQ",
            "season": season,
            "kickoff_date": current_date.isoformat(),
            "source_kickoff_time": raw_time,
            "source_timezone": None,
            "kickoff_utc": None,
            "round": round_name,
            "tie_id": tie_id,
            "leg": None,
            "home_team": home,
            "away_team": away,
            "home_country_code": home_country,
            "away_country_code": away_country,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "_source_order": line_number,
        })

    # A leg is assigned only when the source contains exactly two meetings for
    # the same teams in the same named round.  A lone or ambiguous meeting is
    # deliberately left unknown.
    ties: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if row["tie_id"] is not None:
            ties.setdefault(str(row["tie_id"]), []).append(row)
    for meetings in ties.values():
        if len(meetings) == 2:
            meetings.sort(key=lambda row: (str(row["kickoff_date"]), int(row["_source_order"])))
            meetings[0]["leg"] = 1
            meetings[1]["leg"] = 2

    for row in rows:
        row.pop("_source_order")
        yield row
