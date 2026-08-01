"""Cross-league research-only probabilities derived from dated club Elo snapshots.

This module deliberately does not contain selection, expected-value, staking,
or candidate-admission code.  Its output is a reproducible research baseline,
not evidence of a profitable betting strategy.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Mapping

from .markets import result_1x2
from .models.poisson import normalize, poisson_probabilities
from .providers.club_elo_history import ClubEloHistory, ClubEloHistoryError


class ResearchEloBaseline:
    """Point-in-time Elo-to-Poisson baseline for cross-league research only.

    Parameters are intentionally fixed and serializable.  They may only be
    changed by a separately audited experiment; this class does not fit itself
    on fixture outcomes, which avoids accidental look-ahead during prediction.
    """

    MODEL_ID = "research_elo_poisson_v1"

    def __init__(
        self,
        *,
        home_advantage: float = 65.0,
        base_home_goals: float = 1.35,
        base_away_goals: float = 1.10,
        elo_scale: float = 400.0,
        max_goals: int = 8,
    ) -> None:
        values = (home_advantage, base_home_goals, base_away_goals, elo_scale)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("research Elo parameters must be finite")
        if base_home_goals <= 0 or base_away_goals <= 0 or elo_scale <= 0:
            raise ValueError("goal rates and elo_scale must be positive")
        if max_goals < 1:
            raise ValueError("max_goals must be at least 1")
        self.home_advantage = float(home_advantage)
        self.base_home_goals = float(base_home_goals)
        self.base_away_goals = float(base_away_goals)
        self.elo_scale = float(elo_scale)
        self.max_goals = int(max_goals)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable, versioned model parameters."""
        return {
            "model_id": self.MODEL_ID,
            "home_advantage": self.home_advantage,
            "base_home_goals": self.base_home_goals,
            "base_away_goals": self.base_away_goals,
            "elo_scale": self.elo_scale,
            "max_goals": self.max_goals,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ResearchEloBaseline":
        if value.get("model_id") != cls.MODEL_ID:
            raise ValueError("unsupported research Elo model_id")
        try:
            return cls(
                home_advantage=float(value["home_advantage"]),
                base_home_goals=float(value["base_home_goals"]),
                base_away_goals=float(value["base_away_goals"]),
                elo_scale=float(value["elo_scale"]),
                max_goals=int(value["max_goals"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid research Elo parameters") from exc

    @staticmethod
    def _instant(value: object, label: str) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(float(value), UTC)
        else:
            try:
                parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid {label}: {value!r}") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"{label} must include a timezone")
        return parsed.astimezone(UTC)

    def predict(
        self,
        fixture: Mapping[str, Any],
        ratings: ClubEloHistory,
        *,
        as_of: object,
    ) -> dict[str, object] | None:
        """Return a reproducible score distribution visible at ``as_of``.

        Both the model cutoff and source joins are point-in-time: ClubElo
        snapshots must be dated strictly before ``as_of``.  Prediction fails
        closed for missing teams or when ``as_of`` is after kickoff.
        """
        kickoff_value = fixture.get("scheduled_start") or fixture.get("kickoff")
        if not kickoff_value:
            return None
        cutoff = self._instant(as_of, "as_of")
        kickoff = self._instant(kickoff_value, "kickoff")
        if cutoff > kickoff:
            raise ValueError("as_of cannot be after kickoff")
        try:
            home_date, home_elo, home_country = ratings.snapshot_before(str(fixture["home_team"]), cutoff)
            away_date, away_elo, away_country = ratings.snapshot_before(str(fixture["away_team"]), cutoff)
        except (KeyError, ClubEloHistoryError):
            return None
        exponent = max(-1.5, min(1.5, (home_elo + self.home_advantage - away_elo) / self.elo_scale))
        strength = math.exp(exponent)
        home_rate = self.base_home_goals * math.sqrt(strength)
        away_rate = self.base_away_goals / math.sqrt(strength)
        home_probabilities = poisson_probabilities(home_rate, self.max_goals)
        away_probabilities = poisson_probabilities(away_rate, self.max_goals)
        matrix = normalize([[home * away for away in away_probabilities] for home in home_probabilities])
        flattened = {(home, away): probability for home, row in enumerate(matrix) for away, probability in enumerate(row)}
        return {
            "model_id": self.MODEL_ID,
            "research_only": True,
            "as_of": cutoff.isoformat(),
            "kickoff": kickoff.isoformat(),
            "parameters": self.to_dict(),
            "input_snapshots": {
                "home": {"date": home_date.isoformat(), "elo": home_elo, "country": home_country},
                "away": {"date": away_date.isoformat(), "elo": away_elo, "country": away_country},
            },
            "expected_goals": {"home": home_rate, "away": away_rate},
            "score_matrix": matrix,
            "result_1x2": result_1x2(flattened),
        }


def research_1x2(fixture: Mapping[str, Any], ratings: ClubEloHistory) -> dict[str, float] | None:
    """Return a transparent research probability, never a recommendation signal.

    The Elo record is joined strictly before kickoff. Missing either team returns
    ``None`` rather than inventing a rating.
    """
    kickoff = fixture.get("scheduled_start") or fixture.get("kickoff")
    if not kickoff:
        return None
    prediction = ResearchEloBaseline().predict(fixture, ratings, as_of=kickoff)
    return None if prediction is None else prediction["result_1x2"]  # type: ignore[return-value]
