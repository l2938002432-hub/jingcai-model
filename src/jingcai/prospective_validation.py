"""Link frozen pre-match snapshots to later official result revisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any


def load_captured_fixtures(root: str | Path) -> list[dict[str, Any]]:
    """Read normalized prospective snapshots in deterministic path order."""
    records: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob("normalized/**/*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        observed_at = payload.get("observed_at") if isinstance(payload, Mapping) else None
        fixtures = payload.get("fixtures") if isinstance(payload, Mapping) else None
        if not isinstance(observed_at, str) or not isinstance(fixtures, list):
            raise ValueError(f"invalid prospective snapshot: {path}")
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError(f"snapshot observed_at has no timezone: {path}")
        for fixture in fixtures:
            if not isinstance(fixture, Mapping):
                raise ValueError(f"snapshot fixture is not an object: {path}")
            kickoff = datetime.fromisoformat(str(fixture["kickoff"]).replace("Z", "+00:00"))
            if kickoff.tzinfo is None or observed > kickoff:
                raise ValueError(f"snapshot violates pre-match time chain: {path}")
            record = dict(fixture) | {"observed_at": observed_at, "snapshot_path": str(path)}
            material = f"{path.as_posix()}:{fixture.get('match_id')}:{observed_at}".encode("utf-8")
            record["prospective_sample_id"] = hashlib.sha256(material).hexdigest()
            records.append(record)
    return records


def attach_official_results(
    fixtures: Iterable[Mapping[str, Any]], results: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Attach only one finished official result per match; conflicts stay pending."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get("match_id", "")), []).append(result)
    samples: list[dict[str, Any]] = []
    for fixture in fixtures:
        copied = dict(fixture)
        candidates = [row for row in grouped.get(str(fixture.get("match_id", "")), []) if row.get("status") == "finished"]
        fingerprints = {
            (row.get("home_score"), row.get("away_score"), row.get("half_home_score"), row.get("half_away_score"))
            for row in candidates
        }
        if len(fingerprints) == 1:
            result = candidates[-1]
            copied["result_status"] = "finished"
            copied["home_score"] = result.get("home_score")
            copied["away_score"] = result.get("away_score")
            copied["half_home_score"] = result.get("half_home_score")
            copied["half_away_score"] = result.get("half_away_score")
            copied["result_revision"] = result.get("revision")
        else:
            copied["result_status"] = "pending" if not candidates else "conflict"
        samples.append(copied)
    return samples
