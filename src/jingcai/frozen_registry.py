"""Append-only, one-decision registry for prospective PAPER_ONLY candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from jingcai.prospective_roi import freeze_candidates
from jingcai.storage import AppendOnlyJsonlStore


def _candidate_key(candidate: Mapping[str, Any]) -> str:
    material = {
        "match_id": str(candidate["match_id"]),
        "market": str(candidate["market"]),
        "sale_cutoff": str(candidate["sale_cutoff"]),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def freeze_new_candidates(
    path: str | Path, candidates: Iterable[Mapping[str, Any]], *, frozen_at: datetime
) -> list[dict[str, Any]]:
    """Freeze at most one selection per match-market-cutoff, forever.

    A later hourly run cannot replace or add a second prediction for the same
    market.  This avoids multiple-counting one match in prospective ROI.
    """
    store = AppendOnlyJsonlStore(path)
    existing = {str(record.get("candidate_key")) for record in store.read_verified()}
    unseen = [dict(candidate) for candidate in candidates if _candidate_key(candidate) not in existing]
    frozen = freeze_candidates(unseen, frozen_at=frozen_at)
    for record in frozen:
        key = _candidate_key(record)
        record["candidate_key"] = key
        store.append_once(key, record)
    return frozen
