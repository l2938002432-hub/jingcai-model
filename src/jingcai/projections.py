from __future__ import annotations

from typing import Any, Iterable, Mapping


FIXTURE_FIELDS = (
    "match_id",
    "match_number",
    "match_num",
    "competition",
    "competition_code",
    "home_team",
    "away_team",
    "display_home_team",
    "display_away_team",
    "scheduled_start",
    "kickoff",
    "sale_cutoff",
    "sale_cutoff_estimated",
    "odds_as_of",
    "handicap",
    "odds",
    "model_approved",
    "approved_markets",
    "recommendation_eligible",
)

CANDIDATE_FIELDS = (
    "match_id",
    "match_number",
    "competition",
    "competition_code",
    "home_team",
    "away_team",
    "scheduled_start",
    "market",
    "outcome",
    "market_label",
    "outcome_label",
    "probability",
    "market_probability",
    "decimal_odds",
    "conservative_ev",
    "sale_cutoff",
    "sale_cutoff_estimated",
    "odds_as_of",
    "recommendation_status",
    "risk_status",
)

SETTLEMENT_FIELDS = (
    "report_date",
    "stake",
    "payout",
    "profit",
    "roi",
    "current_bankroll",
    "current_drawdown",
    "max_drawdown",
    "pending_stake",
)


def _pick(source: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: source[field] for field in fields if field in source}


def public_release_projection(
    release: Mapping[str, Any],
    *,
    fixtures: Iterable[Mapping[str, Any]] = (),
    candidates: Iterable[Mapping[str, Any]] = (),
    model_settlement: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the only DTO allowed to reach Pages or notification channels.

    This function deliberately enumerates allowed fields. Unknown values, including
    personal stakes, notes and purchase details, are dropped rather than copied.
    """
    projected = {
        "schema_version": 1,
        "release_id": str(release["release_id"]),
        "release_hash": str(release["release_hash"]),
        "report_date": str(release["report_date"]),
        "generated_at": str(release["generated_at"]),
        "source_as_of": str(release["source_as_of"]),
        "model_state": str(release["model_state"]),
        "fixtures": [_pick(item, FIXTURE_FIELDS) for item in fixtures],
        "candidates": [_pick(item, CANDIDATE_FIELDS) for item in candidates],
    }
    if model_settlement is not None:
        projected["model_settlement"] = _pick(model_settlement, SETTLEMENT_FIELDS)
    return projected
