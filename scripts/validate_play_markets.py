from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from jingcai.market_validation import validate_markets
from jingcai.models import DixonColesModel
from jingcai.models.poisson import field
from jingcai.providers.club_history import load_club_history_csv


def _matrix(model: DixonColesModel, home: str, away: str, max_goals: int = 10) -> dict[tuple[int, int], float]:
    raw = model.predict_score_matrix(home, away, max_goals)
    return {(home_goals, away_goals): probability for home_goals, line in enumerate(raw) for away_goals, probability in enumerate(line)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate each play market on a chronological lockbox")
    parser.add_argument("history_csv")
    parser.add_argument("division")
    parser.add_argument("--lockbox", type=int, default=250)
    args = parser.parse_args()

    rows = sorted(
        load_club_history_csv(args.history_csv, divisions={args.division}),
        key=lambda row: str(row["kickoff_utc"]),
    )
    if len(rows) <= args.lockbox:
        raise RuntimeError("not enough history for requested lockbox")
    split = len(rows) - args.lockbox
    forecasts: list[dict[str, object]] = []
    for index in range(split, len(rows)):
        test = rows[index]
        model = DixonColesModel().fit(
            rows[:index],
            as_of=field(test, "kickoff_utc", "kickoff_date", "date"),
        )
        forecast = dict(test)
        forecast["score_matrix"] = _matrix(
            model, str(test["home_team"]), str(test["away_team"])
        )
        forecasts.append(forecast)
    results = validate_markets(forecasts, baseline_history=rows[:split])
    print(json.dumps({name: asdict(value) for name, value in results.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
