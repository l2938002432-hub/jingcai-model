"""Independent Poisson score model with smoothed team attack/defence effects."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any, Iterable


def field(match: Any, *names: str) -> Any:
    for name in names:
        if isinstance(match, dict) and name in match:
            return match[name]
        if hasattr(match, name):
            return getattr(match, name)
    raise ValueError(f"match is missing one of: {', '.join(names)}")


def match_values(match: Any) -> tuple[str, str, int, int]:
    return (
        str(field(match, "home", "home_team")),
        str(field(match, "away", "away_team")),
        int(field(match, "home_goals", "home_score")),
        int(field(match, "away_goals", "away_score")),
    )


def match_timestamp(match: Any) -> float:
    """Return a deterministic chronological key without trusting caller order."""
    value = field(match, "kickoff_utc", "kickoff_date", "kickoff", "date", "timestamp")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    elif isinstance(value, (int, float)):
        return float(value)
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("match timestamp cannot be empty")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid match timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)  # Ordering only; not a claim about source timezone.
    return parsed.astimezone(UTC).timestamp()


def poisson_probabilities(rate: float, max_goals: int) -> list[float]:
    if max_goals < 1:
        raise ValueError("max_goals must be at least 1")
    rate = max(0.01, min(float(rate), 10.0))
    result = [math.exp(-rate)]
    for goals in range(1, max_goals):
        result.append(result[-1] * rate / goals)
    # The final bucket includes every score at or above max_goals.
    result.append(max(0.0, 1.0 - sum(result)))
    return result


def normalize(matrix: list[list[float]]) -> list[list[float]]:
    clean = [[max(0.0, float(value)) for value in row] for row in matrix]
    total = sum(map(sum, clean))
    if not math.isfinite(total) or total <= 0:
        raise ValueError("score matrix has no finite probability mass")
    return [[value / total for value in row] for row in clean]


class PoissonModel:
    """Estimate expected goals from shrinkage-smoothed home/away team rates."""

    def __init__(self, prior_matches: float = 5.0) -> None:
        self.prior_matches = float(prior_matches)
        self._fitted = False

    def fit(
        self,
        matches: Iterable[Any],
        as_of: Any | None = None,
        half_life_days: float | None = None,
    ) -> "PoissonModel":
        materialized = list(matches)
        if half_life_days is not None and half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        cutoff = None if as_of is None else match_timestamp({"timestamp": as_of})
        if cutoff is None and half_life_days is not None:
            if not materialized:
                raise ValueError("at least one completed match is required")
            cutoff = max(match_timestamp(match) for match in materialized)

        selected: list[Any] = []
        weights: list[float] = []
        for match in materialized:
            timestamp = match_timestamp(match) if cutoff is not None else None
            if cutoff is not None and timestamp is not None and timestamp > cutoff:
                continue
            selected.append(match)
            if half_life_days is None:
                weights.append(1.0)
            else:
                age_days = (cutoff - timestamp) / 86400.0  # type: ignore[operator]
                weights.append(math.exp(-math.log(2.0) * age_days / half_life_days))

        rows = [match_values(match) for match in selected]
        if not rows:
            raise ValueError("at least one completed match is required")
        total_weight = sum(weights)
        self.home_mean = max(0.05, sum(row[2] * weight for row, weight in zip(rows, weights)) / total_weight)
        self.away_mean = max(0.05, sum(row[3] * weight for row, weight in zip(rows, weights)) / total_weight)
        home_for, home_against, home_n = defaultdict(float), defaultdict(float), defaultdict(float)
        away_for, away_against, away_n = defaultdict(float), defaultdict(float), defaultdict(float)
        for (home, away, hg, ag), weight in zip(rows, weights):
            home_for[home] += hg * weight
            home_against[home] += ag * weight
            home_n[home] += weight
            away_for[away] += ag * weight
            away_against[away] += hg * weight
            away_n[away] += weight
        teams = set(home_n) | set(away_n)
        p = self.prior_matches
        self.home_attack, self.home_defence = {}, {}
        self.away_attack, self.away_defence = {}, {}
        for team in teams:
            hn, an = home_n[team], away_n[team]
            self.home_attack[team] = (home_for[team] + p * self.home_mean) / ((hn + p) * self.home_mean)
            self.home_defence[team] = (home_against[team] + p * self.away_mean) / ((hn + p) * self.away_mean)
            self.away_attack[team] = (away_for[team] + p * self.away_mean) / ((an + p) * self.away_mean)
            self.away_defence[team] = (away_against[team] + p * self.home_mean) / ((an + p) * self.home_mean)
        self._fitted = True
        self._fit_matches = selected
        self._fit_weights = weights
        return self

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        if not self._fitted:
            raise RuntimeError("fit must be called before prediction")
        home_rate = self.home_mean * self.home_attack.get(home, 1.0) * self.away_defence.get(away, 1.0)
        away_rate = self.away_mean * self.away_attack.get(away, 1.0) * self.home_defence.get(home, 1.0)
        return max(0.05, home_rate), max(0.05, away_rate)

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10) -> list[list[float]]:
        home_rate, away_rate = self.expected_goals(home, away)
        hp = poisson_probabilities(home_rate, max_goals)
        ap = poisson_probabilities(away_rate, max_goals)
        return normalize([[h * a for a in ap] for h in hp])
