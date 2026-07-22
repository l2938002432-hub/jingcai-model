from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.request import Request, urlopen


Sender = Callable[..., Any]


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    status_code: int


def _post_json(url: str, payload: dict[str, Any], channel: str, sender: Sender = urlopen) -> NotificationResult:
    if not url.lower().startswith("https://"):
        raise ValueError("webhook URL must use HTTPS")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with sender(request, timeout=10) as response:
        status = int(response.status)
        if not 200 <= status < 300:
            raise RuntimeError(f"{channel} notification failed with HTTP {status}")
        return NotificationResult(channel, status)


def send_feishu(webhook_url: str, title: str, text: str, sender: Sender = urlopen) -> NotificationResult:
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": text}}],
        },
    }
    return _post_json(webhook_url, payload, "feishu", sender)


def send_wecom(webhook_url: str, title: str, text: str, sender: Sender = urlopen) -> NotificationResult:
    payload = {"msgtype": "markdown", "markdown": {"content": f"## {title}\n{text}"}}
    return _post_json(webhook_url, payload, "wecom", sender)

