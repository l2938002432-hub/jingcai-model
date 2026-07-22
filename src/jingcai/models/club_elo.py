"""Leakage-safe global club Elo with caller-supplied cold-start priors."""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Mapping

from .poisson import field, match_timestamp, match_values, normalize, poisson_probabilities

PriorProvider = Callable[[Any, str, str | None], float | None]


class ClubEloModel:
    """A chronological club Elo suitable for cross-league qualifiers.

    Association priors are deliberately not learned here.  The caller must supply
    the value that was available immediately before each match, which keeps data
    provenance and point-in-time joins outside the model.
    """

    def __init__(
        self,
        k_factor: float = 20.0,
        home_advantage: float = 65.0,
        default_rating: float = 1500.0,
        prior_weight: float = 1.0,
    ) -> None:
        if k_factor <= 0 or prior_weight < 0 or prior_weight > 1:
            raise ValueError("k_factor must be positive and prior_weight must be in [0, 1]")
        self.k_factor = float(k_factor)
        self.home_advantage = float(home_advantage)
        self.default_rating = float(default_rating)
        self.prior_weight = float(prior_weight)
        self.ratings: dict[str, float] = {}
        self.history: list[tuple[float, str, str, float, float]] = []
        self.home_mean = 1.4
        self.away_mean = 1.1
        self._fitted = False

    def _initial_rating(self, prior: float | None) -> float:
        if prior is None:
            return self.default_rating
        value = float(prior)
        if not math.isfinite(value):
            raise ValueError("association prior must be finite")
        return self.default_rating + self.prior_weight * (value - self.default_rating)

    @staticmethod
    def _association(match: Any, side: str) -> str | None:
        try:
            return str(field(match, f"{side}_association", f"{side}_league"))
        except ValueError:
            return None

    def fit(self, matches: Iterable[Any], prior_provider: PriorProvider | None = None) -> "ClubEloModel":
        rows = list(matches)
        if not rows:
            raise ValueError("at least one completed match is required")
        rows.sort(key=match_timestamp)
        self.ratings, self.history = {}, []
        total_home = total_away = 0
        for match in rows:
            home, away, hg, ag = match_values(match)
            hp = prior_provider(match, home, self._association(match, "home")) if prior_provider else None
            ap = prior_provider(match, away, self._association(match, "away")) if prior_provider else None
            rh = self.ratings.setdefault(home, self._initial_rating(hp))
            ra = self.ratings.setdefault(away, self._initial_rating(ap))
            before_h, before_a = rh, ra
            expected = 1.0 / (1.0 + 10.0 ** ((ra - rh - self.home_advantage) / 400.0))
            actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            margin = 1.0 + math.log1p(abs(hg - ag))
            change = self.k_factor * margin * (actual - expected)
            self.ratings[home], self.ratings[away] = rh + change, ra - change
            self.history.append((match_timestamp(match), home, away, before_h, before_a))
            total_home += hg
            total_away += ag
        self.home_mean = max(0.05, total_home / len(rows))
        self.away_mean = max(0.05, total_away / len(rows))
        self._fitted = True
        return self

    def _rating(self, team: str, association: str | None, priors: Mapping[str, float] | None) -> float:
        if team in self.ratings:
            return self.ratings[team]
        prior = None if priors is None or association is None else priors.get(association)
        return self._initial_rating(prior)

    def expected_goals(
        self, home: str, away: str, *, home_association: str | None = None,
        away_association: str | None = None, association_priors: Mapping[str, float] | None = None,
    ) -> tuple[float, float]:
        if not self._fitted:
            raise RuntimeError("fit must be called before prediction")
        rh = self._rating(home, home_association, association_priors)
        ra = self._rating(away, away_association, association_priors)
        strength = math.exp(max(-2.0, min(2.0, (rh + self.home_advantage - ra) / 400.0)))
        return self.home_mean * math.sqrt(strength), self.away_mean / math.sqrt(strength)

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10, **context: Any) -> list[list[float]]:
        home_rate, away_rate = self.expected_goals(home, away, **context)
        hp, ap = poisson_probabilities(home_rate, max_goals), poisson_probabilities(away_rate, max_goals)
        return normalize([[h * a for a in ap] for h in hp])

    def predict_1x2(self, home: str, away: str, **context: Any) -> dict[str, float]:
        matrix = self.predict_score_matrix(home, away, **context)
        result = {"home": 0.0, "draw": 0.0, "away": 0.0}
        for hg, row in enumerate(matrix):
            for ag, probability in enumerate(row):
                result["home" if hg > ag else "draw" if hg == ag else "away"] += probability
        return result
