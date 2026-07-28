"""Capture a single auditable official on-sale snapshot for prospective validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from jingcai.official_archive import ImmutablePayloadArchive
from jingcai.providers.sporttery import normalize_payload


def capture_snapshot(
    root: str | Path,
    *,
    payload: Mapping[str, Any],
    observed_at: datetime,
) -> dict[str, object]:
    """Archive one canonical source snapshot and its normalized fixtures.

    This is a data-collection primitive only: it emits no recommendations and
    never overwrites a previous observation.
    """
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    root_path = Path(root)
    receipt = ImmutablePayloadArchive(root_path / "raw").append(
        "on_sale", request_params={"pool_code": "five_markets"},
        retrieved_at=observed_at, payload=payload,
    )
    fixtures = normalize_payload(payload, fetched_at=observed_at)
    date = observed_at.astimezone(UTC).date().isoformat()
    filename = observed_at.astimezone(UTC).strftime("%H%M%S") + f"-{receipt.payload_sha256[:12]}.json"
    output = root_path / "normalized" / date / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "raw_receipt": receipt.relative_path, "fixtures": fixtures,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"observed_at": observed_at.astimezone(UTC).isoformat(), "fixtures": len(fixtures), "path": str(output)}
