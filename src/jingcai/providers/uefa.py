"""Strict reader for UEFA's public match feed.

Only completed qualifying matches with an explicit 90-minute ``score.regular``
are accepted.  Malformed records are returned as quarantined observations and
must never silently become training data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://match.uefa.com/v5/matches"
HEADERS = {"Accept": "application/json", "User-Agent": "jingcai-research/0.1"}
Sender = Callable[[str, Mapping[str, str], float], object]


class UefaError(RuntimeError):
    """Raised when the UEFA response cannot be consumed safely."""


def _default_sender(url: str, headers: Mapping[str, str], timeout: float) -> object:
    with urlopen(Request(url, headers=dict(headers)), timeout=timeout) as response:
        return json.load(response)


def _items(payload: object) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get("matches"), list):
        values = payload["matches"]
    else:
        raise UefaError("unexpected UEFA response schema")
    if not all(isinstance(item, Mapping) for item in values):
        raise UefaError("UEFA match list contains a non-object")
    return values


def _phase(match: Mapping[str, Any]) -> str:
    value = match.get("competitionPhase")
    if isinstance(value, Mapping):
        value = value.get("code") or value.get("type") or value.get("name")
    return str(value or "").upper()


def _team(match: Mapping[str, Any], side: str) -> str:
    value = match.get(f"{side}Team")
    if isinstance(value, Mapping):
        name = value.get("internationalName") or value.get("name")
        if name:
            return str(name).strip()
    # Retain compatibility with the alternate teams[] representation without
    # guessing a side from array order.
    teams = match.get("teams")
    if isinstance(teams, list):
        for entry in teams:
            if not isinstance(entry, Mapping):
                continue
            position = str(entry.get("fieldPosition") or entry.get("side") or "").upper()
            if position != side.upper():
                continue
            team = entry.get("team", entry)
            if isinstance(team, Mapping):
                name = team.get("internationalName") or team.get("name")
                if name:
                    return str(name).strip()
    raise UefaError(f"missing {side} team")


def _kickoff(match: Mapping[str, Any]) -> datetime:
    raw = match.get("kickOffTime")
    if isinstance(raw, Mapping):
        raw = raw.get("dateTime")
    if not isinstance(raw, str) or not raw.strip():
        raise UefaError("missing kickoff time")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UefaError("invalid kickoff time") from exc
    if parsed.tzinfo is None:
        raise UefaError("kickoff time has no timezone")
    return parsed.astimezone(UTC)


def _regular_score(match: Mapping[str, Any]) -> tuple[int, int]:
    score = match.get("score")
    regular = score.get("regular") if isinstance(score, Mapping) else None
    if not isinstance(regular, Mapping):
        raise UefaError("missing regular 90-minute score")
    try:
        home, away = int(regular["home"]), int(regular["away"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UefaError("invalid regular 90-minute score") from exc
    if home < 0 or away < 0:
        raise UefaError("negative regular score")
    return home, away


def _label(value: object) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("code") or value.get("value")
    return str(value).strip() if value not in (None, "") else None


def normalize_match(
    match: Mapping[str, Any], *, source_url: str, fetched_at: datetime
) -> dict[str, Any]:
    """Normalize one qualifying match or raise instead of inventing data."""
    if _phase(match) != "QUALIFYING":
        raise UefaError("not a qualifying match")
    if fetched_at.tzinfo is None:
        raise UefaError("fetched_at must be timezone-aware")
    kickoff = _kickoff(match)
    home_goals, away_goals = _regular_score(match)
    provider_id = match.get("id") or match.get("matchId")
    if provider_id in (None, ""):
        raise UefaError("missing provider match id")
    canonical = json.dumps(match, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    aggregate = match.get("aggregateScore")
    if aggregate is None and isinstance(match.get("score"), Mapping):
        aggregate = match["score"].get("aggregate")
    return {
        "provider_match_id": f"uefa:{provider_id}",
        "competition": "UCLQ",
        "kickoff_utc": kickoff.isoformat(),
        "kickoff_date": kickoff.date().isoformat(),
        "home_team": _team(match, "home"),
        "away_team": _team(match, "away"),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "round": _label(match.get("round")),
        "leg": match.get("leg"),
        "aggregate": aggregate,
        "source_url": source_url,
        "fetched_at": fetched_at.astimezone(UTC).isoformat(),
        "source_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def fetch_qualifying_matches(
    season_year: int,
    *,
    sender: Sender = _default_sender,
    limit: int = 100,
    max_pages: int = 20,
    timeout: float = 20.0,
    fetched_at: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Fetch bounded pages, returning ``(accepted, quarantined)`` records."""
    if not 1955 <= season_year <= 2100:
        raise ValueError("season_year is outside a plausible range")
    if not 1 <= limit <= 500 or not 1 <= max_pages <= 100:
        raise ValueError("unsafe pagination bounds")
    fetched_at = fetched_at or datetime.now(UTC)
    accepted: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    for page in range(max_pages):
        query = urlencode({
            "competitionId": 1,
            "seasonYear": season_year,
            "limit": limit,
            "offset": page * limit,
            "order": "ASC",
        })
        url = f"{BASE_URL}?{query}"
        if not url.startswith("https://"):
            raise UefaError("UEFA endpoint must use HTTPS")
        try:
            payload = sender(url, HEADERS, timeout)
        except Exception as exc:
            raise UefaError("UEFA request failed") from exc
        items = _items(payload)
        for match in items:
            if _phase(match) != "QUALIFYING":
                continue
            try:
                accepted.append(normalize_match(match, source_url=url, fetched_at=fetched_at))
            except UefaError as exc:
                match_id = match.get("id") or match.get("matchId") or "unknown"
                quarantined.append({"provider_match_id": str(match_id), "reason": str(exc)})
        if len(items) < limit:
            break
    else:
        raise UefaError("UEFA pagination exceeded max_pages")
    return accepted, quarantined
