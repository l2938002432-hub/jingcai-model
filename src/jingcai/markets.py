from __future__ import annotations

from math import isfinite
from typing import Iterable, Mapping

from .domain import Outcome

ScoreMatrix = Mapping[tuple[int, int], float]
HALF_FULL_CATEGORIES = frozenset(f"{a}_{b}" for a in ("home", "draw", "away") for b in ("home", "draw", "away"))
OFFICIAL_CORRECT_SCORES = frozenset(
    {(0, 0), (1, 1), (2, 2), (3, 3)}
    | {(h, a) for h, a in ((1, 0), (2, 0), (2, 1), (3, 0), (3, 1), (3, 2), (4, 0), (4, 1), (4, 2), (5, 0), (5, 1), (5, 2))}
    | {(a, h) for h, a in ((1, 0), (2, 0), (2, 1), (3, 0), (3, 1), (3, 2), (4, 0), (4, 1), (4, 2), (5, 0), (5, 1), (5, 2))}
)


def validate_score_matrix(matrix: ScoreMatrix) -> None:
    if not matrix:
        raise ValueError("score matrix cannot be empty")
    if any(h < 0 or a < 0 for h, a in matrix):
        raise ValueError("scores cannot be negative")
    if any(not isfinite(p) or p < 0 or p > 1 for p in matrix.values()):
        raise ValueError("score matrix contains invalid probabilities")
    if abs(sum(matrix.values()) - 1.0) > 1e-9:
        raise ValueError("score matrix must include tail mass and sum to 1")


def result_1x2(matrix: ScoreMatrix, handicap: int = 0) -> dict[str, float]:
    validate_score_matrix(matrix)
    result = {Outcome.HOME.value: 0.0, Outcome.DRAW.value: 0.0, Outcome.AWAY.value: 0.0}
    for (home, away), probability in matrix.items():
        adjusted = home + handicap - away
        key = Outcome.HOME.value if adjusted > 0 else Outcome.DRAW.value if adjusted == 0 else Outcome.AWAY.value
        result[key] += probability
    return result


def total_goals(matrix: ScoreMatrix, cap: int = 7) -> dict[str, float]:
    validate_score_matrix(matrix)
    if cap < 1:
        raise ValueError("cap must be positive")
    result = {str(i): 0.0 for i in range(cap)} | {f"{cap}+": 0.0}
    for score, probability in matrix.items():
        goals = sum(score)
        result[str(goals) if goals < cap else f"{cap}+"] += probability
    return result


def correct_score(
    matrix: ScoreMatrix,
    offered_scores: Iterable[tuple[int, int]],
) -> dict[str, float]:
    validate_score_matrix(matrix)
    offered = set(offered_scores)
    if any(h < 0 or a < 0 for h, a in offered):
        raise ValueError("offered scores cannot be negative")
    result = {f"{h}:{a}": matrix.get((h, a), 0.0) for h, a in sorted(offered)}
    result.update({Outcome.OTHER_HOME.value: 0.0, Outcome.OTHER_DRAW.value: 0.0, Outcome.OTHER_AWAY.value: 0.0})
    for (home, away), probability in matrix.items():
        if (home, away) in offered:
            continue
        key = Outcome.OTHER_HOME.value if home > away else Outcome.OTHER_DRAW.value if home == away else Outcome.OTHER_AWAY.value
        result[key] += probability
    return result


def validate_half_full(probabilities: Mapping[str, float]) -> None:
    if set(probabilities) != HALF_FULL_CATEGORIES:
        raise ValueError("half-full probabilities must contain exactly the nine categories")
    if any(not isfinite(p) or p < 0 or p > 1 for p in probabilities.values()):
        raise ValueError("invalid half-full probability")
    if abs(sum(probabilities.values()) - 1.0) > 1e-9:
        raise ValueError("half-full probabilities must sum to 1")


def remove_overround(decimal_odds: Mapping[str, float]) -> dict[str, float]:
    if not decimal_odds or any(not isfinite(o) or o <= 1 for o in decimal_odds.values()):
        raise ValueError("decimal odds must be finite and greater than 1")
    implied = {key: 1.0 / value for key, value in decimal_odds.items()}
    total = sum(implied.values())
    return {key: value / total for key, value in implied.items()}


def expected_value(probability: float, decimal_odds: float, safety_margin: float = 0.0) -> float:
    if not isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if not isfinite(decimal_odds) or decimal_odds <= 1:
        raise ValueError("decimal_odds must be finite and greater than 1")
    if not isfinite(safety_margin) or safety_margin < 0:
        raise ValueError("safety_margin must be finite and non-negative")
    return probability * decimal_odds - 1.0 - safety_margin
