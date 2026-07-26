import math
import unittest
from datetime import UTC, datetime, timedelta

from jingcai.pipeline import (
    build_paper_candidates,
    chinese_market_label,
    chinese_outcome_label,
    predict_all_markets,
    walk_forward_1x2,
)


def synthetic_matches(count: int = 24) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    teams = ("A", "B", "C", "D")
    rows = []
    for index in range(count):
        home = teams[index % 4]
        away = teams[(index + 1 + index // 4) % 4]
        if home == away:
            away = teams[(index + 2) % 4]
        rows.append(
            {
                "kickoff_utc": (start + timedelta(days=index)).isoformat(),
                "home_team": home,
                "away_team": away,
                "home_goals": (index * 3) % 4,
                "away_goals": (index * 2 + 1) % 3,
            }
        )
    return rows


class PipelineTests(unittest.TestCase):
    def test_user_facing_market_and_outcome_names_are_chinese(self) -> None:
        self.assertEqual("胜平负", chinese_market_label("match_result"))
        self.assertEqual("让球胜平负（-1）", chinese_market_label("handicap_result", -1))
        self.assertEqual("客胜", chinese_outcome_label("match_result", "away"))
        self.assertEqual("负平", chinese_outcome_label("half_full", "away_draw"))
        self.assertEqual("7+球", chinese_outcome_label("total_goals", "7+"))

    def test_walk_forward_compares_model_and_baseline_without_roi_claim(self) -> None:
        result = walk_forward_1x2(synthetic_matches(), min_train=12)
        self.assertEqual(12, result.evaluated_matches)
        self.assertTrue(math.isfinite(result.model_log_loss))
        self.assertTrue(math.isfinite(result.baseline_log_loss))
        self.assertIn("UNAVAILABLE", result.roi_status)

    def test_walk_forward_accepts_frozen_time_decay(self) -> None:
        result = walk_forward_1x2(synthetic_matches(), min_train=12, half_life_days=365)
        self.assertEqual(12, result.evaluated_matches)

    def test_predict_all_five_markets(self) -> None:
        result = predict_all_markets(synthetic_matches(), home_team="A", away_team="B", handicap=-1)
        for market in ("match_result", "handicap_result", "total_goals", "correct_score", "half_full"):
            self.assertAlmostEqual(1.0, sum(result[market].values()), places=9)
        self.assertEqual("RESEARCH", result["state"])
        self.assertEqual(9, len(result["half_full"]))

    def test_paper_candidates_choose_positive_conservative_ev_only(self) -> None:
        fixtures = [
            {
                "match_id": "m1",
                "competition_code": "NTL",
                "home_team": "A",
                "away_team": "B",
                "handicap": 0,
                "odds_as_of": "2026-07-22T10:00:00+00:00",
                "sale_cutoff": "2026-07-22T12:00:00+00:00",
                "odds": {"match_result": {"home": 10.0, "draw": 10.0, "away": 10.0}},
            }
        ]
        candidates = build_paper_candidates(
            synthetic_matches(),
            fixtures,
            safety_margin=0.03,
            prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
        )
        self.assertEqual(1, len(candidates))
        self.assertGreater(candidates[0]["conservative_ev"], 0)
        self.assertIn("market_probability", candidates[0])
        self.assertEqual("胜平负", candidates[0]["market_label"])
        self.assertIn(candidates[0]["outcome_label"], {"主胜", "平", "客胜"})
        self.assertEqual(("A", "B"), (candidates[0]["home_team"], candidates[0]["away_team"]))

    def test_paper_candidates_allow_empty_best_action(self) -> None:
        fixtures = [
            {
                "match_id": "m1",
                "competition_code": "NTL",
                "home_team": "A",
                "away_team": "B",
                "odds_as_of": "2026-07-22T10:00:00+00:00",
                "sale_cutoff": "2026-07-22T12:00:00+00:00",
                "odds": {"match_result": {"home": 1.01, "draw": 1.01, "away": 1.01}},
            }
        ]
        self.assertEqual(
            [],
            build_paper_candidates(
                synthetic_matches(),
                fixtures,
                prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
            ),
        )

    def test_paper_candidates_reject_stale_or_future_information(self) -> None:
        fixture = {
            "match_id": "m1",
            "competition_code": "NTL",
            "home_team": "A",
            "away_team": "B",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 2.0, "draw": 3.0, "away": 4.0}},
        }
        self.assertEqual(
            [],
            build_paper_candidates(
                synthetic_matches(), [fixture], prediction_time=datetime(2026, 7, 22, 13, tzinfo=UTC)
            ),
        )
        future = dict(fixture, odds_as_of="2026-07-22T11:30:00+00:00")
        with self.assertRaisesRegex(ValueError, "odds_as_of"):
            build_paper_candidates(
                synthetic_matches(), [future], prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC)
            )

    def test_unknown_teams_never_generate_recommendations(self) -> None:
        fixture = {
            "match_id": "m2", "competition_code": "NTL", "home_team": "UNKNOWN", "away_team": "B",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 10.0, "draw": 10.0, "away": 10.0}},
        }
        self.assertEqual([], build_paper_candidates(
            synthetic_matches(), [fixture], prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC)
        ))

    def test_unapproved_high_ev_correct_score_is_blocked(self) -> None:
        fixture = {
            "match_id": "m3", "competition_code": "NTL", "home_team": "A", "away_team": "B",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"correct_score": {"1:0": 1000.0}},
        }
        self.assertEqual([], build_paper_candidates(
            synthetic_matches(), [fixture], prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC)
        ))

    def test_explicitly_approved_match_result_can_pass(self) -> None:
        fixture = {
            "match_id": "m4", "competition_code": "TEST", "home_team": "A", "away_team": "B",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 10.0, "draw": 10.0, "away": 10.0}},
        }
        acceptance = {"TEST": {"approved": True, "markets": {"match_result": True}}}
        candidates = build_paper_candidates(
            synthetic_matches(), [fixture], acceptance_config=acceptance,
            prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual("match_result", candidates[0]["market"])

    def test_fixture_predictor_can_safely_cover_team_outside_local_history(self) -> None:
        fixture = {
            "match_id": "ucl-1", "competition_code": "UCL",
            "home_team": "New Home", "away_team": "New Away",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 3.0, "draw": 3.0, "away": 3.0}},
        }
        prediction = {"match_result": {"home": 0.6, "draw": 0.2, "away": 0.2}}
        candidates = build_paper_candidates(
            synthetic_matches(), [fixture],
            acceptance_config={"UCL": {"approved": True, "markets": {"match_result": True}}},
            fixture_predictor=lambda _: prediction,
            prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual("home", candidates[0]["outcome"])

    def test_fixture_predictor_none_preserves_unknown_team_fail_closed(self) -> None:
        fixture = {
            "match_id": "ucl-2", "competition_code": "UCL",
            "home_team": "New Home", "away_team": "New Away",
            "odds_as_of": "2026-07-22T10:00:00+00:00",
            "sale_cutoff": "2026-07-22T12:00:00+00:00",
            "odds": {"match_result": {"home": 10.0, "draw": 10.0, "away": 10.0}},
        }
        self.assertEqual([], build_paper_candidates(
            synthetic_matches(), [fixture],
            acceptance_config={"UCL": {"approved": True, "markets": {"match_result": True}}},
            fixture_predictor=lambda _: None,
            prediction_time=datetime(2026, 7, 22, 11, tzinfo=UTC),
        ))


if __name__ == "__main__":
    unittest.main()
