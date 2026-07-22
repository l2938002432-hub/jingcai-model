from datetime import UTC, datetime
import unittest
from urllib.parse import parse_qs, urlparse

from jingcai.providers.uefa import UefaError, fetch_qualifying_matches


def _match(match_id: int = 7) -> dict:
    return {
        "id": match_id,
        "competitionPhase": "QUALIFYING",
        "kickOffTime": {"dateTime": "2025-07-08T18:00:00Z"},
        "homeTeam": {"internationalName": "Kairat Almaty"},
        "awayTeam": {"internationalName": "Olimpija Ljubljana"},
        "score": {"regular": {"home": 1, "away": 1}, "total": {"home": 3, "away": 2}},
        "round": {"name": "First qualifying round"},
        "leg": 1,
        "aggregateScore": {"home": 1, "away": 1},
    }


class UefaProviderTests(unittest.TestCase):
 def test_fetches_pages_and_normalizes_only_qualifying(self) -> None:
    calls = []

    def sender(url, headers, timeout):
        calls.append(url)
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        if offset == 0:
            other = _match(8)
            other["competitionPhase"] = "LEAGUE"
            return [_match(), other]
        return []

    rows, quarantine = fetch_qualifying_matches(
        2025, sender=sender, limit=2, fetched_at=datetime(2025, 7, 9, tzinfo=UTC)
    )
    self.assertEqual(2, len(calls))
    self.assertEqual("uefa:7", rows[0]["provider_match_id"])
    self.assertEqual((1, 1), (rows[0]["home_goals"], rows[0]["away_goals"]))
    self.assertEqual("First qualifying round", rows[0]["round"])
    self.assertTrue(rows[0]["source_url"].startswith("https://match.uefa.com/"))
    self.assertEqual(64, len(rows[0]["source_hash"]))
    self.assertEqual([], quarantine)


 def test_missing_regular_score_is_quarantined_and_total_is_not_used(self) -> None:
    bad = _match()
    bad["score"] = {"total": {"home": 3, "away": 2}}
    rows, quarantine = fetch_qualifying_matches(2025, sender=lambda *_: [bad], limit=2)
    self.assertEqual([], rows)
    self.assertIn("regular 90-minute", quarantine[0]["reason"])


 def test_missing_critical_fields_are_quarantined(self) -> None:
    for field in ("homeTeam", "kickOffTime"):
        with self.subTest(field=field):
            bad = _match()
            del bad[field]
            rows, quarantine = fetch_qualifying_matches(2025, sender=lambda *_: [bad], limit=2)
            self.assertEqual([], rows)
            self.assertEqual(1, len(quarantine))


 def test_hard_page_limit_fails_closed(self) -> None:
    with self.assertRaisesRegex(UefaError, "max_pages"):
        fetch_qualifying_matches(2025, sender=lambda *_: [_match()], limit=1, max_pages=2)


 def test_rejects_unexpected_payload(self) -> None:
    with self.assertRaisesRegex(UefaError, "schema"):
        fetch_qualifying_matches(2025, sender=lambda *_: {"unexpected": []})


if __name__ == "__main__":
    unittest.main()
