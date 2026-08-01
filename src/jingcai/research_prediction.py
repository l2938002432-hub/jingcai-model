"""Cross-league research-only probabilities derived from dated club Elo snapshots."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping

from .markets import result_1x2
from .models.poisson import normalize, poisson_probabilities
from .providers.club_elo_history import ClubEloHistory, ClubEloHistoryError


def research_1x2(fixture: Mapping[str, Any], ratings: ClubEloHistory) -> dict[str, float] | None:
    """Return a transparent research probability, never a recommendation signal.

    The Elo record is joined strictly before kickoff. Missing either team returns
    ``None`` rather than inventing a rating.
    """
    kickoff = fixture.get("scheduled_start") or fixture.get("kickoff")
    if not kickoff:
        return None
    try:
        home = ratings.rating_before(str(fixture["home_team"]), str(kickoff))
        away = ratings.rating_before(str(fixture["away_team"]), str(kickoff))
    except (KeyError, ClubEloHistoryError):
        return None
    strength = math.exp(max(-1.5, min(1.5, (home + 65.0 - away) / 400.0)))
    home_rate, away_rate = 1.35 * math.sqrt(strength), 1.10 / math.sqrt(strength)
    hp, ap = poisson_probabilities(home_rate, 8), poisson_probabilities(away_rate, 8)
    matrix = normalize([[h * a for a in ap] for h in hp])
    return result_1x2({(h, a): value for h, row in enumerate(matrix) for a, value in enumerate(row)})
