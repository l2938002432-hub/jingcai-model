import json
import os
import unittest
from unittest.mock import patch

from jingcai.notifications import (
    MemoryDedupeStore,
    NotificationResult,
    send_configured,
    send_feishu,
    send_serverchan,
    send_wecom,
)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"code": 0}'


class NotificationTests(unittest.TestCase):
    def test_feishu_payload_and_no_secret_logging(self) -> None:
        captured = {}

        def sender(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse()

        result = send_feishu("https://example.invalid/secret", "日报", "无正式推荐", sender)
        self.assertEqual("feishu", result.channel)
        self.assertEqual("interactive", captured["body"]["msg_type"])
        self.assertEqual(10, captured["timeout"])

    def test_wecom_requires_https_and_uses_markdown(self) -> None:
        with self.assertRaises(ValueError):
            send_wecom("http://unsafe.invalid", "日报", "内容")

        def sender(request, timeout):
            self.assertIn(b"markdown", request.data)
            return FakeResponse()

        self.assertEqual("wecom", send_wecom("https://example.invalid", "日报", "内容", sender).channel)

    def test_platform_error_is_not_treated_as_success(self) -> None:
        class RejectedResponse(FakeResponse):
            def read(self):
                return b'{"errcode": 40001}'

        with self.assertRaises(RuntimeError):
            send_wecom(
                "https://example.invalid",
                "日报",
                "内容",
                lambda *_args, **_kwargs: RejectedResponse(),
            )

    def test_send_configured_skips_absent_channels(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            summary = send_configured("日报", "内容")
        self.assertEqual((), summary.configured_channels)
        self.assertFalse(summary.delivered)

    def test_send_configured_can_require_a_channel(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "no notification channel configured"):
                send_configured("日报", "内容", require_configured=True)

    def test_channel_failures_are_isolated_and_sanitized(self) -> None:
        secret = "secret-webhook-token"
        env = {"FEISHU_WEBHOOK_URL": f"https://example.invalid/{secret}", "SERVERCHAN_SENDKEY": "SCT_KEY"}
        with patch.dict(os.environ, env, clear=True), patch(
            "jingcai.notifications.send_feishu", side_effect=RuntimeError(f"failed {secret}")
        ), patch(
            "jingcai.notifications.send_serverchan", return_value=NotificationResult("serverchan", 200)
        ):
            summary = send_configured("日报", "内容")
        self.assertEqual(("feishu", "serverchan"), summary.configured_channels)
        self.assertEqual(("serverchan",), tuple(item.channel for item in summary.successes))
        self.assertEqual("RuntimeError", summary.failures[0].error_type)
        self.assertNotIn(secret, repr(summary))

    def test_dedupe_marks_only_a_delivered_notification(self) -> None:
        store = MemoryDedupeStore()
        env = {"FEISHU_WEBHOOK_URL": "https://example.invalid/hook"}
        with patch.dict(os.environ, env, clear=True), patch(
            "jingcai.notifications.send_feishu", return_value=NotificationResult("feishu", 200)
        ) as sender:
            first = send_configured("日报", "内容", dedupe_key="2026-07-22:daily", dedupe_store=store)
            second = send_configured("日报", "内容", dedupe_key="2026-07-22:daily", dedupe_store=store)
        self.assertTrue(first.delivered)
        self.assertTrue(second.duplicate)
        self.assertEqual(1, sender.call_count)

    def test_complete_failure_remains_retryable(self) -> None:
        store = MemoryDedupeStore()
        env = {"FEISHU_WEBHOOK_URL": "https://example.invalid/hook"}
        with patch.dict(os.environ, env, clear=True), patch(
            "jingcai.notifications.send_feishu", side_effect=RuntimeError("offline")
        ) as sender:
            first = send_configured("日报", "内容", dedupe_key="daily", dedupe_store=store)
            second = send_configured("日报", "内容", dedupe_key="daily", dedupe_store=store)
        self.assertFalse(first.delivered)
        self.assertFalse(second.duplicate)
        self.assertEqual(2, sender.call_count)

    def test_retry_sends_only_channels_that_failed_previously(self) -> None:
        store = MemoryDedupeStore()
        env = {"FEISHU_WEBHOOK_URL": "https://example.invalid/hook", "SERVERCHAN_SENDKEY": "SCT_KEY"}
        with patch.dict(os.environ, env, clear=True), patch(
            "jingcai.notifications.send_feishu", return_value=NotificationResult("feishu", 200)
        ) as feishu, patch(
            "jingcai.notifications.send_serverchan",
            side_effect=[RuntimeError("offline"), NotificationResult("serverchan", 200)],
        ) as wechat:
            first = send_configured("日报", "内容", dedupe_key="daily", dedupe_store=store)
            second = send_configured("日报", "内容", dedupe_key="daily", dedupe_store=store)
            third = send_configured("日报", "内容", dedupe_key="daily", dedupe_store=store)
        self.assertEqual(("feishu",), tuple(item.channel for item in first.successes))
        self.assertEqual(("serverchan",), tuple(item.channel for item in second.successes))
        self.assertTrue(third.duplicate)
        self.assertEqual(1, feishu.call_count)
        self.assertEqual(2, wechat.call_count)

    def test_serverchan_uses_form_body_without_logging_key(self) -> None:
        captured = {}

        def sender(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = request.data.decode("utf-8")
            return FakeResponse()

        result = send_serverchan("SCT_TEST_KEY", "竞彩日报", "研究候选", sender)
        self.assertEqual("serverchan", result.channel)
        self.assertIn("title=", captured["body"])
        self.assertTrue(captured["url"].endswith("/SCT_TEST_KEY.send"))


if __name__ == "__main__":
    unittest.main()
