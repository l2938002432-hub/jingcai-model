import json
import unittest

from jingcai.notifications import send_feishu, send_wecom


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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


if __name__ == "__main__":
    unittest.main()
