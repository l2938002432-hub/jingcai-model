"""Archive a small official-history batch and produce replayable normalized data.

Use a narrow date range first. This program is deliberately rate-limited and
does not send notifications, build pages, or create recommendations.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from jingcai.official_archive import ImmutablePayloadArchive
from jingcai.providers.sporttery import (
    fetch_fixed_bonus_history,
    fetch_uniform_results,
    normalize_fixed_bonus_history,
    normalize_uniform_results,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def archive_batch(
    *,
    results_payload: Mapping[str, Any],
    bonus_payloads: Mapping[str, Mapping[str, Any]],
    root: Path,
    ingested_at: datetime,
    include_bonuses: bool = True,
) -> dict[str, object]:
    """Pure orchestration for live calls and offline fixtures alike."""
    archive = ImmutablePayloadArchive(root / "raw")
    archive.append("results", request_params={}, retrieved_at=ingested_at, payload=results_payload)
    results = normalize_uniform_results(results_payload, ingested_at=ingested_at)
    points: list[dict[str, Any]] = []
    for result in results:
        match_id = str(result["match_id"])
        if not include_bonuses:
            continue
        payload = bonus_payloads.get(match_id)
        if payload is None:
            continue
        archive.append("fixed_bonus", request_params={"match_id": match_id}, retrieved_at=ingested_at, payload=payload)
        points.extend(normalize_fixed_bonus_history(payload, match_id=match_id, ingested_at=ingested_at))
    _write_json(root / "normalized-results.json", results)
    _write_json(root / "normalized-bonus-points.json", points)
    return {"results": len(results), "bonus_points": len(points), "root": str(root)}


def main() -> int:
    parser = argparse.ArgumentParser(description="低频归档官方竞彩历史数据")
    parser.add_argument("--begin", help="开始日期 YYYY-MM-DD；联网模式必填")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD；联网模式必填")
    parser.add_argument("--output-dir", type=Path, default=Path("data/official-history"))
    parser.add_argument("--offline-results", type=Path, help="离线官方赛果 JSON")
    parser.add_argument("--offline-bonus-dir", type=Path, help="离线奖金 JSON 目录，文件名为 matchId.json")
    parser.add_argument("--max-matches", type=int, default=5, help="联网模式单次最多抓取比赛数，1..20")
    parser.add_argument("--sleep-seconds", type=float, default=0.5, help="每场奖金请求间隔")
    args = parser.parse_args()
    if not 1 <= args.max_matches <= 20 or args.sleep_seconds < 0:
        raise SystemExit("max-matches 必须为 1..20，sleep-seconds 必须非负")
    now = datetime.now(UTC)
    if args.offline_results:
        results_payload = _read_json(args.offline_results)
    else:
        if not args.begin or not args.end:
            raise SystemExit("联网模式必须提供 --begin 和 --end")
        results_payload = fetch_uniform_results(args.begin, args.end, page_size=args.max_matches)
    preliminary = normalize_uniform_results(results_payload, ingested_at=now)
    bonus_payloads: dict[str, Mapping[str, Any]] = {}
    for row in preliminary[:args.max_matches]:
        match_id = str(row["match_id"])
        if args.offline_bonus_dir:
            path = args.offline_bonus_dir / f"{match_id}.json"
            if path.exists():
                bonus_payloads[match_id] = _read_json(path)
        elif not args.offline_results:
            bonus_payloads[match_id] = fetch_fixed_bonus_history(match_id)
            if args.sleep_seconds:
                time.sleep(args.sleep_seconds)
    summary = archive_batch(
        results_payload=results_payload, bonus_payloads=bonus_payloads,
        root=args.output_dir, ingested_at=now,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
