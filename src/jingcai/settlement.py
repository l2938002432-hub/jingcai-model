from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from math import prod
from typing import Mapping

from .domain import (
    Market,
    MatchResult,
    Outcome,
    ResultStatus,
    Selection,
    SettlementStatus,
    Ticket,
    TicketBundle,
    TicketSettlement,
)
from .markets import OFFICIAL_CORRECT_SCORES


def _side(home: int, away: int) -> str:
    return Outcome.HOME.value if home > away else Outcome.DRAW.value if home == away else Outcome.AWAY.value


def round_payout(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def settle_selection(selection: Selection, result: MatchResult) -> SettlementStatus:
    if selection.match_id != result.match_id:
        raise ValueError("selection and result match IDs differ")
    if result.status is ResultStatus.CANCELLED:
        return SettlementStatus.VOID
    if result.status is ResultStatus.POSTPONED:
        return SettlementStatus.PENDING
    if result.status is not ResultStatus.FINISHED:
        return SettlementStatus.PENDING
    assert result.home_score is not None and result.away_score is not None
    if selection.market is Market.MATCH_RESULT:
        winning = _side(result.home_score, result.away_score)
    elif selection.market is Market.HANDICAP_RESULT:
        assert selection.handicap is not None
        winning = _side(result.home_score + selection.handicap, result.away_score)
    elif selection.market is Market.TOTAL_GOALS:
        goals = result.home_score + result.away_score
        winning = str(goals) if goals < 7 else "7+"
    elif selection.market is Market.CORRECT_SCORE:
        exact = f"{result.home_score}:{result.away_score}"
        winning = exact if (result.home_score, result.away_score) in OFFICIAL_CORRECT_SCORES else f"other_{_side(result.home_score, result.away_score)}"
    elif selection.market is Market.HALF_FULL:
        if result.half_home_score is None or result.half_away_score is None:
            return SettlementStatus.PENDING
        winning = f"{_side(result.half_home_score, result.half_away_score)}_{_side(result.home_score, result.away_score)}"
    else:
        raise ValueError(f"unsupported market: {selection.market}")
    return SettlementStatus.WON if selection.outcome == winning else SettlementStatus.LOST


def settle_ticket(ticket: Ticket, results: Mapping[str, MatchResult]) -> TicketSettlement:
    if any(selection.match_id not in results for selection in ticket.selections):
        return TicketSettlement(ticket.ticket_id, SettlementStatus.PENDING, 0.0, 0.0)
    states = [settle_selection(selection, results[selection.match_id]) for selection in ticket.selections]
    if SettlementStatus.PENDING in states:
        return TicketSettlement(ticket.ticket_id, SettlementStatus.PENDING, 0.0, 0.0)
    if SettlementStatus.LOST in states:
        return TicketSettlement(ticket.ticket_id, SettlementStatus.LOST, 0.0, -ticket.stake)
    active_odds = [s.decimal_odds for s, state in zip(ticket.selections, states) if state is SettlementStatus.WON]
    if not active_odds:
        return TicketSettlement(ticket.ticket_id, SettlementStatus.VOID, ticket.stake, 0.0)
    payout = round_payout(ticket.stake * prod(active_odds))
    status = SettlementStatus.WON
    return TicketSettlement(ticket.ticket_id, status, payout, payout - ticket.stake)


def settle_bundle(
    bundle: TicketBundle, results: Mapping[str, MatchResult]
) -> TicketSettlement:
    settlements = [settle_ticket(ticket, results) for ticket in bundle.tickets]
    if any(row.status is SettlementStatus.PENDING for row in settlements):
        return TicketSettlement(bundle.bundle_id, SettlementStatus.PENDING, 0.0, 0.0)
    payout = round_payout(sum(row.payout for row in settlements))
    profit = round_payout(payout - bundle.stake)
    if all(row.status is SettlementStatus.VOID for row in settlements):
        status = SettlementStatus.VOID
    elif profit > 0:
        status = SettlementStatus.WON
    else:
        status = SettlementStatus.LOST
    return TicketSettlement(bundle.bundle_id, status, payout, profit)
