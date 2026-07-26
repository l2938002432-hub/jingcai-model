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
        return {"fixtures": 6, "candidates": 2, "source_as_of": "2026-07-23T02:20:00+00:00"}

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
            report = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual((report["fixtures"], report["candidates"]), (6, 2))
            self.assertTrue(captured["require_configured"])
            self.assertRegex(captured["dedupe_key"], r"^daily-report:2026-07-23:[0-9a-f]{64}$")
            self.assertTrue(result.delivered)

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
        })
        self.assertIn("**官方在售比赛**：6 场", summary)
        self.assertIn("**通过玩法级准入的模拟候选**：2 个", summary)
        self.assertIn("不保证中奖或盈利", summary)


if __name__ == "__main__":
    unittest.main()
