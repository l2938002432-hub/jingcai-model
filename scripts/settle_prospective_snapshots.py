"""Fetch official results for captured snapshots and materialize pending/settled samples."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from jingcai.prospective_validation import attach_official_results, load_captured_fixtures
from jingcai.providers.sporttery import fetch_uniform_results, normalize_uniform_results


def main() -> int:
    parser = argparse.ArgumentParser(description="关联前向快照与官方赛果")
    parser.add_argument("--snapshot-root", type=Path, default=Path("data/prospective-snapshots"))
    parser.add_argument("--begin", required=True, help="赛果查询开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="赛果查询结束日期 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=Path("data/prospective-validation/samples.json"))
    parser.add_argument("--results-json", type=Path, help="离线官方赛果 JSON")
    args = parser.parse_args()
    fixtures = load_captured_fixtures(args.snapshot_root)
    payload = json.loads(args.results_json.read_text(encoding="utf-8")) if args.results_json else fetch_uniform_results(args.begin, args.end, page_size=100)
    if not isinstance(payload, dict):
        raise SystemExit("官方赛果必须是 JSON 对象")
    results = normalize_uniform_results(payload, ingested_at=datetime.now(UTC))
    samples = attach_official_results(fixtures, results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {status: sum(row["result_status"] == status for row in samples) for status in ("finished", "pending", "conflict")}
    print(json.dumps({"samples": len(samples), **counts, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
