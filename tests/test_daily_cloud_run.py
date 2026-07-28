import json
import tempfile
import unittest
from pathlib import Path

from jingcai.notifications import NotificationFailure, NotificationResult, NotificationSummary
from scripts.daily_cloud_run import format_summary, run


PAYLOAD = {
    "success": True,
    "value": {"lastUpdateTime": "2026-07-23T10:20:00+08:00", "matchInfoList": []},
}


class DailyCloudRunTests(unittest.TestCase):
    def _runner(self, arguments: list[str]) -> dict:
        output = Path(arguments[arguments.index("--output") + 1])
        output.write_text("<html>strict daily-live report</html>", encoding="utf-8")
        return {
            "fixtures": 6,
            "candidates": 1,
            "source_as_of": "2026-07-23T02:20:00+00:00",
            "candidate_details": [{
                "match_id": "m1", "match_number": "周四001",
                "home_team": "主队", "away_team": "客队",
                "market": "match_result", "market_label": "胜平负",
                "outcome": "home", "outcome_label": "主胜",
                "decimal_odds": 2.1, "probability": 0.55, "conservative_ev": 0.08,
                "odds_as_of": "2026-07-23T02:20:00+00:00",
                "sale_cutoff": "2026-07-23T12:00:00+08:00",
            }],
        }

    def test_archives_html_json_and_uses_date_content_dedupe_key(self) -> None:
        captured = {}

        def notify(title, text, **kwargs):
            captured.update(title=title, text=text, **kwargs)
            return NotificationSummary(("feishu",), (NotificationResult("feishu", 200),), dedupe_key=kwargs["dedupe_key"])

        with tempfile.TemporaryDirectory() as directory:
            html, report_json, raw, result = run(
                Path(directory), fetcher=lambda: PAYLOAD, live_runner=self._runner, notifier=notify
            )
            self.assertTrue(html.exists())
            self.assertTrue(report_json.exists())
            self.assertTrue(raw.exists())
            self.assertTrue((Path(directory) / "model-ledger.jsonl").exists())
            report = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual((report["fixtures"], report["candidates"]), (6, 1))
            self.assertEqual(1, report["notification_candidates"])
            self.assertEqual("胜平负", report["candidate_details"][0]["market_label"])
            self.assertRegex(report["release_id"], r"^2026-07-23-[0-9a-f]{12}$")
            self.assertTrue(captured["require_configured"])
            self.assertEqual(f"daily-report:{report['release_id']}", captured["dedupe_key"])
            self.assertIn("周四001 主队 vs 客队", captured["text"])
            self.assertTrue(result.delivered)

    def test_does_not_push_outside_the_decision_window(self) -> None:
        notified = False

        def runner(arguments: list[str]) -> dict:
            result = self._runner(arguments)
            result["candidate_details"][0]["sale_cutoff"] = "2026-07-23T18:00:00+08:00"
            return result

        def notify(*args, **kwargs):
            nonlocal notified
            notified = True
            return NotificationSummary(("feishu",), (NotificationResult("feishu", 200),))

        with tempfile.TemporaryDirectory() as directory:
            _, report_json, _, result = run(Path(directory), fetcher=lambda: PAYLOAD, live_runner=runner, notifier=notify)
            self.assertEqual((False, True), (notified, result.duplicate))
            self.assertEqual(0, json.loads(report_json.read_text(encoding="utf-8"))["notification_candidates"])

    def test_all_notification_channels_failed_fails_the_task(self) -> None:
        def notify(*args, **kwargs):
            return NotificationSummary(("feishu",), failures=(NotificationFailure("feishu", "TimeoutError"),))

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "all configured"):
                run(Path(directory), fetcher=lambda: PAYLOAD, live_runner=self._runner, notifier=notify)

    def test_partial_notification_failure_requests_a_retry(self) -> None:
        def notify(*args, **kwargs):
            return NotificationSummary(
                ("feishu", "serverchan"),
                successes=(NotificationResult("feishu", 200),),
                failures=(NotificationFailure("serverchan", "TimeoutError"),),
            )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "one or more"):
                run(Path(directory), fetcher=lambda: PAYLOAD, live_runner=self._runner, notifier=notify)

    def test_uses_validated_local_snapshot_without_fetching(self) -> None:
        def no_fetch():
            raise AssertionError("network fetch must not run for a relayed snapshot")

        def notify(*args, **kwargs):
            return NotificationSummary(
                ("feishu",), (NotificationResult("feishu", 200),),
                dedupe_key=kwargs["dedupe_key"],
            )

        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "relay.json"
            snapshot.write_text(json.dumps(PAYLOAD), encoding="utf-8")
            run(
                Path(directory) / "out", fetcher=no_fetch, live_runner=self._runner,
                notifier=notify, snapshot_json=snapshot,
            )

    def test_summary_is_structured_and_contains_research_warning(self) -> None:
        summary = format_summary({
            "report_date": "2026-07-23", "fixtures": 6, "candidates": 2,
            "source_as_of": "2026-07-23T02:20:00+00:00", "model_state": "PAPER_ONLY",
            "candidate_details": [],
        })
        self.assertIn("**官方在售比赛**：6 场", summary)
        self.assertIn("**通过玩法级准入的模拟候选**：2 个", summary)
        self.assertIn("不保证中奖或盈利", summary)
        self.assertIn("今日无符合标准", summary)

    def test_summary_contains_stable_report_link(self) -> None:
        summary = format_summary({
            "report_date": "2026-07-23", "fixtures": 0, "candidates": 0,
            "source_as_of": "2026-07-23T02:20:00+00:00", "model_state": "PAPER_ONLY",
            "candidate_details": [],
        }, "https://example.test/reports/2026-07-23/r1/")
        self.assertIn("https://example.test/reports/2026-07-23/r1/", summary)


if __name__ == "__main__":
    unittest.main()
