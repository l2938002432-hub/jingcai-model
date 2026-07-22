import unittest
from datetime import UTC, datetime, timedelta

from jingcai.backtest import BetObservation, ForecastObservation, brier_score, fixed_unit_returns, log_loss, ranked_probability_score
from jingcai.domain import Market, Match, MatchResult, OddsSnapshot, Outcome, Prediction, ResultStatus, Selection, SettlementStatus, Ticket
from jingcai.markets import correct_score, expected_value, remove_overround, result_1x2, total_goals, validate_half_full
from jingcai.settlement import settle_selection, settle_ticket


NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.match = Match("m1", "league", "A", "B", NOW + timedelta(hours=4), NOW + timedelta(hours=3))
        self.odds = OddsSnapshot("m1", Market.MATCH_RESULT, {"home": 2.0, "draw": 3.0, "away": 4.0}, "official", NOW, NOW + timedelta(minutes=1), self.match.sale_cutoff, True)

    def test_prediction_validates_complete_time_chain(self):
        Prediction("p1", self.match, Market.MATCH_RESULT, {"home": .5, "draw": .3, "away": .2}, NOW + timedelta(minutes=2), NOW, "v1", self.odds)
        with self.assertRaises(ValueError):
            Prediction("p2", self.match, Market.MATCH_RESULT, {"home": .5, "draw": .3, "away": .2}, NOW, NOW, "v1", self.odds)

    def test_ticket_rejects_same_match_twice_and_late_creation(self):
        one = Selection("p1", "m1", Market.MATCH_RESULT, "home", 2.0)
        two = Selection("p2", "m1", Market.TOTAL_GOALS, "2", 3.0)
        with self.assertRaises(ValueError):
            Ticket("t", (one, two), 2.0, NOW, {"m1": self.match.sale_cutoff})
        with self.assertRaises(ValueError):
            Ticket("t", (one,), 2.0, NOW + timedelta(hours=4), {"m1": self.match.sale_cutoff})


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.matrix = {(0, 0): .2, (1, 0): .3, (0, 1): .1, (2, 2): .15, (5, 0): .15, (0, 5): .1}

    def test_score_derivations_preserve_probability(self):
        derived = result_1x2(self.matrix)
        self.assertAlmostEqual(derived["home"], .45)
        self.assertAlmostEqual(derived["draw"], .35)
        self.assertAlmostEqual(derived["away"], .2)
        self.assertAlmostEqual(sum(total_goals(self.matrix).values()), 1.0)
        scores = correct_score(self.matrix, {(0, 0), (1, 0), (0, 1)})
        self.assertAlmostEqual(sum(scores.values()), 1.0)
        self.assertAlmostEqual(scores[Outcome.OTHER_HOME.value], .15)
        self.assertAlmostEqual(scores[Outcome.OTHER_DRAW.value], .15)
        self.assertAlmostEqual(scores[Outcome.OTHER_AWAY.value], .1)

    def test_handicap_and_market_math(self):
        self.assertEqual(result_1x2(self.matrix, handicap=-1)["draw"], .3)
        fair = remove_overround({"home": 2, "draw": 3, "away": 4})
        self.assertAlmostEqual(sum(fair.values()), 1)
        self.assertAlmostEqual(expected_value(.6, 2, .05), .15)

    def test_half_full_requires_nine_categories(self):
        valid = {f"{a}_{b}": 1 / 9 for a in ("home", "draw", "away") for b in ("home", "draw", "away")}
        validate_half_full(valid)
        with self.assertRaises(ValueError):
            validate_half_full({"home_home": 1.0})


class SettlementTests(unittest.TestCase):
    def test_markets_and_parlay_void_leg(self):
        result = MatchResult("m1", ResultStatus.FINISHED, 2, 1, 1, 0)
        self.assertIs(settle_selection(Selection("p", "m1", Market.MATCH_RESULT, "home", 2), result), SettlementStatus.WON)
        self.assertIs(settle_selection(Selection("p", "m1", Market.HANDICAP_RESULT, "draw", 3, -1), result), SettlementStatus.WON)
        self.assertIs(settle_selection(Selection("p", "m1", Market.TOTAL_GOALS, "3", 4), result), SettlementStatus.WON)
        self.assertIs(settle_selection(Selection("p", "m1", Market.HALF_FULL, "home_home", 5), result), SettlementStatus.WON)
        self.assertIs(settle_selection(Selection("p", "m1", Market.CORRECT_SCORE, "2:1", 5), result), SettlementStatus.WON)
        self.assertIs(
            settle_selection(Selection("p", "m1", Market.CORRECT_SCORE, "other_home", 20), MatchResult("m1", ResultStatus.FINISHED, 6, 1)),
            SettlementStatus.WON,
        )
        self.assertIs(settle_selection(Selection("p", "m1", Market.MATCH_RESULT, "home", 2), MatchResult("m1", ResultStatus.POSTPONED)), SettlementStatus.PENDING)
        s1 = Selection("p1", "m1", Market.MATCH_RESULT, "home", 2)
        s2 = Selection("p2", "m2", Market.MATCH_RESULT, "away", 3)
        ticket = Ticket("t", (s1, s2), 2, NOW, {"m1": NOW + timedelta(hours=1), "m2": NOW + timedelta(hours=1)})
        settled = settle_ticket(ticket, {"m1": result, "m2": MatchResult("m2", ResultStatus.CANCELLED)})
        self.assertEqual((settled.status, settled.payout, settled.profit), (SettlementStatus.WON, 4, 2))


class BacktestTests(unittest.TestCase):
    def test_probability_metrics(self):
        rows = [ForecastObservation({"away": .1, "draw": .2, "home": .7}, "home")]
        self.assertGreater(log_loss(rows), 0)
        self.assertAlmostEqual(brier_score(rows), .14)
        self.assertGreaterEqual(ranked_probability_score(rows, ("away", "draw", "home")), 0)

    def test_roi_requires_trusted_odds_and_computes_drawdown(self):
        report = fixed_unit_returns([BetObservation(True, 2, True), BetObservation(False, 3, True), BetObservation(False, 2, True)])
        self.assertEqual((report.profit, report.roi, report.max_drawdown), (-1, -1 / 3, 2))
        with self.assertRaisesRegex(ValueError, "ROI is forbidden"):
            fixed_unit_returns([BetObservation(True, 2, False)])


if __name__ == "__main__":
    unittest.main()
