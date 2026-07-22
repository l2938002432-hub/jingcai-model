"""Point-in-time access to ClubElo historical ratings.

The loader deliberately performs strict ``snapshot_date < match_date`` joins.
It never substitutes a same-day or later observation, so a missing historical
rating fails closed (with an association mean available as an explicit prior).
"""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jingcai.identity import TeamAliases
from jingcai.models.poisson import match_timestamp


class ClubEloHistoryError(ValueError):
    """The source cannot support a safe point-in-time lookup."""


def _date(value: date | datetime | str | float | int) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ClubEloHistoryError("datetime must include a timezone")
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(float(value), timezone.utc).date()
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError) as exc:
        raise ClubEloHistoryError(f"invalid date: {value!r}") from exc


class ClubEloHistory:
    """Immutable, leakage-safe index of ClubElo snapshot history."""

    def __init__(self, rows: Iterable[dict[str, str]], aliases: TeamAliases | None = None) -> None:
        self.aliases = aliases or TeamAliases()
        by_team: dict[str, list[tuple[date, float, str]]] = defaultdict(list)
        seen: set[tuple[str, date]] = set()

        for number, row in enumerate(rows, start=2):
            try:
                snapshot = _date(row["date"])
                raw_club, country = row["club"].strip(), row["country"].strip()
                rating = float(row["elo"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ClubEloHistoryError(f"invalid row {number}") from exc
            if not raw_club or not country or not math.isfinite(rating):
                raise ClubEloHistoryError(f"missing/non-finite value in row {number}")
            club = self.aliases.canonical(raw_club)
            identity = (club, snapshot)
            if identity in seen:
                raise ClubEloHistoryError(f"duplicate snapshot for {raw_club!r} on {snapshot}")
            seen.add(identity)
            by_team[club].append((snapshot, rating, country))

        if not by_team:
            raise ClubEloHistoryError("Elo history is empty")
        self._teams = {team: sorted(values) for team, values in by_team.items()}

    @classmethod
    def from_csv(cls, path: str | Path, aliases: TeamAliases | None = None) -> "ClubEloHistory":
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "club", "country", "elo"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ClubEloHistoryError("Elo CSV must contain date, club, country and elo")
            return cls(reader, aliases)

    def _latest(self, team: str, before: date) -> tuple[date, float, str] | None:
        values = self._teams.get(self.aliases.canonical(team))
        if not values:
            return None
        index = bisect_left([item[0] for item in values], before) - 1
        return None if index < 0 else values[index]

    def rating_before(self, team: str, as_of: date | datetime | str | float | int) -> float:
        cutoff = _date(as_of)
        result = self._latest(team, cutoff)
        if result is None:
            raise ClubEloHistoryError(f"no snapshot for {team!r} before {cutoff}")
        return result[1]

    def association_priors(self, as_of: date | datetime | str | float | int) -> dict[str, float]:
        """Return means over each club's latest visible snapshot, not all rows."""
        cutoff = _date(as_of)
        grouped: dict[str, list[float]] = defaultdict(list)
        for values in self._teams.values():
            index = bisect_left([item[0] for item in values], cutoff) - 1
            if index >= 0:
                _, rating, country = values[index]
                grouped[country].append(rating)
        if not grouped:
            raise ClubEloHistoryError(f"no association snapshots before {cutoff}")
        return {country: sum(values) / len(values) for country, values in grouped.items()}

    def prior_provider(self, match: Any, team: str, association: str | None) -> float:
        """Adapter for :meth:`ClubEloModel.fit`, with association fallback."""
        cutoff = _date(match_timestamp(match))
        direct = self._latest(team, cutoff)
        if direct is not None:
            return direct[1]
        if not association:
            raise ClubEloHistoryError(f"no team snapshot and no association for {team!r}")
        priors = self.association_priors(cutoff)
        if association not in priors:
            raise ClubEloHistoryError(f"no prior for association {association!r} before {cutoff}")
        return priors[association]

    __call__ = prior_provider
