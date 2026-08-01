from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from itertools import groupby

from jingcai.market_validation import validate_markets
from jingcai.models import DixonColesModel, HalfFullModel
from jingcai.models.poisson import match_timestamp
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
    training_rows: list[dict[str, object]] = []
    baseline_history: list[dict[str, object]] | None = None
    for kickoff, batch_iter in groupby(rows, key=match_timestamp):
        batch = list(batch_iter)
        # The lockbox boundary may fall inside a simultaneous kick-off batch.
        # Skip that whole batch rather than allowing one final score to train a
        # forecast for another match that started at the same instant.
        if len(training_rows) < split:
            training_rows.extend(batch)
            continue
        if baseline_history is None:
            baseline_history = list(training_rows)
        model = DixonColesModel().fit(
            training_rows,
            as_of=kickoff,
        )
        for test in batch:
            forecast = dict(test)
            forecast["score_matrix"] = _matrix(
                model, str(test["home_team"]), str(test["away_team"])
            )
            if test.get("half_home_goals") is not None and test.get("half_away_goals") is not None:
                forecast["half_full_probabilities"] = HalfFullModel(model).predict_proba(
                    str(test["home_team"]), str(test["away_team"])
                )
            forecasts.append(forecast)
        training_rows.extend(batch)
    results = validate_markets(forecasts, baseline_history=baseline_history or training_rows)
    print(json.dumps({name: asdict(value) for name, value in results.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
