"""Leakage-safe, market-level probability validation.

The caller supplies forecasts made before each match.  Baselines are updated only
after a timestamp batch has been scored, so matches kicking off together cannot
leak their results into one another.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from typing import Any, Iterable, Mapping

from .backtest import ForecastObservation, log_loss
from .markets import OFFICIAL_CORRECT_SCORES, correct_score, result_1x2, total_goals, validate_half_full
from .models.poisson import match_timestamp


MARKETS = ("match_result", "handicap_result", "total_goals", "correct_score", "half_full")


@dataclass(frozen=True)
class MarketValidationResult:
    market: str
    available: bool
    sample_count: int
    model_log_loss: float | None
    baseline_log_loss: float | None
    improvement: float | None
    reason: str | None = None


def _side(home: int, away: int) -> str:
    return "home" if home > away else "draw" if home == away else "away"


def _actuals(row: Mapping[str, Any]) -> dict[str, str]:
    home, away = int(row["home_goals"]), int(row["away_goals"])
    score = (home, away)
    exact = f"{home}:{away}"
    if score not in OFFICIAL_CORRECT_SCORES:
        exact = f"other_{_side(home, away)}"
    actuals = {
        "match_result": _side(home, away),
        "total_goals": str(home + away) if home + away < 7 else "7+",
        "correct_score": exact,
    }
    if row.get("handicap") is not None:
        actuals["handicap_result"] = _side(home + int(row["handicap"]), away)
    half_home, half_away = row.get("half_home_goals"), row.get("half_away_goals")
    if half_home is not None and half_away is not None:
        actuals["half_full"] = f"{_side(int(half_home), int(half_away))}_{_side(home, away)}"
    return actuals


def _matrix(row: Mapping[str, Any]) -> dict[tuple[int, int], float]:
    value = row["score_matrix"]
    if isinstance(value, Mapping):
        return dict(value)
    return {(home, away): probability for home, line in enumerate(value) for away, probability in enumerate(line)}


def _forecasts(row: Mapping[str, Any]) -> dict[str, Mapping[str, float]]:
    matrix = _matrix(row)
    result: dict[str, Mapping[str, float]] = {
        "match_result": result_1x2(matrix),
        "total_goals": total_goals(matrix),
        "correct_score": correct_score(matrix, OFFICIAL_CORRECT_SCORES),
    }
    if row.get("handicap") is not None:
        result["handicap_result"] = result_1x2(matrix, int(row["handicap"]))
    half_full = row.get("half_full_probabilities")
    if half_full is not None:
        validate_half_full(half_full)
        result["half_full"] = half_full
    return result


def validate_markets(
    rows: Iterable[Mapping[str, Any]],
    *,
    smoothing: float = 1.0,
    baseline_history: Iterable[Mapping[str, Any]] = (),
) -> dict[str, MarketValidationResult]:
    """Compare supplied pre-match forecasts with expanding-frequency baselines.

    Required row fields are a supported time field, ``home_goals``,
    ``away_goals`` and ``score_matrix``.  Half/full validation additionally
    requires both half-time goals and explicit ``half_full_probabilities``;
    a full-time score matrix cannot reconstruct a genuine half-time label.
    """
    if smoothing <= 0:
        raise ValueError("smoothing must be positive")
    ordered = sorted(list(rows), key=match_timestamp)
    model: dict[str, list[ForecastObservation]] = {market: [] for market in MARKETS}
    baseline: dict[str, list[ForecastObservation]] = {market: [] for market in MARKETS}
    counts: dict[str, Counter[str]] = {market: Counter() for market in MARKETS}
    for historical in baseline_history:
        for market, actual in _actuals(historical).items():
            counts[market][actual] += 1

    for _, batch_iter in groupby(ordered, key=match_timestamp):
        batch = list(batch_iter)
        pending: list[tuple[str, str]] = []
        for row in batch:
            actuals, forecasts = _actuals(row), _forecasts(row)
            for market, probabilities in forecasts.items():
                actual = actuals.get(market)
                if actual is None:
                    continue
                categories = tuple(probabilities)
                denominator = sum(counts[market][category] + smoothing for category in categories)
                baseline_probabilities = {
                    category: (counts[market][category] + smoothing) / denominator for category in categories
                }
                model[market].append(ForecastObservation(probabilities, actual))
                baseline[market].append(ForecastObservation(baseline_probabilities, actual))
                pending.append((market, actual))
        for market, actual in pending:
            counts[market][actual] += 1

    output: dict[str, MarketValidationResult] = {}
    for market in MARKETS:
        sample_count = len(model[market])
        if not sample_count:
            reason = (
                "half-time labels and explicit half/full forecasts are unavailable; "
                "full-time scores must not be used to infer them"
                if market == "half_full"
                else "no valid observations"
            )
            output[market] = MarketValidationResult(market, False, 0, None, None, None, reason)
            continue
        model_loss, baseline_loss = log_loss(model[market]), log_loss(baseline[market])
        improvement = (baseline_loss - model_loss) / baseline_loss
        output[market] = MarketValidationResult(
            market, True, sample_count, model_loss, baseline_loss, improvement
        )
    return output
