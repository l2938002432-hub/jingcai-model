"""Offline importer for Football-Data.co.uk result CSV files."""

from __future__ import annotations

import csv
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Iterator

MATCH_FIELDS = (
    "provider_match_id",
    "competition",
    "season",
    "kickoff_utc",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
)


class FootballDataError(ValueError):
    """Raised when a Football-Data row cannot be imported safely."""


def _required(row: dict[str, str | None], name: str, row_number: int) -> str:
    value = (row.get(name) or "").strip()
    if not value:
        raise FootballDataError(f"row {row_number}: missing required column {name}")
    return value


def _parse_kickoff(date: str, time: str, source_timezone: tzinfo) -> str:
    text = f"{date} {time or '00:00'}"
    formats = ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M", "%d/%m/%Y %H.%M", "%d/%m/%y %H.%M")
    for fmt in formats:
        try:
            local = datetime.strptime(text, fmt).replace(tzinfo=source_timezone)
            return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    raise FootballDataError(f"unsupported kickoff date/time: {text!r}")


def load_football_data_csv(
    path: str | Path,
    *,
    season: str,
    competition: str | None = None,
    source_timezone: tzinfo = timezone.utc,
) -> Iterator[dict[str, object]]:
    """Yield normalized matches from a local Football-Data CSV.

    Football-Data dates are local to the competition. Callers should pass the
    competition's timezone; UTC is deliberately only a deterministic fallback.
    """

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise FootballDataError("CSV has no header")
        for row_number, row in enumerate(reader, start=2):
            home = _required(row, "HomeTeam", row_number)
            away = _required(row, "AwayTeam", row_number)
            date = _required(row, "Date", row_number)
            league = (competition or row.get("Div") or "").strip()
            if not league:
                raise FootballDataError(f"row {row_number}: missing competition/Div")
            provider_id = (row.get("MatchID") or "").strip()
            if not provider_id:
                provider_id = f"{league}:{season}:{date}:{home}:{away}"
            try:
                home_goals = int(_required(row, "FTHG", row_number))
                away_goals = int(_required(row, "FTAG", row_number))
            except ValueError as exc:
                raise FootballDataError(f"row {row_number}: goals must be integers") from exc
            if home_goals < 0 or away_goals < 0:
                raise FootballDataError(f"row {row_number}: goals cannot be negative")
            yield {
                "provider_match_id": provider_id,
                "competition": league,
                "season": season,
                "kickoff_utc": _parse_kickoff(date, (row.get("Time") or "").strip(), source_timezone),
                "home_team": home,
                "away_team": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
            }
