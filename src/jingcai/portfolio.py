"""Legal ticket construction, budget allocation, and auditable payout scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    bankroll: float | None = None
    current_drawdown: float = 0.0
    max_drawdown_fraction: float = 0.10

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
        if self.bankroll is not None and (
            not isfinite(self.bankroll) or self.bankroll <= 0
        ):
            raise ValueError("bankroll must be positive and finite")
        if not isfinite(self.current_drawdown) or self.current_drawdown < 0:
            raise ValueError("current_drawdown must be finite and non-negative")
        if (
            not isfinite(self.max_drawdown_fraction)
            or not 0 < self.max_drawdown_fraction <= 1
        ):
            raise ValueError("max_drawdown_fraction must be in (0, 1]")


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reasons: tuple[str, ...]
    candidate_gate: bool
    joint_probability_gate: bool
    rules_gate: bool
    economic_gate: bool


@dataclass(frozen=True)
class AuditedPayoutDistribution(PayoutDistribution):
    correlation_haircut: float
    algorithm_version: str
    raw_joint_probabilities: tuple[float, ...]
    adjusted_joint_probabilities: tuple[float, ...]


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
        raise ValueError("at least two candidates are required for 2-leg tickets")
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
    correlation_haircut: float = 0.0,
    algorithm_version: str = "independent-v1",
) -> AuditedPayoutDistribution:
    if (
        not isfinite(correlation_haircut)
        or not 0 <= correlation_haircut < 1
    ):
        raise ValueError("correlation_haircut must be in [0, 1)")
    if not algorithm_version:
        raise ValueError("algorithm_version is required")
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
    raw_rows: list[tuple[float, float]] = []
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
        raw_rows.append((probability, payout))
    raw_probabilities = tuple(row[0] for row in raw_rows)
    adjusted_probabilities = [
        probability * (1 - correlation_haircut) if payout > 0 else probability
        for probability, payout in raw_rows
    ]
    removed = 1 - sum(adjusted_probabilities)
    zero_indexes = [
        index for index, (_, payout) in enumerate(raw_rows) if payout == 0
    ]
    if not zero_indexes:
        raise ValueError("distribution has no losing scenario for correlation haircut")
    zero_mass = sum(raw_probabilities[index] for index in zero_indexes)
    for index in zero_indexes:
        adjusted_probabilities[index] += (
            removed * raw_probabilities[index] / zero_mass
        )
    scenarios = [
        PayoutScenario(
            probability,
            payout,
            round_payout(payout - bundle.stake),
        )
        for probability, (_, payout) in zip(adjusted_probabilities, raw_rows)
    ]
    expected_payout = sum(row.probability * row.payout for row in scenarios)
    expected_profit = expected_payout - bundle.stake
    return AuditedPayoutDistribution(
        tuple(scenarios),
        min(row.payout for row in scenarios),
        max(row.payout for row in scenarios),
        expected_payout,
        expected_profit,
        sum(row.probability for row in scenarios if row.payout > 0),
        sum(row.probability for row in scenarios if row.profit > 0),
        correlation_haircut,
        algorithm_version,
        raw_probabilities,
        tuple(adjusted_probabilities),
    )


def allocate_budget(
    candidates: Sequence[Candidate],
    total_budget: float,
    created_at: datetime,
    sale_cutoffs: Mapping[str, datetime],
    *,
    transfer_to_lower_risk: bool = False,
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
    if transfer_to_lower_risk:
        single_indexes = [
            index for index, ticket in enumerate(tickets)
            if len(ticket.selections) == 1
        ]
        remaining_units = int((total_budget - used) / 2)
        for offset in range(remaining_units):
            index = single_indexes[offset % len(single_indexes)]
            tickets[index] = replace(tickets[index], stake=tickets[index].stake + 2)
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
        return GateResult(
            False,
            ("candidate_coverage_mismatch",),
            False,
            False,
            False,
            False,
        )
    if any(not row.approved for row in candidates):
        reasons.append("unapproved_candidate")
    if any(row.risk_blocked for row in candidates):
        reasons.append("risk_blocked")
    candidate_gate = not reasons
    joint_probability_gate = (
        bool(distribution.algorithm_version)
        and 0 <= distribution.correlation_haircut < 1
        and abs(sum(distribution.adjusted_joint_probabilities) - 1) <= 1e-9
    )
    if not joint_probability_gate:
        reasons.append("joint_probability_invalid")
    rules_gate = all(
        len(ticket.selections) in (1, 2)
        and len({selection.match_id for selection in ticket.selections})
        == len(ticket.selections)
        for ticket in bundle.tickets
    )
    if not rules_gate:
        reasons.append("rules_invalid")
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
    if limits.bankroll is not None:
        worst_loss = max(0.0, bundle.stake - distribution.minimum_payout)
        if (
            limits.current_drawdown + worst_loss
            > limits.bankroll * limits.max_drawdown_fraction
        ):
            reasons.append("drawdown_limit_exceeded")
    economic_reasons = {
        "non_positive_conservative_ev",
        "daily_exposure_exceeded",
        "match_exposure_exceeded",
        "competition_exposure_exceeded",
        "drawdown_limit_exceeded",
    }
    economic_gate = not any(reason in economic_reasons for reason in reasons)
    return GateResult(
        not reasons,
        tuple(reasons),
        candidate_gate,
        joint_probability_gate,
        rules_gate,
        economic_gate,
    )
