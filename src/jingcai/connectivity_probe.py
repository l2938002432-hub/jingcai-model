"""Minimal, non-persistent Sporttery connectivity probe for domestic CI."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


PROBE_URL = (
    "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
    "?poolCode=had&channel=c"
)
_HEADERS = {"Accept": "application/json", "Referer": "https://m.sporttery.cn/"}


def probe(
    *, timeout: float = 10.0,
    opener: Callable[..., Any] = urlopen,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[int, dict[str, object]]:
    """Check only availability and schema; never persist or print match contents."""
    checked_at = datetime.now(UTC).isoformat()
    started = clock()
    base: dict[str, object] = {"probe_version": 1, "checked_at_utc": checked_at}
    try:
        with opener(Request(PROBE_URL, headers=_HEADERS), timeout=timeout) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except Exception as exc:
        return 10, base | {"ok": False, "error_class": type(exc).__name__}
    latency_ms = round((clock() - started) * 1000)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 11, base | {"ok": False, "http_status": status, "latency_ms": latency_ms, "response_bytes": len(raw), "error_class": "InvalidJson"}
    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        return 12, base | {"ok": False, "http_status": status, "latency_ms": latency_ms, "response_bytes": len(raw), "error_class": "OfficialFailure"}
    value = payload.get("value")
    groups = value.get("matchInfoList") if isinstance(value, Mapping) else None
    if not isinstance(groups, list) or any(not isinstance(group, Mapping) or not isinstance(group.get("subMatchList"), list) for group in groups):
        return 13, base | {"ok": False, "http_status": status, "latency_ms": latency_ms, "response_bytes": len(raw), "error_class": "SchemaChanged"}
    match_count = sum(len(group["subMatchList"]) for group in groups)
    update_present = bool(value.get("lastUpdateTime"))
    fingerprint = hashlib.sha256(
        json.dumps(sorted(value.keys()), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]
    return 0, base | {
        "ok": True, "http_status": status, "latency_ms": latency_ms,
        "response_bytes": len(raw), "success_flag": True, "group_count": len(groups),
        "match_count": match_count, "official_update_present": update_present,
        "schema_fingerprint": fingerprint,
    }
