"""Legal ticket construction, budget allocation, and auditable payout scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations, product
from math import isfinite, prod
from typing import Iterable, Mapping, Sequence

from .domain import (
    PayoutDistribution,
    PayoutScenario,
    Selection,
    Ticket,
    TicketBundle,
)
from .settlement import round_payout


@dataclass(frozen=True)
class Candidate:
    selection: Selection
    probability: float
    conservative_probability: float
    competition: str
    approved: bool = True
    risk_blocked: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.probability, "probability"),
            (self.conservative_probability, "conservative_probability"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability")
        if self.conservative_probability > self.probability:
            raise ValueError("conservative_probability cannot exceed probability")
        if not self.competition:
            raise ValueError("competition is required")


@dataclass(frozen=True)
class GateLimits:
    max_daily_stake: float
    max_match_stake: float
    max_competition_stake: float

    def __post_init__(self) -> None:
        if any(
            not isfinite(value) or value <= 0
            for value in (
                self.max_daily_stake,
                self.max_match_stake,
                self.max_competition_stake,
            )
        ):
            raise ValueError("gate limits must be positive and finite")


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reasons: tuple[str, ...]


def _validate_ticket_inputs(
    candidates: Sequence[Candidate],
    stake: float,
    sale_cutoffs: Mapping[str, datetime],
) -> None:
    if not candidates:
        raise ValueError("at least one candidate is required")
    if not isfinite(stake) or stake <= 0 or stake % 2 != 0:
        raise ValueError("stake must be a positive multiple of 2 yuan")
    match_ids = [row.selection.match_id for row in candidates]
    if len(match_ids) != len(set(match_ids)):
        raise ValueError("ticket candidates must come from different matches")
    if any(match_id not in sale_cutoffs for match_id in match_ids):
        raise ValueError("sale cutoff missing for selected match")


def _ticket(
    ticket_id: str,
    candidates: Sequence[Candidate],
    stake: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
) -> Ticket:
    _validate_ticket_inputs(candidates, stake, sale_cutoffs)
    cutoffs = {row.selection.match_id: sale_cutoffs[row.selection.match_id] for row in candidates}
    return Ticket(
        ticket_id,
        tuple(row.selection for row in candidates),
        stake,
        created_at,
        cutoffs,
    )


def single_tickets(
    candidates: Sequence[Candidate],
    stake_per_ticket: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
) -> tuple[Ticket, ...]:
    return tuple(
        _ticket(f"single-{index}", (row,), stake_per_ticket, created_at, sale_cutoffs)
        for index, row in enumerate(candidates, 1)
    )


def two_leg_tickets(
    candidates: Sequence[Candidate],
    stake_per_ticket: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
) -> tuple[Ticket, ...]:
    if len(candidates) < 2:
        return ()
    return tuple(
        _ticket(
            f"double-{index}",
            pair,
            stake_per_ticket,
            created_at,
            sale_cutoffs,
        )
        for index, pair in enumerate(combinations(candidates, 2), 1)
    )


def system_tickets(
    candidates: Sequence[Candidate],
    *,
    choose: int,
    stake_per_ticket: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
) -> tuple[Ticket, ...]:
    if choose != 2:
        raise ValueError("the first release supports only choose=2 system tickets")
    if len(candidates) != 3:
        raise ValueError("3-select-2 requires exactly three candidates")
    return tuple(
        _ticket(f"system-3x2-{index}", pair, stake_per_ticket, created_at, sale_cutoffs)
        for index, pair in enumerate(combinations(candidates, choose), 1)
    )


def payout_distribution(
    bundle: TicketBundle,
    candidates: Sequence[Candidate],
    *,
    conservative: bool = True,
) -> PayoutDistribution:
    by_match = {row.selection.match_id: row for row in candidates}
    if len(by_match) != len(candidates):
        raise ValueError("candidates must contain at most one selection per match")
    selected_matches = {
        selection.match_id
        for ticket in bundle.tickets
        for selection in ticket.selections
    }
    if set(by_match) != selected_matches:
        raise ValueError("candidates must cover bundle matches exactly")
    ordered = [by_match[match_id] for match_id in sorted(by_match)]
    scenarios: list[PayoutScenario] = []
    for states in product((False, True), repeat=len(ordered)):
        probabilities = [
            row.conservative_probability if conservative else row.probability
            for row in ordered
        ]
        probability = prod(
            chance if won else 1 - chance
            for chance, won in zip(probabilities, states)
        )
        wins = {
            row.selection.match_id: won
            for row, won in zip(ordered, states)
        }
        payout = sum(
            round_payout(
                ticket.stake
                * prod(selection.decimal_odds for selection in ticket.selections)
            )
            for ticket in bundle.tickets
            if all(wins[selection.match_id] for selection in ticket.selections)
        )
        payout = round_payout(payout)
        scenarios.append(
            PayoutScenario(probability, payout, round_payout(payout - bundle.stake))
        )
    expected_payout = sum(row.probability * row.payout for row in scenarios)
    expected_profit = expected_payout - bundle.stake
    return PayoutDistribution(
        tuple(scenarios),
        min(row.payout for row in scenarios),
        max(row.payout for row in scenarios),
        expected_payout,
        expected_profit,
        sum(row.probability for row in scenarios if row.payout > 0),
        sum(row.probability for row in scenarios if row.profit > 0),
    )


def allocate_budget(
    candidates: Sequence[Candidate],
    total_budget: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
) -> TicketBundle:
    if not isfinite(total_budget) or total_budget <= 0 or total_budget % 2 != 0:
        raise ValueError("total_budget must be a positive multiple of 2 yuan")
    eligible = [row for row in candidates if row.approved and not row.risk_blocked]
    if not eligible:
        raise ValueError("no eligible candidates")

    def units(cap: float, count: int) -> float:
        if count == 0:
            return 0
        return float(int(cap / (2 * count)) * 2)

    tickets: list[Ticket] = []
    single_stake = units(total_budget * 0.7, len(eligible))
    if single_stake:
        tickets.extend(single_tickets(eligible, single_stake, created_at, sale_cutoffs))
    pairs = tuple(combinations(eligible, 2))
    pair_stake = units(total_budget * 0.2, len(pairs))
    if pair_stake:
        tickets.extend(two_leg_tickets(eligible, pair_stake, created_at, sale_cutoffs))
    if len(eligible) == 3:
        system_stake = units(total_budget * 0.1, 3)
        if system_stake:
            tickets.extend(
                system_tickets(
                    eligible,
                    choose=2,
                    stake_per_ticket=system_stake,
                    created_at=created_at,
                    sale_cutoffs=sale_cutoffs,
                )
            )
    if not tickets:
        raise ValueError("budget is too small for eligible tickets")
    used = sum(ticket.stake for ticket in tickets)
    return TicketBundle("allocated", tuple(tickets), "70-20-10-caps", total_budget,
                        total_budget - used)


def gate_bundle(
    bundle: TicketBundle,
    candidates: Sequence[Candidate],
    distribution: PayoutDistribution,
    limits: GateLimits,
) -> GateResult:
    reasons: list[str] = []
    bundle_matches = {
        selection.match_id
        for ticket in bundle.tickets
        for selection in ticket.selections
    }
    candidate_matches = {row.selection.match_id for row in candidates}
    if bundle_matches != candidate_matches or len(candidate_matches) != len(candidates):
        return GateResult(False, ("candidate_coverage_mismatch",))
    if any(not row.approved for row in candidates):
        reasons.append("unapproved_candidate")
    if any(row.risk_blocked for row in candidates):
        reasons.append("risk_blocked")
    if distribution.expected_profit <= 0:
        reasons.append("non_positive_conservative_ev")
    if bundle.stake > limits.max_daily_stake:
        reasons.append("daily_exposure_exceeded")
    by_match: dict[str, float] = {}
    competition_by_match = {
        row.selection.match_id: row.competition for row in candidates
    }
    by_competition: dict[str, float] = {}
    for ticket in bundle.tickets:
        for selection in ticket.selections:
            by_match[selection.match_id] = by_match.get(selection.match_id, 0) + ticket.stake
            competition = competition_by_match[selection.match_id]
            by_competition[competition] = (
                by_competition.get(competition, 0) + ticket.stake
            )
    if any(value > limits.max_match_stake for value in by_match.values()):
        reasons.append("match_exposure_exceeded")
    if any(value > limits.max_competition_stake for value in by_competition.values()):
        reasons.append("competition_exposure_exceeded")
    return GateResult(not reasons, tuple(reasons))
