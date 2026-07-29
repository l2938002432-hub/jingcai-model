"""Settle frozen prospective candidates only against official result revisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from jingcai.prospective_roi import prospective_return_summary, settle_frozen_candidates
from jingcai.prospective_validation import attach_official_results


def settle_registry(
    frozen: Iterable[Mapping[str, Any]], official_results: Iterable[Mapping[str, Any]], *, stake: float = 2.0
) -> dict[str, Any]:
    """Return an auditable settlement report; unresolved results stay pending."""
    frozen_rows = [dict(row) for row in frozen]
    samples = attach_official_results(frozen_rows, official_results)
    settlements = settle_frozen_candidates(frozen_rows, samples, stake=stake)
    return {
        "model_state": "PAPER_ONLY",
        "method": "one frozen pre-cutoff selection per match-market; official-result settlement",
        "frozen": len(frozen_rows),
        "settlements": settlements,
        "summary": prospective_return_summary(settlements, stake=stake),
        "pending": sum(row["settlement_status"] == "pending" for row in settlements),
        "conflicts": sum(sample["result_status"] == "conflict" for sample in samples),
    }
