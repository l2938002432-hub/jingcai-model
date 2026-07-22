"""Conservative team normalization and triple-key match identity resolution."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping


class MatchIdentityError(ValueError):
    """Base class for identity resolution failures."""


class MatchNotFoundError(MatchIdentityError):
    pass


class AmbiguousMatchError(MatchIdentityError):
    pass


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE)


class TeamAliases:
    def __init__(self, aliases: Mapping[str, Iterable[str]] | None = None) -> None:
        self._canonical: dict[str, str] = {}
        for canonical, variants in (aliases or {}).items():
            names = [canonical, *variants]
            for name in names:
                key = normalize_name(name)
                existing = self._canonical.get(key)
                if existing is not None and existing != canonical:
                    raise AmbiguousMatchError(f"alias {name!r} maps to both {existing!r} and {canonical!r}")
                self._canonical[key] = canonical

    def canonical(self, name: str) -> str:
        key = normalize_name(name)
        if not key:
            raise MatchIdentityError("team name is blank after normalization")
        return self._canonical.get(key, key)


def _utc(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MatchIdentityError("kickoff must include a timezone")
    return parsed.astimezone(timezone.utc)


def resolve_match(
    target: Mapping[str, object],
    candidates: Iterable[Mapping[str, object]],
    *,
    aliases: TeamAliases | None = None,
    kickoff_tolerance: timedelta = timedelta(minutes=5),
) -> Mapping[str, object]:
    """Resolve by competition, kickoff and ordered home/away teams.

    Zero and multiple matches are both hard failures; callers must never guess.
    """

    aliases = aliases or TeamAliases()
    competition = normalize_name(str(target["competition"]))
    kickoff = _utc(target["kickoff_utc"])
    home = aliases.canonical(str(target["home_team"]))
    away = aliases.canonical(str(target["away_team"]))
    matches = [
        item
        for item in candidates
        if normalize_name(str(item["competition"])) == competition
        and abs(_utc(item["kickoff_utc"]) - kickoff) <= kickoff_tolerance
        and aliases.canonical(str(item["home_team"])) == home
        and aliases.canonical(str(item["away_team"])) == away
    ]
    if not matches:
        raise MatchNotFoundError("no candidate matched competition, kickoff and ordered teams")
    if len(matches) != 1:
        ids = [str(item.get("provider_match_id", "<unknown>")) for item in matches]
        raise AmbiguousMatchError(f"multiple candidates matched: {', '.join(ids)}")
    return matches[0]
