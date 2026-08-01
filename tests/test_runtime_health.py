from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from jingcai.runtime_health import build_health_report


class RuntimeHealthTests(unittest.TestCase):
    def test_reports_latest_data_source_relay_and_market_quality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            daily, relay = root / "daily", root / "relay"
            daily.mkdir()
            relay.mkdir()
            (daily / "report-old.json").write_text(json.dumps({
                "generated_at": "2026-08-01T01:00:00+00:00", "model_state": "OLD",
            }), encoding="utf-8")
            (daily / "report-new.json").write_text(json.dumps({
                "generated_at": "2026-08-01T02:00:00+00:00",
                "source_as_of": "2026-08-01T01:45:00+00:00",
                "model_state": "PAPER_ONLY",
                "fixture_details": [
                    {"odds": {"match_result": {"home": 2.0}, "total_goals": {"2": 3.0}}},
                    {"odds": {market: {"x": 2.0} for market in ("match_result", "handicap_result", "correct_score", "total_goals", "half_full")}},
                ],
            }), encoding="utf-8")
            (relay / "last-success.json").write_text(json.dumps({
                "completed_at": "2026-08-01T01:50:00+00:00", "fixture_count": 2,
            }), encoding="utf-8")

            health = build_health_report(daily, relay_dir=relay, now=datetime(2026, 8, 1, 2, 0, tzinfo=UTC))

        self.assertEqual("healthy", health["status"])
        self.assertEqual("PAPER_ONLY", health["current_model_status"]["value"])
        self.assertEqual(900, health["source_age_seconds"])
        self.assertEqual("2026-08-01T01:50:00+00:00", health["last_success"]["relay"])
        quality = health["fixture_market_quality"]
        self.assertEqual((2, 2, 1), (quality["fixture_count"], quality["fixtures_with_any_market"], quality["fixtures_with_all_standard_markets"]))
        self.assertEqual(1, quality["market_coverage"]["correct_score"]["missing_fixtures"])

    def test_missing_or_corrupt_inputs_degrade_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relay = root / "relay"
            relay.mkdir()
            (relay / "last-success.json").write_text("not json", encoding="utf-8")
            health = build_health_report(root / "missing", relay_dir=relay, now=datetime(2026, 8, 1, tzinfo=UTC))

        self.assertEqual("unavailable", health["status"])
        self.assertEqual("UNKNOWN", health["current_model_status"]["value"])
        self.assertIsNone(health["source_age_seconds"])
        self.assertIn("daily_report_unavailable", health["warnings"])
        self.assertIn("relay_last_success_unavailable", health["warnings"])

    def test_missing_fixture_details_is_degraded_not_an_empty_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            daily = Path(directory)
            (daily / "report-one.json").write_text(json.dumps({
                "generated_at": "2026-08-01T00:00:00Z",
                "source_as_of": "2026-08-01T00:00:00Z",
                "model_state": "PAPER_ONLY",
            }), encoding="utf-8")
            health = build_health_report(daily, now=datetime(2026, 8, 1, tzinfo=UTC))

        self.assertEqual("degraded", health["status"])
        self.assertIn("fixture_markets_unavailable", health["warnings"])


if __name__ == "__main__":
    unittest.main()
