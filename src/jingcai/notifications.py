from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol
from urllib.request import Request, urlopen
from urllib.parse import urlencode


Sender = Callable[..., Any]


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    status_code: int


@dataclass(frozen=True)
class NotificationFailure:
    channel: str
    error_type: str
    message: str = "delivery failed"


@dataclass(frozen=True)
class NotificationSummary:
    """Aggregate delivery outcome. Iteration yields successes for legacy callers."""

    configured_channels: tuple[str, ...]
    successes: tuple[NotificationResult, ...] = ()
    failures: tuple[NotificationFailure, ...] = ()
    duplicate: bool = False
    dedupe_key: str | None = None

    def __iter__(self) -> Iterator[NotificationResult]:
        return iter(self.successes)

    @property
    def delivered(self) -> bool:
        return bool(self.successes)


class DedupeStore(Protocol):
    """Minimal persistence boundary; production may back this with a file or database."""

    def contains(self, key: str) -> bool: ...

    def add(self, key: str) -> None: ...


class MemoryDedupeStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def contains(self, key: str) -> bool:
        return key in self._keys

    def add(self, key: str) -> None:
        self._keys.add(key)


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


def send_configured(
    title: str,
    text: str,
    *,
    require_configured: bool = False,
    dedupe_key: str | None = None,
    dedupe_store: DedupeStore | None = None,
) -> NotificationSummary:
    """Send independently to all configured channels and summarize every outcome.

    Exceptions are reduced to their type and a generic message so webhook URLs and
    SendKeys embedded in transport errors cannot escape through reports or logs.
    """
    configured: list[tuple[str, Callable[[], NotificationResult]]] = []
    if url := os.environ.get("FEISHU_WEBHOOK_URL", "").strip():
        configured.append(("feishu", lambda url=url: send_feishu(url, title, text)))
    if url := os.environ.get("WECOM_WEBHOOK_URL", "").strip():
        configured.append(("wecom", lambda url=url: send_wecom(url, title, text)))
    if key := os.environ.get("SERVERCHAN_SENDKEY", "").strip():
        configured.append(("serverchan", lambda key=key: send_serverchan(key, title, text)))

    channel_names = tuple(channel for channel, _send in configured)
    if not configured and require_configured:
        raise RuntimeError("no notification channel configured")
    if dedupe_key is not None and dedupe_store is None:
        raise ValueError("dedupe_store is required when dedupe_key is provided")
    delivered_keys = {
        channel: f"{dedupe_key}:{channel}" for channel in channel_names
    } if dedupe_key is not None else {}
    if delivered_keys and dedupe_store is not None and all(
        dedupe_store.contains(key) for key in delivered_keys.values()
    ):
        return NotificationSummary(channel_names, duplicate=True, dedupe_key=dedupe_key)

    successes: list[NotificationResult] = []
    failures: list[NotificationFailure] = []
    for channel, send in configured:
        if dedupe_store is not None and channel in delivered_keys and dedupe_store.contains(delivered_keys[channel]):
            continue
        try:
            result = send()
            successes.append(result)
            if dedupe_store is not None and channel in delivered_keys:
                dedupe_store.add(delivered_keys[channel])
        except Exception as exc:  # isolate one transport without suppressing its outcome
            failures.append(NotificationFailure(channel, type(exc).__name__))

    return NotificationSummary(
        channel_names,
        tuple(successes),
        tuple(failures),
        dedupe_key=dedupe_key,
    )
