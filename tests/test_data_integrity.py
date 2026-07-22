import unittest

from jingcai.data_integrity import (
    ambiguous_numeric_date,
    detect_date_risks,
    reconcile_with_schedule,
)
from jingcai.identity import TeamAliases


def match(identifier: str, kickoff: str = "2024-05-03T23:30:00Z") -> dict[str, object]:
    return {
        "provider_match_id": identifier,
        "competition": "USA",
        "season": "2024",
        "kickoff_utc": kickoff,
        "home_team": "A Team",
        "away_team": "B Team",
        "home_goals": 2,
        "away_goals": 1,
    }


class DateRiskTests(unittest.TestCase):
    def test_flags_only_dates_with_two_valid_distinct_interpretations(self) -> None:
        self.assertTrue(ambiguous_numeric_date("03/05/2024"))
        self.assertTrue(ambiguous_numeric_date("03-05-2024 20:00"))
        self.assertFalse(ambiguous_numeric_date("13/05/2024"))
        self.assertFalse(ambiguous_numeric_date("2024-05-03"))
        self.assertFalse(ambiguous_numeric_date("11/11/2024"))

    def test_risk_report_is_deterministic(self) -> None:
        a, b = match("b"), match("a")
        a["source_match_date"] = "03/05/2024"
        b["source_match_date"] = "13/05/2024"
        self.assertEqual(["b"], [row["provider_match_id"] for row in detect_date_risks([a, b])])


class ReconciliationTests(unittest.TestCase):
    def test_unique_reference_corrects_date_without_swapping_guess(self) -> None:
        source = match("history", "2024-03-05T12:00:00Z")
        reference = match("trusted", "2024-05-03T23:30:00Z")
        result = reconcile_with_schedule([source], [reference])
        self.assertEqual("2024-05-03T23:30:00Z", result.corrected[0]["kickoff_utc"])
        self.assertEqual("trusted", result.corrected[0]["date_reference_id"])
        self.assertEqual((), result.quarantined)

    def test_date_only_reference_removes_false_utc_precision(self) -> None:
        source = match("history", "2024-03-05T12:00:00Z")
        reference = match("trusted")
        reference.pop("kickoff_utc")
        reference["kickoff_date"] = "2024-05-03"
        fixed = reconcile_with_schedule([source], [reference]).corrected[0]
        self.assertEqual("2024-05-03", fixed["kickoff_date"])
        self.assertNotIn("kickoff_utc", fixed)

    def test_explicit_team_aliases_allow_safe_cross_source_match(self) -> None:
        source = match("history")
        source["home_team"] = "Inter Miami"
        reference = match("trusted")
        reference["home_team"] = "Inter Miami CF"
        result = reconcile_with_schedule(
            [source], [reference], aliases=TeamAliases({"Inter Miami": ["Inter Miami CF"]})
        )
        self.assertEqual(1, len(result.corrected))

    def test_missing_and_duplicate_references_are_quarantined(self) -> None:
        source = match("history")
        missing = reconcile_with_schedule([source], [])
        self.assertEqual("schedule_match_not_found", missing.quarantined[0].reason)

        duplicate = reconcile_with_schedule([source], [match("r1"), match("r2")])
        self.assertEqual("schedule_match_ambiguous", duplicate.quarantined[0].reason)
        self.assertEqual(2, duplicate.quarantined[0].candidate_count)
        self.assertEqual((), duplicate.corrected)

    def test_score_and_home_away_order_are_part_of_identity(self) -> None:
        source = match("history")
        wrong_score = match("r1")
        wrong_score["home_goals"] = 1
        reversed_teams = match("r2")
        reversed_teams["home_team"], reversed_teams["away_team"] = (
            reversed_teams["away_team"], reversed_teams["home_team"]
        )
        result = reconcile_with_schedule([source], [wrong_score, reversed_teams])
        self.assertEqual("schedule_match_not_found", result.quarantined[0].reason)

    def test_output_is_independent_of_input_order(self) -> None:
        first = match("h1")
        second = match("h2")
        second["home_team"] = "C Team"
        reference1, reference2 = match("r1"), match("r2")
        reference2["home_team"] = "C Team"
        left = reconcile_with_schedule([second, first], [reference2, reference1])
        right = reconcile_with_schedule([first, second], [reference1, reference2])
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
