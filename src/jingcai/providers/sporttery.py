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
RESULTS_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getUniformMatchResultV1.qry"
)
FIXED_BONUS_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry"
)
INJURY_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getInjurySuspensionV1.qry"
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


def _decode_json(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SportteryError("official feed returned invalid JSON") from exc
    return dict(payload)


def _curl_command(url: str, timeout: float) -> list[str]:
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
        url,
    ]


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=timeout) as response:
            return _decode_json(response.read().decode("utf-8"))
    except Exception as exc:
        # Some managed Windows environments block Python TLS while allowing the
        # system curl binary. Keep this fixed-host fallback non-shelling.
        try:
            completed = subprocess.run(
                _curl_command(url, timeout),
                check=True, capture_output=True, text=True, encoding="utf-8",
            )
            return _decode_json(completed.stdout)
        except (OSError, subprocess.SubprocessError, SportteryError) as fallback_exc:
            raise SportteryError(
                f"official Sporttery feed unavailable: {type(exc).__name__}"
            ) from fallback_exc


def _require_success(payload: Mapping[str, Any], *, endpoint: str) -> dict[str, Any]:
    if payload.get("success") is not True:
        raise SportteryError(f"official {endpoint} feed did not report success")
    return dict(payload)


def fetch_sporttery_payload(*, timeout: float = 20.0) -> dict[str, Any]:
    payload = _fetch_json(UPSTREAM_URL, timeout=timeout)
    try:
        validate_payload(payload)
    except SportteryError as exc:
        raise SportteryError("official Sporttery feed unavailable: invalid schema") from exc
    return payload


def fetch_uniform_results(
    match_begin_date: str,
    match_end_date: str,
    *,
    page_no: int = 1,
    page_size: int = 100,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Read official historical results without guessing result fields.

    Callers must retain the raw payload because the upstream schema is not a
    contracted public API. Date values are deliberately explicit ISO dates.
    """
    if page_no < 1 or not 1 <= page_size <= 100:
        raise ValueError("page_no must be positive and page_size must be 1..100")
    query = (
        f"?matchBeginDate={match_begin_date}&matchEndDate={match_end_date}&leagueId="
        f"&pageSize={page_size}&pageNo={page_no}&isFix=0&matchPage=1&pcOrWap=1"
    )
    return _require_success(_fetch_json(RESULTS_URL + query, timeout=timeout), endpoint="result")


def fetch_fixed_bonus_history(match_id: str | int, *, timeout: float = 20.0) -> dict[str, Any]:
    if not str(match_id).strip():
        raise ValueError("match_id is required")
    return _require_success(
        _fetch_json(f"{FIXED_BONUS_URL}?clientCode=3001&matchId={match_id}", timeout=timeout),
        endpoint="fixed-bonus",
    )


def fetch_injury_suspension(match_id: str | int, *, timeout: float = 20.0) -> dict[str, Any]:
    if not str(match_id).strip():
        raise ValueError("match_id is required")
    return _require_success(
        _fetch_json(f"{INJURY_URL}?sportteryMatchId={match_id}", timeout=timeout),
        endpoint="injury-suspension",
    )


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


_HISTORY_MARKETS = {
    "had": "match_result", "hhad": "handicap_result", "ttg": "total_goals",
    "crs": "correct_score", "hafu": "half_full",
}
_HISTORY_METADATA = {
    "updateDate", "updateTime", "bonusDate", "bonusTime", "date", "time",
    "goalLineValue", "goalLine", "matchId", "poolCode",
}


def _history_time(item: Mapping[str, Any]) -> datetime:
    date = item.get("updateDate") or item.get("bonusDate") or item.get("date")
    clock = item.get("updateTime") or item.get("bonusTime") or item.get("time")
    raw = item.get("updateDateTime")
    if raw is not None and "T" in str(raw):
        candidate = str(raw).replace("Z", "+00:00")
    elif date is not None and clock is not None:
        candidate = f"{date}T{clock}+08:00"
    else:
        raise SportteryError("official fixed-bonus row has no usable update time")
    try:
        value = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SportteryError("official fixed-bonus row has invalid update time") from exc
    if value.tzinfo is None:
        raise SportteryError("official fixed-bonus row time zone is unknown")
    return value.astimezone(UTC)


def normalize_fixed_bonus_history(
    payload: Mapping[str, Any], *, match_id: str | int, ingested_at: datetime
) -> list[dict[str, Any]]:
    """Normalize official historic fixed-bonus points without using retrieval time.

    ``published_at`` is the upstream update timestamp and is the only timestamp
    suitable for historical replay. ``ingested_at`` exists solely for audit.
    """
    if payload.get("success") is not True:
        raise SportteryError("official fixed-bonus feed did not report success")
    if ingested_at.tzinfo is None:
        raise ValueError("ingested_at must be timezone-aware")
    value = payload.get("value")
    if not isinstance(value, Mapping):
        raise SportteryError("official fixed-bonus payload has no value mapping")
    rows: list[dict[str, Any]] = []
    for code, market in _HISTORY_MARKETS.items():
        series: object = value.get(code)
        if series is None:
            series = value.get(f"{code}List") or value.get(f"{code}BonusList")
        if isinstance(series, Mapping):
            series = series.get("list") or series.get("data") or [series]
        if series is None:
            continue
        if not isinstance(series, list):
            raise SportteryError(f"official fixed-bonus {code} history has invalid schema")
        for item in series:
            if not isinstance(item, Mapping):
                raise SportteryError("official fixed-bonus history contains a non-object row")
            odds = _odds(item, {str(key): str(key) for key in item if key not in _HISTORY_METADATA})
            if not odds:
                raise SportteryError("official fixed-bonus history row has no valid odds")
            record = {
                "match_id": str(match_id), "market": market, "market_code": code,
                "published_at": _history_time(item).isoformat(),
                "ingested_at": ingested_at.astimezone(UTC).isoformat(),
                "odds": odds, "source": "sporttery-uniform-fixed-bonus",
            }
            if code == "hhad" and item.get("goalLineValue") is not None:
                record["handicap"] = str(item["goalLineValue"])
            rows.append(record)
    if not rows:
        raise SportteryError("official fixed-bonus payload has no recognized market history")
    rows.sort(key=lambda row: (str(row["market"]), str(row["published_at"])))
    return rows
