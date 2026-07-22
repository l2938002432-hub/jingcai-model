from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from jingcai.backtest import ForecastObservation, brier_score, log_loss
from jingcai.markets import (
    OFFICIAL_CORRECT_SCORES,
    correct_score,
    expected_value,
    remove_overround,
    result_1x2,
    total_goals,
)
from jingcai.models import DixonColesModel, HalfFullModel
from jingcai.models.poisson import field, match_timestamp


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
    half_life_days: float | None = None,
) -> WalkForwardResult:
    rows = sorted(list(matches), key=match_timestamp)
    if min_train < 3 or len(rows) <= min_train:
        raise ValueError("walk-forward evaluation needs more matches than min_train")
    model_observations: list[ForecastObservation] = []
    baseline_observations: list[ForecastObservation] = []
    for index in range(min_train, len(rows)):
        train = rows[:index]
        test = rows[index]
        model = DixonColesModel().fit(
            train,
            as_of=field(test, "kickoff_utc", "kickoff_date", "kickoff", "date", "timestamp"),
            half_life_days=half_life_days,
        )
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


def build_paper_candidates(
    matches: Iterable[Mapping[str, Any]],
    fixtures: Iterable[Mapping[str, Any]],
    *,
    safety_margin: float = 0.03,
    prediction_time: datetime | None = None,
    acceptance_config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if acceptance_config is None:
        acceptance_path = Path(__file__).resolve().parents[2] / "config" / "model-acceptance.json"
        acceptance_config = json.loads(acceptance_path.read_text(encoding="utf-8"))
    history = list(matches)
    as_of = prediction_time or datetime.now(UTC)
    if as_of.tzinfo is None:
        raise ValueError("prediction_time must be timezone-aware")
    trained_teams = {
        str(row[field]) for row in history for field in ("home_team", "away_team")
    }
    candidates: list[dict[str, Any]] = []
    for fixture in fixtures:
        competition_code = str(fixture.get("competition_code", ""))
        competition_acceptance = acceptance_config.get(competition_code, {})
        if not isinstance(competition_acceptance, Mapping) or competition_acceptance.get("approved") is not True:
            continue
        approved_markets = competition_acceptance.get("markets", {})
        if not isinstance(approved_markets, Mapping):
            continue
        if str(fixture["home_team"]) not in trained_teams or str(fixture["away_team"]) not in trained_teams:
            continue
        cutoff = datetime.fromisoformat(str(fixture["sale_cutoff"]))
        odds_as_of = datetime.fromisoformat(str(fixture["odds_as_of"]))
        if cutoff.tzinfo is None or odds_as_of.tzinfo is None:
            raise ValueError("sale_cutoff and odds_as_of must be timezone-aware")
        if odds_as_of > as_of:
            raise ValueError("odds_as_of cannot be after prediction_time")
        if as_of > cutoff:
            continue
        prediction = predict_all_markets(
            history,
            home_team=str(fixture["home_team"]),
            away_team=str(fixture["away_team"]),
            handicap=int(fixture.get("handicap", 0)),
        )
        best: dict[str, Any] | None = None
        odds_by_market = fixture.get("odds", {})
        if not isinstance(odds_by_market, Mapping):
            raise ValueError("fixture odds must be a market mapping")
        for market, odds in odds_by_market.items():
            if market not in prediction or not isinstance(odds, Mapping):
                raise ValueError(f"unknown or invalid odds market: {market}")
            if approved_markets.get(market) is not True:
                continue
            market_probabilities = prediction[market]
            market_baseline = remove_overround({str(k): float(v) for k, v in odds.items()})
            for outcome, decimal_odds in odds.items():
                if outcome not in market_probabilities:
                    raise ValueError(f"outcome {outcome!r} is missing from model market {market!r}")
                probability = float(market_probabilities[outcome])
                ev = expected_value(probability, float(decimal_odds), safety_margin)
                item = {
                    "match_id": str(fixture["match_id"]),
                    "label": f"{fixture['home_team']} vs {fixture['away_team']}",
                    "play": f"{market}:{outcome}",
                    "market": market,
                    "outcome": str(outcome),
                    "probability": probability,
                    "market_probability": market_baseline[str(outcome)],
                    "decimal_odds": float(decimal_odds),
                    "conservative_ev": ev,
                    "safety_margin": safety_margin,
                    "odds_as_of": odds_as_of.isoformat(),
                    "sale_cutoff": cutoff.isoformat(),
                    "sale_cutoff_estimated": bool(fixture.get("sale_cutoff_estimated", False)),
                }
                if best is None or item["conservative_ev"] > best["conservative_ev"]:
                    best = item
        if best is not None and best["conservative_ev"] > 0:
            candidates.append(best)
    return sorted(candidates, key=lambda item: item["conservative_ev"], reverse=True)
