"""Low-frequency reader for the public Sporttery football calculator feed."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

UPSTREAM_URL = (
    "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
    "?poolCode=hhad%2Chad%2Ccrs%2Cttg%2Chafu&channel=c"
)
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://m.sporttery.cn/",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1",
}


class SportteryError(RuntimeError):
    """Raised when the official payload cannot be safely consumed."""


def validate_payload(payload: object) -> None:
    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        raise SportteryError("official feed did not report success")
    value = payload.get("value")
    if not isinstance(value, Mapping):
        raise SportteryError("unexpected official feed schema")
    groups = value.get("matchInfoList")
    if not isinstance(groups, list):
        raise SportteryError("unexpected official feed schema")
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("subMatchList"), list):
            raise SportteryError("unexpected official feed schema")
        if not all(isinstance(match, Mapping) for match in group["subMatchList"]):
            raise SportteryError("unexpected official feed schema")


def _decode_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SportteryError("official feed returned invalid JSON") from exc
    validate_payload(payload)
    return dict(payload)


def _curl_command(timeout: float) -> list[str]:
    executable = "curl.exe" if os.name == "nt" else "curl"
    return [
        executable,
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout),
        "-H",
        f"Accept: {HEADERS['Accept']}",
        "-H",
        f"Referer: {HEADERS['Referer']}",
        "-H",
        f"User-Agent: {HEADERS['User-Agent']}",
        UPSTREAM_URL,
    ]


def fetch_sporttery_payload(*, timeout: float = 20.0) -> dict[str, Any]:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    try:
        with urlopen(Request(UPSTREAM_URL, headers=HEADERS), timeout=timeout) as response:
            return _decode_payload(response.read().decode("utf-8"))
    except Exception as exc:
        # Some managed Windows environments block Python TLS while allowing the
        # system curl binary. Keep this fixed-host fallback non-shelling.
        try:
            completed = subprocess.run(
                _curl_command(timeout),
                check=True, capture_output=True, text=True, encoding="utf-8",
            )
            return _decode_payload(completed.stdout)
        except (OSError, subprocess.SubprocessError, SportteryError) as fallback_exc:
            raise SportteryError(
                f"official Sporttery feed unavailable: {type(exc).__name__}"
            ) from fallback_exc


def save_snapshot(payload: Mapping[str, Any], path: str | Path) -> Path:
    validate_payload(payload)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _odds(raw: object, keys: Mapping[str, str]) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        return {}
    result = {}
    for source, target in keys.items():
        try:
            value = float(raw.get(source, 0))
        except (TypeError, ValueError):
            continue
        if value > 1:
            result[target] = value
    return result


def _score_keys() -> dict[str, str]:
    keys = {f"s{h:02d}s{a:02d}": f"{h}:{a}" for h in range(6) for a in range(6)}
    keys.update({"s1sh": "other_home", "s1sd": "other_draw", "s1sa": "other_away"})
    return keys


def normalize_payload(
    payload: Mapping[str, Any], *, fetched_at: datetime | None = None
) -> list[dict[str, Any]]:
    """Convert all selling matches and five pools to the pipeline fixture contract."""
    validate_payload(payload)
    fetched_at = fetched_at or datetime.now(UTC)
    if fetched_at.tzinfo is None:
        raise SportteryError("fetched_at must be timezone-aware")
    result_keys = {"h": "home", "d": "draw", "a": "away"}
    total_keys = {f"s{i}": str(i) for i in range(7)} | {"s7": "7+"}
    half_full_keys = {
        "hh": "HH", "hd": "HD", "ha": "HA",
        "dh": "DH", "dd": "DD", "da": "DA",
        "ah": "AH", "ad": "AD", "aa": "AA",
    }
    fixtures = []
    for group in payload["value"]["matchInfoList"]:
        for match in group.get("subMatchList", []):
            if match.get("matchStatus") != "Selling":
                continue
            kickoff = datetime.fromisoformat(f"{match['matchDate']}T{match['matchTime']}+08:00")
            markets = {
                "match_result": _odds(match.get("had"), result_keys),
                "handicap_result": _odds(match.get("hhad"), result_keys),
                "correct_score": _odds(match.get("crs"), _score_keys()),
                "total_goals": _odds(match.get("ttg"), total_keys),
                "half_full": _odds(match.get("hafu"), half_full_keys),
            }
            handicap_raw = (match.get("hhad") or {}).get("goalLineValue", 0)
            fixtures.append({
                "match_id": str(match["matchId"]),
                "match_num": str(match.get("matchNumStr", "")),
                "competition": str(match.get("leagueAbbName", "")),
                "competition_code": str(match.get("leagueCode", "")),
                "home_team": str(match["homeTeamAbbName"]),
                "away_team": str(match["awayTeamAbbName"]),
                "kickoff": kickoff.isoformat(),
                "sale_cutoff": (kickoff - timedelta(minutes=10)).isoformat(),
                "sale_cutoff_estimated": True,
                "status": "Selling",
                "handicap": int(float(handicap_raw or 0)),
                "odds_as_of": fetched_at.isoformat(),
                "odds": {name: odds for name, odds in markets.items() if odds},
                "source": "sporttery-public-calculator",
            })
    return fixtures
