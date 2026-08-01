"""Explainable, fail-closed status for every official on-sale fixture."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping


STATUS_CANDIDATE = "candidate_eligible"
STATUS_RESEARCH = "research_observation"
STATUS_INSUFFICIENT = "data_insufficient"
STATUS_REJECTED = "safety_rejected"


def assess_fixtures(
    fixtures: Iterable[Mapping[str, Any]], *, history_teams: Iterable[str],
    acceptance: Mapping[str, Any], now: datetime, data_fresh: bool,
    research_predictor: Callable[[Mapping[str, Any]], Mapping[str, float] | None] | None = None,
) -> list[dict[str, Any]]:
    """Keep every fixture while making recommendation eligibility explicit."""
    trained = {str(team) for team in history_teams}
    assessed: list[dict[str, Any]] = []
    for source in fixtures:
        row = dict(source)
        code = str(row.get("competition_code", ""))
        policy = acceptance.get(code, {})
        policy = policy if isinstance(policy, Mapping) else {}
        approved = policy.get("approved") is True
        markets = policy.get("markets", {})
        approved_markets = [str(key) for key, value in markets.items() if value is True] if isinstance(markets, Mapping) else []
        reason = ""
        if not data_fresh:
            status, reason = STATUS_REJECTED, "官方赔率数据过期"
        else:
            try:
                cutoff = datetime.fromisoformat(str(row["sale_cutoff"]))
                if cutoff.tzinfo is None or cutoff <= now:
                    status, reason = STATUS_REJECTED, "已过停售时间或停售时间无效"
                elif str(row.get("home_team")) not in trained or str(row.get("away_team")) not in trained:
                    research = research_predictor(row) if research_predictor else None
                    if research is None:
                        status, reason = STATUS_INSUFFICIENT, "缺少可追溯的球队历史"
                    else:
                        status, reason = STATUS_RESEARCH, "使用跨联赛 Elo 生成研究概率，赛事尚未独立验收"
                        row["research_probability"] = dict(research)
                elif approved:
                    status, reason = STATUS_CANDIDATE, "赛事玩法已通过独立概率验收"
                else:
                    status, reason = STATUS_RESEARCH, "可计算研究概率，赛事尚未独立验收"
            except (KeyError, TypeError, ValueError):
                status, reason = STATUS_REJECTED, "停售时间字段无效"
        row.update({
            "analysis_status": status,
            "analysis_reason": reason,
            "model_approved": approved,
            "approved_markets": approved_markets,
            "recommendation_eligible": status == STATUS_CANDIDATE,
        })
        assessed.append(row)
    return assessed


def coverage_summary(fixtures: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("analysis_status", STATUS_INSUFFICIENT)) for row in fixtures)
    return {
        "official_on_sale": sum(counts.values()),
        "candidate_eligible": counts[STATUS_CANDIDATE],
        "research_observation": counts[STATUS_RESEARCH],
        "data_insufficient": counts[STATUS_INSUFFICIENT],
        "safety_rejected": counts[STATUS_REJECTED],
    }
