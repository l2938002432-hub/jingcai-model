"""Leakage-safe construction of minimal cross-league training examples.

The builder intentionally has no model dependency.  It produces a small,
auditable table from completed historical matches and point-in-time ClubElo
snapshots.  Scores are labels only: every feature is calculated before the
row's kickoff, and matches with the same kickoff are held out as a group.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from jingcai.identity import MatchIdentityError, TeamAliases
from jingcai.models.poisson import match_timestamp
from jingcai.providers.club_elo_history import ClubEloHistory, ClubEloHistoryError


@dataclass(frozen=True)
class RejectedTrainingMatch:
    provider_match_id: str
    reason: str


@dataclass(frozen=True)
class TrainingBuildResult:
    """Rows plus explicit exclusions, so coverage cannot be silently inflated."""

    rows: tuple[dict[str, object], ...]
    rejected: tuple[RejectedTrainingMatch, ...]
    input_matches: int
    exact_kickoff_matches: int
    date_only_matches: int
    date_only_policy: str

    @property
    def coverage(self) -> dict[str, object]:
        rejected_by_reason = Counter(item.reason for item in self.rejected)
        return {
            "input_matches": self.input_matches,
            "exact_kickoff_matches": self.exact_kickoff_matches,
            "date_only_matches": self.date_only_matches,
            "date_only_policy": self.date_only_policy,
            "accepted_matches": len(self.rows),
            "rejected_matches": len(self.rejected),
            "coverage_rate": len(self.rows) / self.input_matches if self.input_matches else 0.0,
            # Date-only source rows can only be used in a day-frozen research
            # set.  They have no valid point-in-time relation to odds.
            "safe_for_economic_validation": self.date_only_policy == "reject",
            "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        }


@dataclass
class _TeamHistory:
    matches: int = 0
    goals_for: int = 0
    goals_against: int = 0

    def snapshot(self) -> dict[str, object]:
        if not self.matches:
            return {"prior_matches": 0, "prior_goals_for_per_match": None, "prior_goals_against_per_match": None}
        return {
            "prior_matches": self.matches,
            "prior_goals_for_per_match": self.goals_for / self.matches,
            "prior_goals_against_per_match": self.goals_against / self.matches,
        }

    def add(self, goals_for: int, goals_against: int) -> None:
        self.matches += 1
        self.goals_for += goals_for
        self.goals_against += goals_against


@dataclass(frozen=True)
class _Match:
    source: Mapping[str, object]
    provider_match_id: str
    competition: str
    season: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


def build_cross_league_training_rows(
    matches: Iterable[Mapping[str, object]],
    *,
    elo_history: ClubEloHistory,
    aliases: TeamAliases | None = None,
    date_only_policy: Literal["reject", "freeze_utc_day"] = "reject",
) -> TrainingBuildResult:
    """Build standardized rows using only facts available before each kickoff.

    Inputs must be completed matches. Invalid inputs and teams without a
    strictly earlier Elo snapshot are returned with a reason instead of being
    guessed or backfilled. ``reject`` is the default for date-only source rows.
    ``freeze_utc_day`` creates a larger *research-only* set: every match on a
    UTC date is built before any result from that date enters history. It must
    not be used for odds/economic validation because the true decision time is
    unknown. Result labels are never used to build their own features.
    """
    if date_only_policy not in {"reject", "freeze_utc_day"}:
        raise ValueError("date_only_policy must be 'reject' or 'freeze_utc_day'")
    aliases = aliases or TeamAliases()
    prepared: list[_Match] = []
    rejected: list[RejectedTrainingMatch] = []
    input_matches = 0
    exact_kickoff_matches = 0
    date_only_matches = 0
    for index, source in enumerate(matches):
        input_matches += 1
        fallback_id = f"input:{index}"
        try:
            match = _normalize_match(source, aliases, fallback_id)
            is_date_only = source.get("kickoff_precision") == "date_only"
            if is_date_only:
                date_only_matches += 1
            else:
                exact_kickoff_matches += 1
            if is_date_only and date_only_policy == "reject":
                rejected.append(RejectedTrainingMatch(match.provider_match_id, "kickoff_time_unknown"))
            else:
                prepared.append(match)
        except (KeyError, TypeError, ValueError, MatchIdentityError) as exc:
            provider_match_id = str(source.get("provider_match_id", fallback_id))
            rejected.append(RejectedTrainingMatch(provider_match_id, _input_reason(exc)))

    prepared.sort(key=lambda item: (_history_cutoff(item, date_only_policy), item.provider_match_id))
    histories: dict[str, _TeamHistory] = defaultdict(_TeamHistory)
    rows: list[dict[str, object]] = []

    position = 0
    while position < len(prepared):
        cutoff = _history_cutoff(prepared[position], date_only_policy)
        group: list[_Match] = []
        while position < len(prepared) and _history_cutoff(prepared[position], date_only_policy) == cutoff:
            group.append(prepared[position])
            position += 1

        # Create all rows before adding this group to the history.  This is
        # essential for simultaneous matches: their final scores were not
        # visible to each other at decision time.
        for match in group:
            try:
                home_elo = elo_history.observation_before(match.home_team, match.kickoff_utc)
            except ClubEloHistoryError:
                rejected.append(RejectedTrainingMatch(match.provider_match_id, "home_elo_missing_before_kickoff"))
                continue
            try:
                away_elo = elo_history.observation_before(match.away_team, match.kickoff_utc)
            except ClubEloHistoryError:
                rejected.append(RejectedTrainingMatch(match.provider_match_id, "away_elo_missing_before_kickoff"))
                continue
            rows.append(_training_row(match, home_elo, away_elo, histories, date_only_policy))

        for match in group:
            histories[match.home_team].add(match.home_goals, match.away_goals)
            histories[match.away_team].add(match.away_goals, match.home_goals)

    return TrainingBuildResult(
        tuple(rows), tuple(rejected), input_matches, exact_kickoff_matches, date_only_matches, date_only_policy
    )


def _normalize_match(source: Mapping[str, object], aliases: TeamAliases, fallback_id: str) -> _Match:
    provider_match_id = str(source.get("provider_match_id", fallback_id)).strip() or fallback_id
    competition = str(source["competition"]).strip()
    season = str(source.get("season", "")).strip()
    if not competition:
        raise ValueError("competition_missing")
    timestamp = match_timestamp(source)
    kickoff_utc = datetime.fromtimestamp(timestamp, timezone.utc)
    home_team = aliases.canonical(str(source["home_team"]))
    away_team = aliases.canonical(str(source["away_team"]))
    home_goals, away_goals = int(source["home_goals"]), int(source["away_goals"])
    if home_goals < 0 or away_goals < 0:
        raise ValueError("negative_score")
    return _Match(source, provider_match_id, competition, season, kickoff_utc, home_team, away_team, home_goals, away_goals)


def _history_cutoff(match: _Match, date_only_policy: str) -> datetime:
    if date_only_policy == "freeze_utc_day":
        return match.kickoff_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return match.kickoff_utc


def _training_row(
    match: _Match, home_elo: Any, away_elo: Any, histories: Mapping[str, _TeamHistory], date_only_policy: str
) -> dict[str, object]:
    home_history = histories[match.home_team].snapshot()
    away_history = histories[match.away_team].snapshot()
    return {
        "provider_match_id": match.provider_match_id,
        "competition": match.competition,
        "season": match.season,
        "kickoff_utc": match.kickoff_utc.isoformat().replace("+00:00", "Z"),
        "time_precision": str(match.source.get("kickoff_precision", "exact")),
        "history_cutoff_utc": _history_cutoff(match, date_only_policy).isoformat().replace("+00:00", "Z"),
        "home_team": match.home_team,
        "away_team": match.away_team,
        # Pre-match, auditable features.
        "home_elo": home_elo.rating,
        "away_elo": away_elo.rating,
        "home_elo_snapshot_date": home_elo.snapshot_date.isoformat(),
        "away_elo_snapshot_date": away_elo.snapshot_date.isoformat(),
        "home_association": home_elo.association,
        "away_association": away_elo.association,
        "home_history": home_history,
        "away_history": away_history,
        # Labels must never be copied into a feature list by a trainer.
        "label_home_goals": match.home_goals,
        "label_away_goals": match.away_goals,
        "label_result_1x2": "home" if match.home_goals > match.away_goals else "draw" if match.home_goals == match.away_goals else "away",
    }


def _input_reason(exc: Exception) -> str:
    text = str(exc).strip()
    if text in {"competition_missing", "negative_score"}:
        return text
    if "timestamp" in text or "kickoff" in text or "date" in text:
        return "kickoff_invalid"
    if "blank" in text:
        return "team_invalid"
    return "input_invalid"
