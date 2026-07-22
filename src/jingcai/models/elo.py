"""Chronologically updated Elo baseline converted to a score distribution."""

from __future__ import annotations

import math
from typing import Any, Iterable

from .poisson import field, match_values, normalize, poisson_probabilities


class EloModel:
    def __init__(self, k_factor: float = 20.0, home_advantage: float = 65.0) -> None:
        self.k_factor = float(k_factor)
        self.home_advantage = float(home_advantage)
        self.ratings: dict[str, float] = {}
        self.history: list[tuple[Any, str, str]] = []
        self._fitted = False

    def fit(self, matches: Iterable[Any]) -> "EloModel":
        materialized = list(matches)
        if not materialized:
            raise ValueError("at least one completed match is required")
        try:
            materialized.sort(key=lambda m: field(m, "kickoff", "date", "timestamp"))
        except ValueError:
            pass  # Caller order is chronological when no timestamp is supplied.
        self.ratings = {}
        self.history = []
        total_home = total_away = 0
        for match in materialized:
            home, away, hg, ag = match_values(match)
            rh, ra = self.ratings.get(home, 1500.0), self.ratings.get(away, 1500.0)
            expected = 1.0 / (1.0 + 10.0 ** ((ra - rh - self.home_advantage) / 400.0))
            actual = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
            multiplier = 1.0 + math.log1p(abs(hg - ag))
            change = self.k_factor * multiplier * (actual - expected)
            self.ratings[home], self.ratings[away] = rh + change, ra - change
            try:
                stamp = field(match, "kickoff", "date", "timestamp")
            except ValueError:
                stamp = len(self.history)
            self.history.append((stamp, home, away))
            total_home += hg
            total_away += ag
        self.home_mean = max(0.05, total_home / len(materialized))
        self.away_mean = max(0.05, total_away / len(materialized))
        self._fitted = True
        return self

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        if not self._fitted:
            raise RuntimeError("fit must be called before prediction")
        delta = self.ratings.get(home, 1500.0) + self.home_advantage - self.ratings.get(away, 1500.0)
        strength = math.exp(max(-2.0, min(2.0, delta / 400.0)))
        return self.home_mean * math.sqrt(strength), self.away_mean / math.sqrt(strength)

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10) -> list[list[float]]:
        home_rate, away_rate = self.expected_goals(home, away)
        hp, ap = poisson_probabilities(home_rate, max_goals), poisson_probabilities(away_rate, max_goals)
        return normalize([[h * a for a in ap] for h in hp])
