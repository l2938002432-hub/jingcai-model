"""Freeze paper candidates and settle them only against later official results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from jingcai.backtest import BetObservation, fixed_unit_returns
from jingcai.domain import Market, MatchResult, ResultStatus, Selection, SettlementStatus
from jingcai.settlement import settle_selection


def freeze_candidates(candidates: Iterable[Mapping[str, Any]], *, frozen_at: datetime) -> list[dict[str, Any]]:
    """Create immutable paper selections before their estimated sale cutoff."""
    if frozen_at.tzinfo is None:
        raise ValueError("frozen_at must be timezone-aware")
    frozen: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for candidate in candidates:
        match_id, market = str(candidate["match_id"]), str(candidate["market"])
        identity = (match_id, market)
        if identity in identities:
            raise ValueError("at most one frozen candidate per match and market")
        identities.add(identity)
        odds_as_of = datetime.fromisoformat(str(candidate["odds_as_of"]).replace("Z", "+00:00"))
        sale_cutoff = datetime.fromisoformat(str(candidate["sale_cutoff"]).replace("Z", "+00:00"))
        if odds_as_of.tzinfo is None or sale_cutoff.tzinfo is None:
            raise ValueError("candidate time zone is required")
        if odds_as_of > frozen_at or frozen_at > sale_cutoff:
            raise ValueError("candidate cannot be frozen outside its visible sale window")
        record = {
            "match_id": match_id, "market": market, "outcome": str(candidate["outcome"]),
            "decimal_odds": float(candidate["decimal_odds"]), "probability": float(candidate["probability"]),
            "odds_as_of": odds_as_of.isoformat(), "sale_cutoff": sale_cutoff.isoformat(),
            "frozen_at": frozen_at.isoformat(), "handicap": candidate.get("handicap"),
            "model_state": "PAPER_ONLY",
        }
        if record["decimal_odds"] <= 1 or not 0 <= record["probability"] <= 1:
            raise ValueError("candidate odds or probability is invalid")
        record["frozen_prediction_id"] = hashlib.sha256(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        frozen.append(record)
    return frozen


def settle_frozen_candidates(
    frozen: Iterable[Mapping[str, Any]], samples: Iterable[Mapping[str, Any]], *, stake: float = 2.0
) -> list[dict[str, Any]]:
    """Return settled or pending paper selections; result ambiguity never pays out."""
    if stake <= 0:
        raise ValueError("stake must be positive")
    by_match = {str(sample.get("match_id")): sample for sample in samples}
    settled: list[dict[str, Any]] = []
    for item in frozen:
        record = dict(item)
        sample = by_match.get(str(item["match_id"]))
        if not sample or sample.get("result_status") != "finished":
            record.update({"settlement_status": "pending", "payout": 0.0, "profit": 0.0})
            settled.append(record)
            continue
        result = MatchResult(
            str(item["match_id"]), ResultStatus.FINISHED,
            int(sample["home_score"]), int(sample["away_score"]),
            None if sample.get("half_home_score") is None else int(sample["half_home_score"]),
            None if sample.get("half_away_score") is None else int(sample["half_away_score"]),
        )
        selection = Selection(
            str(item["frozen_prediction_id"]), str(item["match_id"]), Market(str(item["market"])),
            str(item["outcome"]), float(item["decimal_odds"]),
            None if item.get("handicap") is None else int(item["handicap"]),
        )
        status = settle_selection(selection, result)
        if status is SettlementStatus.PENDING:
            record.update({"settlement_status": "pending", "payout": 0.0, "profit": 0.0})
        elif status is SettlementStatus.VOID:
            record.update({"settlement_status": "void", "payout": stake, "profit": 0.0})
        elif status is SettlementStatus.WON:
            payout = round(stake * float(item["decimal_odds"]), 2)
            record.update({"settlement_status": "won", "payout": payout, "profit": round(payout - stake, 2)})
        else:
            record.update({"settlement_status": "lost", "payout": 0.0, "profit": -stake})
        settled.append(record)
    return settled


def prospective_return_summary(rows: Iterable[Mapping[str, Any]], *, stake: float = 2.0) -> dict[str, float | int]:
    """Summarize only final won/lost rows; pending and void rows are excluded."""
    completed = [row for row in rows if row.get("settlement_status") in {"won", "lost"}]
    if not completed:
        return {"bets": 0, "wins": 0, "stake": 0.0, "payout": 0.0, "profit": 0.0, "roi": 0.0, "max_drawdown": 0.0}
    returns = fixed_unit_returns(
        [BetObservation(row["settlement_status"] == "won", float(row["decimal_odds"]), True) for row in completed],
        unit_stake=stake,
    )
    return returns.__dict__
