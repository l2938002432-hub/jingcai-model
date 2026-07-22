from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from jingcai.backtest import ForecastObservation, brier_score, log_loss
from jingcai.markets import OFFICIAL_CORRECT_SCORES, correct_score, result_1x2, total_goals
from jingcai.models import DixonColesModel, HalfFullModel


def matrix_mapping(matrix: list[list[float]]) -> dict[tuple[int, int], float]:
    return {(home, away): value for home, row in enumerate(matrix) for away, value in enumerate(row)}


def actual_result(home_goals: int, away_goals: int) -> str:
    return "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"


@dataclass(frozen=True)
class WalkForwardResult:
    evaluated_matches: int
    model_log_loss: float
    baseline_log_loss: float
    model_brier: float
    baseline_brier: float
    roi_status: str = "UNAVAILABLE_WITHOUT_TRUSTED_SPORTTERY_ODDS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _frequency_baseline(matches: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    counts = {"home": 1.0, "draw": 1.0, "away": 1.0}
    for match in matches:
        counts[actual_result(int(match["home_goals"]), int(match["away_goals"]))] += 1.0
    total = sum(counts.values())
    return {key: value / total for key, value in counts.items()}


def walk_forward_1x2(
    matches: Iterable[Mapping[str, Any]],
    *,
    min_train: int = 30,
    max_goals: int = 10,
) -> WalkForwardResult:
    rows = sorted(list(matches), key=lambda item: str(item["kickoff_utc"]))
    if min_train < 3 or len(rows) <= min_train:
        raise ValueError("walk-forward evaluation needs more matches than min_train")
    model_observations: list[ForecastObservation] = []
    baseline_observations: list[ForecastObservation] = []
    for index in range(min_train, len(rows)):
        train = rows[:index]
        test = rows[index]
        model = DixonColesModel().fit(train)
        probabilities = result_1x2(
            matrix_mapping(model.predict_score_matrix(str(test["home_team"]), str(test["away_team"]), max_goals))
        )
        actual = actual_result(int(test["home_goals"]), int(test["away_goals"]))
        model_observations.append(ForecastObservation(probabilities, actual))
        baseline_observations.append(ForecastObservation(_frequency_baseline(train), actual))
    return WalkForwardResult(
        evaluated_matches=len(model_observations),
        model_log_loss=log_loss(model_observations),
        baseline_log_loss=log_loss(baseline_observations),
        model_brier=brier_score(model_observations),
        baseline_brier=brier_score(baseline_observations),
    )


def predict_all_markets(
    matches: Iterable[Mapping[str, Any]],
    *,
    home_team: str,
    away_team: str,
    handicap: int = 0,
    max_goals: int = 10,
) -> dict[str, Any]:
    rows = list(matches)
    model = DixonColesModel().fit(rows)
    matrix = matrix_mapping(model.predict_score_matrix(home_team, away_team, max_goals))
    half_full = HalfFullModel(model).predict_proba(home_team, away_team, max_goals)
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "model": "dixon-coles-v0.1",
        "state": "RESEARCH",
        "home_team": home_team,
        "away_team": away_team,
        "match_result": result_1x2(matrix),
        "handicap_result": result_1x2(matrix, handicap),
        "handicap": handicap,
        "total_goals": total_goals(matrix),
        "correct_score": correct_score(matrix, OFFICIAL_CORRECT_SCORES),
        "half_full": half_full,
    }

