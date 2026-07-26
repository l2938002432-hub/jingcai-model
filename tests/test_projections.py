import unittest

from jingcai.projections import public_release_projection


class PublicProjectionTests(unittest.TestCase):
    def test_only_explicit_public_fields_survive(self) -> None:
        projection = public_release_projection(
            {
                "release_id": "release-1",
                "release_hash": "abc",
                "report_date": "2026-07-26",
                "generated_at": "2026-07-26T10:20:00+08:00",
                "source_as_of": "2026-07-26T10:18:00+08:00",
                "model_state": "PAPER_ONLY",
                "personal_bankroll": 5000,
                "webhook": "secret",
            },
            fixtures=[
                {
                    "match_id": "m1",
                    "match_number": "周日001",
                    "home_team": "主队",
                    "away_team": "客队",
                    "odds": {"match_result": {"home": 2.0}},
                    "raw_payload": "private",
                }
            ],
            candidates=[
                {
                    "match_id": "m1",
                    "market_label": "胜平负",
                    "outcome_label": "主胜",
                    "decimal_odds": 2.0,
                    "actual_stake": 500,
                    "ticket_note": "private",
                }
            ],
            model_settlement={
                "stake": 10,
                "payout": 20,
                "profit": 10,
                "personal_profit": 999,
            },
        )
        serialized = repr(projection)
        self.assertNotIn("personal", serialized)
        self.assertNotIn("webhook", serialized)
        self.assertNotIn("ticket_note", serialized)
        self.assertNotIn("raw_payload", serialized)
        self.assertEqual("周日001", projection["fixtures"][0]["match_number"])
        self.assertEqual(10, projection["model_settlement"]["profit"])

    def test_required_release_identity_is_preserved(self) -> None:
        projection = public_release_projection(
            {
                "release_id": "r2",
                "release_hash": "hash2",
                "report_date": "2026-07-26",
                "generated_at": "now",
                "source_as_of": "source",
                "model_state": "PAUSED",
            }
        )
        self.assertEqual(("r2", "hash2"), (projection["release_id"], projection["release_hash"]))


if __name__ == "__main__":
    unittest.main()
