"""Outcome-level calibration kept separate from base-model fitting."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from .poisson import field, match_values, normalize


def outcome_probabilities(matrix: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    home = draw = away = 0.0
    for hg, row in enumerate(matrix):
        for ag, probability in enumerate(row):
            if hg > ag:
                home += probability
            elif hg == ag:
                draw += probability
            else:
                away += probability
    return home, draw, away


class OutcomeCalibrator:
    """Calibrate 1X2 probabilities with three positive multiplicative weights."""

    def __init__(self, smoothing: float = 5.0) -> None:
        self.smoothing = float(smoothing)
        self._fitted = False

    def fit(self, probabilities: Iterable[Sequence[float]], outcomes: Iterable[int]) -> "OutcomeCalibrator":
        rows, labels = list(probabilities), list(outcomes)
        if not rows or len(rows) != len(labels):
            raise ValueError("probabilities and outcomes must be non-empty and equally sized")
        predicted = [0.0, 0.0, 0.0]
        observed = [0.0, 0.0, 0.0]
        for row, label in zip(rows, labels):
            if len(row) != 3 or label not in (0, 1, 2):
                raise ValueError("calibration expects 1X2 rows and labels 0, 1 or 2")
            total = sum(max(0.0, float(v)) for v in row)
            if total <= 0:
                raise ValueError("probability row has no mass")
            for index, value in enumerate(row):
                predicted[index] += max(0.0, float(value)) / total
            observed[label] += 1.0
        prior = self.smoothing
        self.weights = tuple((observed[i] + prior) / (predicted[i] + prior) for i in range(3))
        self._fitted = True
        return self

    def transform(self, probabilities: Sequence[float]) -> tuple[float, float, float]:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        values = [max(0.0, float(p)) * self.weights[i] for i, p in enumerate(probabilities)]
        total = sum(values)
        return tuple(value / total for value in values)  # type: ignore[return-value]


class CalibratedModel:
    """Fit a base model on an earlier window and calibrate on a later holdout."""

    def __init__(self, base_model: Any, calibration_fraction: float = 0.2) -> None:
        if not 0.05 <= calibration_fraction <= 0.5:
            raise ValueError("calibration_fraction must be between 0.05 and 0.5")
        self.base_model = base_model
        self.calibration_fraction = calibration_fraction
        self.calibrator = OutcomeCalibrator()

    def fit(self, matches: Iterable[Any]) -> "CalibratedModel":
        rows = list(matches)
        if len(rows) < 5:
            raise ValueError("at least five matches are required for separated calibration")
        try:
            rows.sort(key=lambda m: field(m, "kickoff", "date", "timestamp"))
        except ValueError:
            pass
        split = max(1, min(len(rows) - 1, round(len(rows) * (1.0 - self.calibration_fraction))))
        self.base_model.fit(rows[:split])
        probabilities, outcomes = [], []
        for match in rows[split:]:
            home, away, hg, ag = match_values(match)
            probabilities.append(outcome_probabilities(self.base_model.predict_score_matrix(home, away)))
            outcomes.append(0 if hg > ag else (1 if hg == ag else 2))
        self.calibrator.fit(probabilities, outcomes)
        return self

    def predict_score_matrix(self, home: str, away: str, max_goals: int = 10) -> list[list[float]]:
        matrix = self.base_model.predict_score_matrix(home, away, max_goals)
        raw = outcome_probabilities(matrix)
        calibrated = self.calibrator.transform(raw)
        factors = [calibrated[i] / raw[i] if raw[i] > 0 else 0.0 for i in range(3)]
        adjusted = []
        for hg, row in enumerate(matrix):
            adjusted.append([p * factors[0 if hg > ag else (1 if hg == ag else 2)] for ag, p in enumerate(row)])
        return normalize(adjusted)
