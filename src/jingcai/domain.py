from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Mapping


class Market(str, Enum):
    MATCH_RESULT = "match_result"
    HANDICAP_RESULT = "handicap_result"
    CORRECT_SCORE = "correct_score"
    TOTAL_GOALS = "total_goals"
    HALF_FULL = "half_full"


class Outcome(str, Enum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"
    OTHER_HOME = "other_home"
    OTHER_DRAW = "other_draw"
    OTHER_AWAY = "other_away"


class ResultStatus(str, Enum):
    FINISHED = "finished"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class SettlementStatus(str, Enum):
    WON = "won"
    LOST = "lost"
    VOID = "void"
    PENDING = "pending"


def require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _probabilities(values: Mapping[str, float], name: str) -> None:
    if not values:
        raise ValueError(f"{name} cannot be empty")
    if any(not isfinite(v) or v < 0 or v > 1 for v in values.values()):
        raise ValueError(f"{name} values must be finite probabilities")
    if abs(sum(values.values()) - 1.0) > 1e-9:
        raise ValueError(f"{name} must sum to 1")


@dataclass(frozen=True)
class Match:
    match_id: str
    competition: str
    home_team: str
    away_team: str
    scheduled_start: datetime
    sale_cutoff: datetime

    def __post_init__(self) -> None:
        for value, name in ((self.scheduled_start, "scheduled_start"), (self.sale_cutoff, "sale_cutoff")):
            require_aware(value, name)
        if not all((self.match_id, self.competition, self.home_team, self.away_team)):
            raise ValueError("match identifiers and names cannot be empty")
        if self.home_team == self.away_team:
            raise ValueError("home and away teams must differ")
        if self.sale_cutoff > self.scheduled_start:
            raise ValueError("sale_cutoff cannot be after scheduled_start")


@dataclass(frozen=True)
class OddsSnapshot:
    match_id: str
    market: Market
    odds: Mapping[str, float]
    source: str
    source_as_of: datetime
    retrieved_at: datetime
    sale_cutoff: datetime
    trusted_for_roi: bool = False
    handicap: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_as_of, "source_as_of"),
            (self.retrieved_at, "retrieved_at"),
            (self.sale_cutoff, "sale_cutoff"),
        ):
            require_aware(value, name)
        if not self.match_id or not self.source or not self.odds:
            raise ValueError("snapshot identifiers, source and odds are required")
        if self.source_as_of > self.retrieved_at:
            raise ValueError("source_as_of cannot be after retrieved_at")
        if self.retrieved_at > self.sale_cutoff:
            raise ValueError("odds retrieved after sale cutoff are not usable")
        if any(not isfinite(v) or v <= 1 for v in self.odds.values()):
            raise ValueError("decimal odds must be finite and greater than 1")
        if self.market is Market.HANDICAP_RESULT and self.handicap is None:
            raise ValueError("handicap market requires an integer handicap")


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    match: Match
    market: Market
    probabilities: Mapping[str, float]
    created_at: datetime
    feature_as_of: datetime
    model_version: str
    odds_snapshot: OddsSnapshot | None = None

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")
        require_aware(self.feature_as_of, "feature_as_of")
        if not self.prediction_id or not self.model_version:
            raise ValueError("prediction_id and model_version are required")
        _probabilities(self.probabilities, "probabilities")
        if self.feature_as_of > self.created_at:
            raise ValueError("feature_as_of cannot be after prediction creation")
        if self.created_at > self.match.sale_cutoff:
            raise ValueError("prediction cannot be created after sale cutoff")
        if self.odds_snapshot is not None:
            odds = self.odds_snapshot
            if odds.match_id != self.match.match_id or odds.market is not self.market:
                raise ValueError("odds snapshot must match prediction match and market")
            if odds.sale_cutoff != self.match.sale_cutoff:
                raise ValueError("snapshot and match sale cutoffs must agree")
            if odds.retrieved_at > self.created_at or odds.source_as_of > self.created_at:
                raise ValueError("prediction cannot use odds from the future")


@dataclass(frozen=True)
class Selection:
    prediction_id: str
    match_id: str
    market: Market
    outcome: str
    decimal_odds: float
    handicap: int | None = None

    def __post_init__(self) -> None:
        if not self.prediction_id or not self.match_id or not self.outcome:
            raise ValueError("selection identifiers and outcome are required")
        if not isfinite(self.decimal_odds) or self.decimal_odds <= 1:
            raise ValueError("decimal_odds must be finite and greater than 1")
        if self.market is Market.HANDICAP_RESULT and self.handicap is None:
            raise ValueError("handicap selection requires handicap")


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    selections: tuple[Selection, ...]
    stake: float
    created_at: datetime
    sale_cutoffs: Mapping[str, datetime] = field(repr=False)

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")
        if not self.ticket_id or not self.selections:
            raise ValueError("ticket_id and at least one selection are required")
        if not isfinite(self.stake) or self.stake <= 0:
            raise ValueError("stake must be positive and finite")
        match_ids = [selection.match_id for selection in self.selections]
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("a ticket cannot contain correlated selections from the same match")
        if set(match_ids) != set(self.sale_cutoffs):
            raise ValueError("sale_cutoffs must cover every selected match exactly")
        for match_id, cutoff in self.sale_cutoffs.items():
            require_aware(cutoff, f"sale_cutoffs[{match_id}]")
            if self.created_at > cutoff:
                raise ValueError("ticket cannot be created after a selected match cutoff")


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    status: ResultStatus
    home_score: int | None = None
    away_score: int | None = None
    half_home_score: int | None = None
    half_away_score: int | None = None

    def __post_init__(self) -> None:
        scores = (self.home_score, self.away_score, self.half_home_score, self.half_away_score)
        if any(value is not None and value < 0 for value in scores):
            raise ValueError("scores cannot be negative")
        if self.status is ResultStatus.FINISHED:
            if self.home_score is None or self.away_score is None:
                raise ValueError("finished result requires full-time scores")
            if (self.half_home_score is None) != (self.half_away_score is None):
                raise ValueError("half-time scores must be supplied together")


@dataclass(frozen=True)
class TicketSettlement:
    ticket_id: str
    status: SettlementStatus
    payout: float
    profit: float

