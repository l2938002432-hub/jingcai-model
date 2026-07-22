"""Derive nine half-time/full-time probabilities from expected goal rates."""

from __future__ import annotations

from typing import Any, Iterable

from .poisson import normalize, poisson_probabilities


LABELS = ("HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA")


def result_index(home: int, away: int) -> int:
    return 0 if home > away else (1 if home == away else 2)


class HalfFullModel:
    def __init__(self, base_model: Any, first_half_share: float = 0.45) -> None:
        if not 0.0 < first_half_share < 1.0:
            raise ValueError("first_half_share must be between zero and one")
        self.base_model = base_model
        self.first_half_share = first_half_share

    def fit(self, matches: Iterable[Any]) -> "HalfFullModel":
        self.base_model.fit(matches)
        return self

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10) -> list[list[float]]:
        if not hasattr(self.base_model, "expected_goals"):
            raise TypeError("base model must expose expected_goals for half/full prediction")
        lh, la = self.base_model.expected_goals(home, away)
        share = self.first_half_share
        h1, a1 = poisson_probabilities(lh * share, max_goals), poisson_probabilities(la * share, max_goals)
        h2, a2 = poisson_probabilities(lh * (1.0 - share), max_goals), poisson_probabilities(la * (1.0 - share), max_goals)
        result = [[0.0] * 3 for _ in range(3)]
        for hg1, ph1 in enumerate(h1):
            for ag1, pa1 in enumerate(a1):
                half = result_index(hg1, ag1)
                for hg2, ph2 in enumerate(h2):
                    for ag2, pa2 in enumerate(a2):
                        full = result_index(hg1 + hg2, ag1 + ag2)
                        result[half][full] += ph1 * pa1 * ph2 * pa2
        return normalize(result)

    def predict_proba(self, home: str, away: str, max_goals: int = 10) -> dict[str, float]:
        matrix = self.predict_score_matrix(home, away, max_goals)
        return {LABELS[h * 3 + f]: matrix[h][f] for h in range(3) for f in range(3)}
