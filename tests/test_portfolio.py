import unittest
from datetime import UTC, datetime, timedelta

from jingcai.domain import Market, Selection, TicketBundle
from jingcai.portfolio import (
    Candidate,
    GateLimits,
    StrategyEvidence,
    admit_strategy,
    allocate_budget,
    gate_bundle,
    payout_distribution,
    simulate_research_budget,
    single_tickets,
    system_tickets,
    two_leg_tickets,
)


NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)
CUTOFFS = {f"m{i}": NOW + timedelta(hours=i) for i in range(1, 5)}


def candidate(
    index: int, *, approved: bool = True, risk: bool = False, snapshot: bool = True,
) -> Candidate:
    return Candidate(
        Selection(
            f"p{index}", f"m{index}", Market.MATCH_RESULT, "home", 1.91 + index / 10
        ),
        probability=0.6,
        conservative_probability=0.55,
        competition="TEST",
        approved=approved,
        risk_blocked=risk,
        trusted_odds_snapshot=snapshot,
    )


def evidence(*, approved: bool = True) -> StrategyEvidence:
    return StrategyEvidence(
        "single-and-double-v1", "e" * 64, NOW, ("match_result",), approved,
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
            evidence=evidence(),
        )
        self.assertIsInstance(bundle, TicketBundle)
        self.assertLessEqual(bundle.stake, 18)
        self.assertEqual(18 - bundle.stake, bundle.unused_budget)
        self.assertTrue(all(ticket.stake % 2 == 0 for ticket in bundle.tickets))
        with self.assertRaises(ValueError):
            allocate_budget([candidate(1)], 3, NOW, CUTOFFS, evidence=evidence())

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
        self.assertFalse(result.candidate_gate)

    def test_correlation_haircut_is_audited_and_reduces_joint_return(self) -> None:
        rows = [candidate(1), candidate(2)]
        tickets = two_leg_tickets(rows, 2, NOW, CUTOFFS)
        bundle = TicketBundle("b", tickets, "double", 2, 0)
        raw = payout_distribution(bundle, rows)
        adjusted = payout_distribution(
            bundle,
            rows,
            correlation_haircut=0.25,
            algorithm_version="independent-haircut-v1",
        )
        self.assertEqual("independent-haircut-v1", adjusted.algorithm_version)
        self.assertEqual(0.25, adjusted.correlation_haircut)
        self.assertEqual(
            len(adjusted.raw_joint_probabilities),
            len(adjusted.adjusted_joint_probabilities),
        )
        self.assertLess(adjusted.expected_payout, raw.expected_payout)
        self.assertAlmostEqual(1, sum(adjusted.adjusted_joint_probabilities))
        for bad in (-0.1, 1.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                payout_distribution(bundle, rows, correlation_haircut=bad)
        with self.assertRaises(ValueError):
            payout_distribution(bundle, rows, algorithm_version="")

    def test_ticket_generation_fails_closed_when_candidates_are_insufficient(self) -> None:
        with self.assertRaises(ValueError):
            two_leg_tickets([candidate(1)], 2, NOW, CUTOFFS)
        with self.assertRaises(ValueError):
            system_tickets(
                [candidate(1), candidate(2)],
                choose=2,
                stake_per_ticket=2,
                created_at=NOW,
                sale_cutoffs=CUTOFFS,
            )

    def test_empty_risky_buckets_stay_unused_unless_transferred_to_singles(self) -> None:
        rows = [candidate(1)]
        kept = allocate_budget(rows, 20, NOW, CUTOFFS, evidence=evidence())
        transferred = allocate_budget(
            rows, 20, NOW, CUTOFFS, transfer_to_lower_risk=True, evidence=evidence()
        )
        self.assertEqual(6, kept.unused_budget)
        self.assertEqual(0, transferred.unused_budget)
        self.assertTrue(all(len(ticket.selections) == 1 for ticket in transferred.tickets))

    def test_four_layer_gate_and_ten_percent_pretrade_loss_limit(self) -> None:
        rows = [candidate(1), candidate(2)]
        tickets = two_leg_tickets(rows, 2, NOW, CUTOFFS)
        bundle = TicketBundle("b", tickets, "double", 2, 0)
        distribution = payout_distribution(bundle, rows)
        result = gate_bundle(
            bundle,
            rows,
            distribution,
            GateLimits(
                20,
                10,
                20,
                bankroll=100,
                current_drawdown=9,
                max_drawdown_fraction=0.10,
            ),
        )
        self.assertFalse(result.allowed)
        self.assertIn("drawdown_limit_exceeded", result.reasons)
        self.assertTrue(result.candidate_gate)
        self.assertTrue(result.joint_probability_gate)
        self.assertTrue(result.rules_gate)
        self.assertFalse(result.economic_gate)

    def test_portfolio_requires_real_snapshot_and_validated_strategy_evidence(self) -> None:
        rows = [candidate(1, snapshot=False)]
        admission = admit_strategy(rows, evidence())
        self.assertFalse(admission.allowed)
        self.assertIn("trusted_pre_cutoff_odds_missing", admission.reasons)
        with self.assertRaisesRegex(PermissionError, "strategy_evidence_missing"):
            allocate_budget(rows, 20, NOW, CUTOFFS)
        with self.assertRaisesRegex(PermissionError, "trusted_pre_cutoff_odds_missing"):
            allocate_budget(rows, 20, NOW, CUTOFFS, evidence=evidence())
        denied = admit_strategy([candidate(1)], evidence(approved=False))
        self.assertIn("strategy_not_approved", denied.reasons)

    def test_research_budget_simulation_preserves_amount_and_payout_bounds_without_advice(self) -> None:
        simulation = simulate_research_budget([candidate(1, snapshot=False), candidate(2, snapshot=False)], 10)
        self.assertEqual((10, 10, 0), (simulation.budget, simulation.allocated, simulation.unallocated))
        self.assertEqual(0, simulation.minimum_payout)
        self.assertGreater(simulation.maximum_payout, 0)
        self.assertEqual(2, len(simulation.lines))
        for line in simulation.lines:
            self.assertAlmostEqual(line.payout_if_hit - 10, line.net_if_hit)


if __name__ == "__main__":
    unittest.main()
