"""Dixon-Coles low-score correction over a fitted Poisson model."""

from __future__ import annotations

import math
from typing import Any, Iterable

from .poisson import PoissonModel, match_values, normalize


class DixonColesModel(PoissonModel):
    def __init__(self, prior_matches: float = 5.0, rho: float | None = None) -> None:
        super().__init__(prior_matches)
        self.fixed_rho = rho
        self.rho = 0.0

    @staticmethod
    def _tau(home_goals: int, away_goals: int, lh: float, la: float, rho: float) -> float:
        if home_goals == 0 and away_goals == 0:
            return 1.0 - lh * la * rho
        if home_goals == 0 and away_goals == 1:
            return 1.0 + lh * rho
        if home_goals == 1 and away_goals == 0:
            return 1.0 + la * rho
        if home_goals == 1 and away_goals == 1:
            return 1.0 - rho
        return 1.0

    def fit(self, matches: Iterable[Any]) -> "DixonColesModel":
        materialized = list(matches)
        super().fit(materialized)
        if self.fixed_rho is not None:
            self.rho = max(-0.2, min(0.2, float(self.fixed_rho)))
            return self
        best_score, best_rho = -math.inf, 0.0
        for step in range(-20, 21):
            rho = step / 100.0
            score = 0.0
            valid = True
            for match in materialized:
                home, away, hg, ag = match_values(match)
                if hg <= 1 and ag <= 1:
                    lh, la = self.expected_goals(home, away)
                    tau = self._tau(hg, ag, lh, la, rho)
                    if tau <= 0:
                        valid = False
                        break
                    score += math.log(tau)
            if valid and score > best_score:
                best_score, best_rho = score, rho
        self.rho = best_rho
        return self

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10) -> list[list[float]]:
        matrix = super().predict_score_matrix(home, away, max_goals)
        lh, la = self.expected_goals(home, away)
        for hg in range(min(2, len(matrix))):
            for ag in range(min(2, len(matrix[hg]))):
                matrix[hg][ag] *= self._tau(hg, ag, lh, la, self.rho)
        return normalize(matrix)
