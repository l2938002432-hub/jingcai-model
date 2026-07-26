import unittest
from datetime import UTC, datetime, timedelta

from jingcai.domain import Market, Selection, TicketBundle
from jingcai.portfolio import (
    Candidate,
    GateLimits,
    allocate_budget,
    gate_bundle,
    payout_distribution,
    single_tickets,
    system_tickets,
    two_leg_tickets,
)


NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)
CUTOFFS = {f"m{i}": NOW + timedelta(hours=i) for i in range(1, 5)}


def candidate(index: int, *, approved: bool = True, risk: bool = False) -> Candidate:
    return Candidate(
        Selection(
            f"p{index}", f"m{index}", Market.MATCH_RESULT, "home", 1.91 + index / 10
        ),
        probability=0.6,
        conservative_probability=0.55,
        competition="TEST",
        approved=approved,
        risk_blocked=risk,
    )


class PortfolioTests(unittest.TestCase):
    def test_expands_single_two_leg_and_three_choose_two(self) -> None:
        rows = [candidate(1), candidate(2), candidate(3)]
        self.assertEqual(3, len(single_tickets(rows, 2, NOW, CUTOFFS)))
        self.assertEqual(3, len(two_leg_tickets(rows, 2, NOW, CUTOFFS)))
        system = system_tickets(rows, choose=2, stake_per_ticket=2, created_at=NOW,
                                sale_cutoffs=CUTOFFS)
        self.assertEqual(3, len(system))
        self.assertTrue(all(len(ticket.selections) == 2 for ticket in system))

    def test_budget_allocation_uses_two_yuan_units_and_never_overspends(self) -> None:
        bundle = allocate_budget(
            [candidate(1), candidate(2), candidate(3)],
            total_budget=18,
            created_at=NOW,
            sale_cutoffs=CUTOFFS,
        )
        self.assertIsInstance(bundle, TicketBundle)
        self.assertLessEqual(bundle.stake, 18)
        self.assertEqual(18 - bundle.stake, bundle.unused_budget)
        self.assertTrue(all(ticket.stake % 2 == 0 for ticket in bundle.tickets))
        with self.assertRaises(ValueError):
            allocate_budget([candidate(1)], 3, NOW, CUTOFFS)

    def test_distribution_is_discrete_complete_and_ev_is_reproducible(self) -> None:
        tickets = two_leg_tickets([candidate(1), candidate(2)], 2, NOW, CUTOFFS)
        bundle = TicketBundle("b", tickets, "double", 2, 0)
        distribution = payout_distribution(bundle, [candidate(1), candidate(2)])
        self.assertAlmostEqual(1, sum(row.probability for row in distribution.scenarios))
        self.assertEqual(0, distribution.minimum_payout)
        self.assertGreater(distribution.maximum_payout, 2)
        self.assertAlmostEqual(
            distribution.expected_profit,
            sum(row.probability * row.profit for row in distribution.scenarios),
        )

    def test_gate_fails_closed_for_unapproved_risk_and_negative_ev(self) -> None:
        rows = [candidate(1, approved=False), candidate(2, risk=True)]
        tickets = two_leg_tickets(rows, 2, NOW, CUTOFFS)
        bundle = TicketBundle("b", tickets, "double", 2, 0)
        distribution = payout_distribution(bundle, rows)
        result = gate_bundle(bundle, rows, distribution, GateLimits(20, 10, 20))
        self.assertFalse(result.allowed)
        self.assertIn("unapproved_candidate", result.reasons)
        self.assertIn("risk_blocked", result.reasons)


if __name__ == "__main__":
    unittest.main()
