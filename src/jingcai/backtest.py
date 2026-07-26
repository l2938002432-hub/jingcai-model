from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from statistics import fmean
from typing import Iterable, Mapping, Sequence

from .domain import SettlementStatus, TicketSettlement


@dataclass(frozen=True)
class ForecastObservation:
    probabilities: Mapping[str, float]
    actual: str


@dataclass(frozen=True)
class BetObservation:
    won: bool
    decimal_odds: float | None
    trusted_odds: bool


@dataclass(frozen=True)
class BacktestReturns:
    bets: int
    wins: int
    stake: float
    payout: float
    profit: float
    roi: float
    max_drawdown: float


def _validate_forecast(observation: ForecastObservation) -> None:
    if observation.actual not in observation.probabilities:
        raise ValueError("actual category missing from probabilities")
    if any(p < 0 or p > 1 for p in observation.probabilities.values()):
        raise ValueError("invalid probability")
    if abs(sum(observation.probabilities.values()) - 1.0) > 1e-9:
        raise ValueError("probabilities must sum to 1")


def log_loss(observations: Iterable[ForecastObservation], epsilon: float = 1e-15) -> float:
    rows = list(observations)
    if not rows:
        raise ValueError("at least one observation is required")
    for row in rows:
        _validate_forecast(row)
    return -fmean(log(max(epsilon, row.probabilities[row.actual])) for row in rows)


def brier_score(observations: Iterable[ForecastObservation]) -> float:
    rows = list(observations)
    if not rows:
        raise ValueError("at least one observation is required")
    scores = []
    for row in rows:
        _validate_forecast(row)
        scores.append(sum((probability - (1.0 if category == row.actual else 0.0)) ** 2 for category, probability in row.probabilities.items()))
    return fmean(scores)


def ranked_probability_score(observations: Iterable[ForecastObservation], order: Sequence[str]) -> float:
    rows = list(observations)
    if not rows or len(order) < 2 or len(order) != len(set(order)):
        raise ValueError("observations and a unique category order are required")
    scores = []
    for row in rows:
        _validate_forecast(row)
        if set(row.probabilities) != set(order):
            raise ValueError("probability categories must equal the supplied order")
        actual_index = order.index(row.actual)
        cumulative = 0.0
        score = 0.0
        for index, category in enumerate(order[:-1]):
            cumulative += row.probabilities[category]
            observed_cumulative = 1.0 if actual_index <= index else 0.0
            score += (cumulative - observed_cumulative) ** 2
        scores.append(score / (len(order) - 1))
    return fmean(scores)


def fixed_unit_returns(bets: Iterable[BetObservation], unit_stake: float = 1.0) -> BacktestReturns:
    rows = list(bets)
    if not rows:
        raise ValueError("at least one bet is required")
    if unit_stake <= 0:
        raise ValueError("unit_stake must be positive")
    if any(not row.trusted_odds or row.decimal_odds is None for row in rows):
        raise ValueError("ROI is forbidden without trusted, time-valid odds for every bet")
    if any(row.decimal_odds is None or row.decimal_odds <= 1 for row in rows):
        raise ValueError("decimal odds must be greater than 1")
    profits = [unit_stake * ((row.decimal_odds or 0.0) - 1.0) if row.won else -unit_stake for row in rows]
    equity = peak = drawdown = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    stake = unit_stake * len(rows)
    profit = sum(profits)
    payout = stake + profit
    return BacktestReturns(len(rows), sum(row.won for row in rows), stake, payout, profit, profit / stake, drawdown)


def ticket_returns(
    settlements: Iterable[TicketSettlement], *, stakes: Mapping[str, float]
) -> BacktestReturns:
    rows = list(settlements)
    if not rows:
        raise ValueError("at least one settlement is required")
    if any(row.status is SettlementStatus.PENDING for row in rows):
        raise ValueError("pending settlements cannot be included in returns")
    if set(stakes) != {row.ticket_id for row in rows}:
        raise ValueError("stakes must cover every settlement exactly")
    if any(not isfinite(stake) or stake <= 0 for stake in stakes.values()):
        raise ValueError("stakes must be positive")
    equity = peak = drawdown = 0.0
    for row in rows:
        equity += row.profit
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    stake = sum(stakes.values())
    payout = sum(row.payout for row in rows)
    profit = sum(row.profit for row in rows)
    return BacktestReturns(
        len(rows),
        sum(row.status is SettlementStatus.WON for row in rows),
        stake,
        payout,
        profit,
        profit / stake,
        drawdown,
    )

