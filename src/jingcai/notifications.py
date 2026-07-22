from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.request import Request, urlopen
from urllib.parse import urlencode


Sender = Callable[..., Any]


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    status_code: int


def _response_payload(response: Any) -> dict[str, Any]:
    if not hasattr(response, "read"):
        return {}
    raw = response.read()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _post_json(url: str, payload: dict[str, Any], channel: str, sender: Sender = urlopen) -> NotificationResult:
    if not url.lower().startswith("https://"):
        raise ValueError("webhook URL must use HTTPS")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with sender(request, timeout=10) as response:
        status = int(response.status)
        if not 200 <= status < 300:
            raise RuntimeError(f"{channel} notification failed with HTTP {status}")
        response_payload = _response_payload(response)
        platform_code = response_payload.get("code", response_payload.get("errcode", 0))
        if platform_code not in (None, 0, "0"):
            raise RuntimeError(f"{channel} notification rejected with code {platform_code}")
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


def send_serverchan(send_key: str, title: str, text: str, sender: Sender = urlopen) -> NotificationResult:
    """Push one consolidated notification to personal WeChat via ServerChan Turbo."""
    key = send_key.strip()
    if not key or any(char in key for char in "/?#&"):
        raise ValueError("invalid ServerChan SendKey")
    url = f"https://sctapi.ftqq.com/{key}.send"
    body = urlencode({"title": title[:32], "desp": text}).encode("utf-8")
    request = Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )
    with sender(request, timeout=10) as response:
        status = int(response.status)
        payload = _response_payload(response)
        if not 200 <= status < 300 or payload.get("code") not in (0, "0"):
            raise RuntimeError(f"serverchan notification failed with HTTP {status}")
        return NotificationResult("serverchan", status)


def send_configured(title: str, text: str) -> list[NotificationResult]:
    """Send to every configured channel; an absent secret disables it."""
    results = []
    if url := os.environ.get("FEISHU_WEBHOOK_URL", "").strip():
        results.append(send_feishu(url, title, text))
    if url := os.environ.get("WECOM_WEBHOOK_URL", "").strip():
        results.append(send_wecom(url, title, text))
    if key := os.environ.get("SERVERCHAN_SENDKEY", "").strip():
        results.append(send_serverchan(key, title, text))
    return results
