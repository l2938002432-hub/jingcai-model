"""Capture a single auditable official on-sale snapshot for prospective validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from jingcai.data_contract import DEFAULT_SCHEMA_VERSION, summarize_quality, with_provenance
from jingcai.official_archive import ImmutablePayloadArchive
from jingcai.providers.sporttery import normalize_payload


OFFICIAL_ON_SALE_SOURCE = "sporttery-public-calculator"


def _contract_fixtures(
    fixtures: list[Mapping[str, Any]], *, observed_at: datetime, raw_hash: str
) -> list[dict[str, Any]]:
    """Attach record-level lineage to normalized official on-sale fixtures.

    The calculator endpoint publishes a whole pool in one payload, so every
    fixture intentionally references the same immutable archived payload hash.
    ``observed_at`` is also the first time this collector can prove the data
    was available; it is not backfilled from a kickoff or sale-cutoff estimate.
    """
    return [
        with_provenance(
            fixture,
            source=OFFICIAL_ON_SALE_SOURCE,
            source_record_id=str(fixture["match_id"]),
            captured_at=observed_at,
            available_at=observed_at,
            raw_hash=raw_hash,
            schema_version=DEFAULT_SCHEMA_VERSION,
        )
        for fixture in fixtures
    ]


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
    fixtures = _contract_fixtures(
        normalize_payload(payload, fetched_at=observed_at),
        observed_at=observed_at,
        raw_hash=receipt.payload_sha256,
    )
    quality = summarize_quality(fixtures).as_dict()
    date = observed_at.astimezone(UTC).date().isoformat()
    filename = observed_at.astimezone(UTC).strftime("%H%M%S") + f"-{receipt.payload_sha256[:12]}.json"
    output = root_path / "normalized" / date / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    observed = observed_at.astimezone(UTC).isoformat()
    output.write_text(json.dumps({
        "observed_at": observed,
        "raw_receipt": receipt.relative_path,
        "fixtures": fixtures,
        # This is deliberately top-level metadata, so legacy readers that
        # consume only ``fixtures`` remain compatible while reports and health
        # checks can read one deterministic quality object.
        "data_quality": {
            "source": OFFICIAL_ON_SALE_SOURCE,
            "captured_at": observed,
            "raw_hash": receipt.payload_sha256,
            "schema_version": DEFAULT_SCHEMA_VERSION,
            "provenance": quality,
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "observed_at": observed,
        "fixtures": len(fixtures),
        "path": str(output),
        "data_quality": quality,
    }
