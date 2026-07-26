import unittest
from datetime import UTC, datetime, timedelta

from jingcai.backtest import ticket_returns
from jingcai.domain import (
    Market,
    MatchResult,
    ResultStatus,
    Selection,
    SettlementStatus,
    Ticket,
    TicketBundle,
)
from jingcai.settlement import settle_bundle, settle_ticket


NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)


class TicketSettlementTests(unittest.TestCase):
    def test_ticket_stake_requires_two_yuan_units(self) -> None:
        selection = Selection("p", "m", Market.MATCH_RESULT, "home", 2)
        with self.assertRaises(ValueError):
            Ticket("t", (selection,), 3, NOW, {"m": NOW + timedelta(hours=1)})

    def test_rounds_each_ticket_before_bundle_aggregation(self) -> None:
        selection = Selection("p", "m", Market.MATCH_RESULT, "home", 1.333)
        ticket1 = Ticket("t1", (selection,), 2, NOW, {"m": NOW + timedelta(hours=1)})
        ticket2 = Ticket("t2", (selection,), 4, NOW, {"m": NOW + timedelta(hours=1)})
        bundle = TicketBundle("b", (ticket1, ticket2), "single", 6, 0)
        result = settle_bundle(
            bundle, {"m": MatchResult("m", ResultStatus.FINISHED, 1, 0)}
        )
        self.assertEqual(2.67, settle_ticket(ticket1, {
            "m": MatchResult("m", ResultStatus.FINISHED, 1, 0)
        }).payout)
        self.assertEqual(8.0, result.payout)
        self.assertEqual(2.0, result.profit)

    def test_backtest_uses_ticket_stakes_and_rejects_pending(self) -> None:
        rows = [
            settle_ticket(
                Ticket(
                    "t", (Selection("p", "m", Market.MATCH_RESULT, "home", 2),),
                    2, NOW, {"m": NOW + timedelta(hours=1)}
                ),
                {"m": MatchResult("m", ResultStatus.FINISHED, 1, 0)},
            )
        ]
        report = ticket_returns(rows, stakes={"t": 2})
        self.assertEqual((report.stake, report.payout, report.profit), (2, 4, 2))
        pending = rows[0].__class__("p", SettlementStatus.PENDING, 0, 0)
        with self.assertRaises(ValueError):
            ticket_returns([pending], stakes={"p": 2})


if __name__ == "__main__":
    unittest.main()
