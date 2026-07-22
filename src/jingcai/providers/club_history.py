"""Importer for the MIT Club Football Match Data cold-start dataset."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Iterator


class ClubHistoryError(ValueError):
    pass


def load_club_history_csv(
    path: str | Path,
    *,
    divisions: set[str] | None = None,
    since: str | None = None,
) -> Iterator[dict[str, object]]:
    """Stream normalized completed matches, optionally filtering division/date."""
    since_date = datetime.fromisoformat(since).date() if since else None
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ClubHistoryError(f"missing columns: {', '.join(sorted(required - set(reader.fieldnames or [])))}")
        for index, row in enumerate(reader, start=2):
            division = row["Division"].strip()
            if divisions and division not in divisions:
                continue
            # The upstream file also contains scheduled fixtures. A pair of
            # blank scores means "not completed", not a corrupt result.
            if not (row["FTHome"] or "").strip() and not (row["FTAway"] or "").strip():
                continue
            try:
                match_date = datetime.fromisoformat(row["MatchDate"].strip()).date()
                if since_date and match_date < since_date:
                    continue
                raw_time = (row.get("MatchTime") or "12:00:00").strip() or "12:00:00"
                match_time = time.fromisoformat(raw_time)
                kickoff = datetime.combine(match_date, match_time, tzinfo=UTC)
                home_score, away_score = float(row["FTHome"]), float(row["FTAway"])
                if not home_score.is_integer() or not away_score.is_integer():
                    raise ValueError("scores must be whole numbers")
                home_goals, away_goals = int(home_score), int(away_score)
            except (TypeError, ValueError) as exc:
                raise ClubHistoryError(f"row {index}: invalid date, time or score") from exc
            if home_goals < 0 or away_goals < 0:
                raise ClubHistoryError(f"row {index}: negative score")
            home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
            if not home or not away:
                raise ClubHistoryError(f"row {index}: blank team")
            yield {
                "provider_match_id": f"club-history:{division}:{match_date}:{home}:{away}",
                "competition": division,
                "season": str(match_date.year),
                "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                "home_team": home,
                "away_team": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                # Retain the source text so downstream integrity checks can
                # detect ambiguous numeric dates instead of silently guessing.
                "source_match_date": row["MatchDate"].strip(),
                **_optional_numeric_fields(row, index),
            }


def _optional_numeric_fields(row: dict[str, str], index: int) -> dict[str, object]:
    """Keep useful pre-match/half-time fields only when the source supplies them."""
    output: dict[str, object] = {}
    for source, target, integer in (
        ("HTHome", "half_home_goals", True),
        ("HTAway", "half_away_goals", True),
        ("HomeElo", "home_elo", False),
        ("AwayElo", "away_elo", False),
    ):
        raw = (row.get(source) or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise ClubHistoryError(f"row {index}: invalid optional field {source}") from exc
        if integer:
            if value < 0 or not value.is_integer():
                raise ClubHistoryError(f"row {index}: invalid optional field {source}")
            output[target] = int(value)
        else:
            output[target] = value
    return output
