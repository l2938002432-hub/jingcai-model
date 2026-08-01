"""Auditable, leakage-safe evaluation for cross-league 1X2 forecasts.

This module deliberately consumes *frozen prediction records*, rather than a
model or odds feed.  It therefore cannot quietly invent a market comparison or
an ROI claim.  A record needs a pre-kickoff prediction timestamp and the final
outcome; equal kickoff timestamps are reported as one atomic evaluation batch.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

from .backtest import ForecastObservation, brier_score, log_loss
from .models.poisson import match_timestamp


OUTCOMES = ("home", "draw", "away")


@dataclass(frozen=True)
class ProbabilityMetrics:
    sample_count: int
    log_loss: float
    brier: float
    top_label_ece: float
    kickoff_batches: int


@dataclass(frozen=True)
class CrossLeagueEvaluationReport:
    """A serialisable report which is intentionally not a betting approval."""

    schema_version: int
    market: str
    overall: ProbabilityMetrics
    by_competition: Mapping[str, ProbabilityMetrics]
    by_data_coverage: Mapping[str, ProbabilityMetrics]
    input_manifest_sha256: str | None
    market_comparison: Mapping[str, str]
    confidence_note: str
    admission_status: str = "RESEARCH_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "market": self.market,
            "overall": asdict(self.overall),
            "by_competition": {key: asdict(value) for key, value in self.by_competition.items()},
            "by_data_coverage": {key: asdict(value) for key, value in self.by_data_coverage.items()},
            "input_manifest_sha256": self.input_manifest_sha256,
            "market_comparison": dict(self.market_comparison),
            "confidence_note": self.confidence_note,
            "admission_status": self.admission_status,
        }


def _timestamp(record: Mapping[str, Any], *names: str) -> float:
    for name in names:
        if name in record:
            return match_timestamp({"timestamp": record[name]})
    raise ValueError(f"prediction record missing one of: {', '.join(names)}")


def _coverage_band(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "complete" if value else "incomplete"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not isfinite(float(value)) or not 0 <= float(value) <= 1:
            raise ValueError("data_coverage must be between 0 and 1")
        return "complete" if value >= 0.9 else "partial" if value >= 0.5 else "sparse"
    text = str(value).strip().lower()
    return text or "unknown"


def _observation(record: Mapping[str, Any]) -> ForecastObservation:
    probabilities = record.get("probabilities")
    if not isinstance(probabilities, Mapping) or set(probabilities) != set(OUTCOMES):
        raise ValueError("probabilities must contain exactly home, draw and away")
    numeric = {outcome: float(probabilities[outcome]) for outcome in OUTCOMES}
    actual = str(record.get("actual", ""))
    if actual not in OUTCOMES:
        raise ValueError("actual must be home, draw or away")
    # ForecastObservation validation is executed by the score functions below.
    return ForecastObservation(numeric, actual)


def _top_label_ece(observations: list[ForecastObservation], *, bins: int) -> float:
    """Top-label ECE, not a full calibration curve.

    Each row contributes its highest predicted probability and whether that
    predicted class occurred.  The binning definition is retained here so that
    future reports remain comparable.
    """
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for row in observations:
        predicted, confidence = max(row.probabilities.items(), key=lambda item: item[1])
        index = min(bins - 1, int(confidence * bins))
        buckets[index].append((confidence, 1.0 if row.actual == predicted else 0.0))
    total = len(observations)
    return sum(
        (len(bucket) / total)
        * abs(sum(confidence for confidence, _ in bucket) / len(bucket) - sum(correct for _, correct in bucket) / len(bucket))
        for bucket in buckets if bucket
    )


def _metrics(rows: list[tuple[float, ForecastObservation]], *, bins: int) -> ProbabilityMetrics:
    observations = [observation for _, observation in rows]
    if not observations:
        raise ValueError("at least one prediction record is required")
    return ProbabilityMetrics(
        sample_count=len(observations),
        log_loss=log_loss(observations),
        brier=brier_score(observations),
        top_label_ece=_top_label_ece(observations, bins=bins),
        kickoff_batches=len({kickoff for kickoff, _ in rows}),
    )


def _confidence_note(overall: ProbabilityMetrics, competitions: int) -> str:
    if overall.sample_count < 200:
        level = "低"
    elif overall.sample_count < 1_000 or competitions < 3:
        level = "有限"
    else:
        level = "中等（仍须使用未来样本复核）"
    return (
        f"证据置信度：{level}；基于 {overall.sample_count} 场、{overall.kickoff_batches} 个独立开球批次、"
        f"{competitions} 个赛事分层。指标是赛果概率质量，不代表盈利或可进入候选。"
    )


def evaluate_cross_league_1x2(
    records: Iterable[Mapping[str, Any]], *, input_manifest_sha256: str | None = None, ece_bins: int = 10,
) -> CrossLeagueEvaluationReport:
    """Score frozen pre-match 1X2 forecasts across competitions.

    Required fields: ``kickoff_utc`` (or another supported kickoff name),
    ``predicted_at``/``forecast_at``, ``probabilities`` and ``actual``.  An
    optional ``competition_code`` and ``data_coverage`` provide auditable
    strata.  ``predicted_at`` must not be after kickoff.

    Future market comparison must be attached as a separate, trusted,
    time-valid de-vig snapshot dataset keyed by prediction id.  It must report
    its own coverage before calculating model-vs-market deltas; this function
    deliberately does not read arbitrary odds fields from prediction records.
    """
    if ece_bins < 2:
        raise ValueError("ece_bins must be at least 2")
    if input_manifest_sha256 is not None and (len(input_manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in input_manifest_sha256.lower())):
        raise ValueError("input_manifest_sha256 must be a SHA-256 hex digest")

    materialised: list[tuple[float, str, str, ForecastObservation]] = []
    for record in records:
        kickoff = _timestamp(record, "kickoff_utc", "kickoff", "date", "timestamp")
        predicted_at = _timestamp(record, "predicted_at", "forecast_at", "prediction_time")
        if predicted_at > kickoff:
            raise ValueError("prediction record was created after kickoff")
        materialised.append((
            kickoff,
            str(record.get("competition_code") or "UNKNOWN"),
            _coverage_band(record.get("data_coverage")),
            _observation(record),
        ))
    if not materialised:
        raise ValueError("at least one prediction record is required")

    overall_rows = [(kickoff, observation) for kickoff, _, _, observation in materialised]
    competitions: dict[str, list[tuple[float, ForecastObservation]]] = defaultdict(list)
    coverages: dict[str, list[tuple[float, ForecastObservation]]] = defaultdict(list)
    for kickoff, competition, coverage, observation in materialised:
        competitions[competition].append((kickoff, observation))
        coverages[coverage].append((kickoff, observation))
    overall = _metrics(overall_rows, bins=ece_bins)
    return CrossLeagueEvaluationReport(
        schema_version=1,
        market="match_result",
        overall=overall,
        by_competition={key: _metrics(value, bins=ece_bins) for key, value in sorted(competitions.items())},
        by_data_coverage={key: _metrics(value, bins=ece_bins) for key, value in sorted(coverages.items())},
        input_manifest_sha256=input_manifest_sha256,
        market_comparison={
            "status": "UNAVAILABLE",
            "reason": "未提供独立、可验证且赛前有效的去水市场概率快照；不得推断赔率、市场优势或ROI。",
            "future_interface": "join trusted de-vig 1X2 snapshots by prediction_id and report matched coverage before deltas",
        },
        confidence_note=_confidence_note(overall, len(competitions)),
    )
