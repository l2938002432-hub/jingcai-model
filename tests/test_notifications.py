import json
import os
import unittest
from unittest.mock import patch

from jingcai.notifications import send_configured, send_feishu, send_serverchan, send_wecom


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
            self.assertEqual([], send_configured("日报", "内容"))

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
