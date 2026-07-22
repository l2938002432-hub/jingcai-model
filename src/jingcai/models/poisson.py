"""Independent Poisson score model with smoothed team attack/defence effects."""

from __future__ import annotations

import math
from collections import defaultdict
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

    def fit(self, matches: Iterable[Any]) -> "PoissonModel":
        rows = [match_values(match) for match in matches]
        if not rows:
            raise ValueError("at least one completed match is required")
        n = len(rows)
        self.home_mean = max(0.05, sum(row[2] for row in rows) / n)
        self.away_mean = max(0.05, sum(row[3] for row in rows) / n)
        home_for, home_against, home_n = defaultdict(float), defaultdict(float), defaultdict(int)
        away_for, away_against, away_n = defaultdict(float), defaultdict(float), defaultdict(int)
        for home, away, hg, ag in rows:
            home_for[home] += hg
            home_against[home] += ag
            home_n[home] += 1
            away_for[away] += ag
            away_against[away] += hg
            away_n[away] += 1
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
