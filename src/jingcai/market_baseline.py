"""Reproducible pre-match market baselines.

This module turns one *complete* 1X2 decimal-odds snapshot into a fair-probability
baseline.  It is deliberately a benchmark, not a selection or profitability
signal: it says what the supplied market priced before a match, after removing
the market's aggregate margin by proportional normalisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping


ONE_X_TWO_OUTCOMES = ("home", "draw", "away")


@dataclass(frozen=True)
class MarketBaselineDiagnostics:
    """Audit values retained alongside a de-vig 1X2 market baseline."""

    implied_probability_total: float
    overround: float
    margin: float
    price_shape: str
    normalization: str = "multiplicative"


@dataclass(frozen=True)
class Prematch1X2MarketBaseline:
    """Fair 1X2 probabilities derived only from one decimal-odds snapshot."""

    probabilities: Mapping[str, float]
    implied_probabilities: Mapping[str, float]
    diagnostics: MarketBaselineDiagnostics


def prematch_1x2_market_baseline(decimal_odds: Mapping[str, float]) -> Prematch1X2MarketBaseline:
    """Remove aggregate margin from a complete 1X2 decimal-odds market.

    ``decimal_odds`` must contain exactly ``home``, ``draw`` and ``away`` and
    every price must be a finite decimal return strictly greater than one.
    The raw implied probabilities are ``1 / odds``.  Their sum is the market
    overround; proportional normalisation divides each raw probability by that
    sum, producing probabilities that total one.  An underround is accepted and
    flagged diagnostically because it can occur in an aggregated or erroneous
    snapshot, but it is not silently presented as bookmaker margin.
    """
    if set(decimal_odds) != set(ONE_X_TWO_OUTCOMES):
        raise ValueError("1X2 odds must contain exactly home, draw and away")
    if any(not isinstance(odds, (int, float)) or isinstance(odds, bool) or not isfinite(odds) or odds <= 1 for odds in decimal_odds.values()):
        raise ValueError("1X2 decimal odds must be finite numbers greater than 1")

    implied = {outcome: 1.0 / float(decimal_odds[outcome]) for outcome in ONE_X_TWO_OUTCOMES}
    total = sum(implied.values())
    # The checks above make this mathematically impossible, but retain an
    # explicit guard so callers never receive an unverifiable baseline.
    if not isfinite(total) or total <= 0:
        raise ValueError("1X2 implied probability total must be positive and finite")
    margin = total - 1.0
    tolerance = 1e-12
    price_shape = "overround" if margin > tolerance else "underround" if margin < -tolerance else "fair"
    probabilities = {outcome: implied[outcome] / total for outcome in ONE_X_TWO_OUTCOMES}
    return Prematch1X2MarketBaseline(
        probabilities=MappingProxyType(probabilities),
        implied_probabilities=MappingProxyType(implied),
        diagnostics=MarketBaselineDiagnostics(total, total, margin, price_shape),
    )
