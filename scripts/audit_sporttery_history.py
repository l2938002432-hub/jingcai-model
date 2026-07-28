"""Create a deterministic decision-time coverage report from archived history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jingcai.history_audit import audit_history_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="审计官方历史竞彩奖金覆盖率")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--results", type=Path, help="可选：已补官方开赛时刻的赛果文件")
    parser.add_argument("--output", type=Path, default=Path("reports/history-coverage.json"))
    parser.add_argument("--decision-offset-minutes", type=int, default=105)
    parser.add_argument("--max-snapshot-age-minutes", type=int, default=30)
    parser.add_argument("--minimum-coverage-percent", type=float, default=95.0)
    parser.add_argument("--protocol", type=Path, help="可选：冻结的验收协议 JSON")
    args = parser.parse_args()
    results_path = args.results or args.input_dir / "normalized-results.json"
    points_path = args.input_dir / "normalized-bonus-points.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    points = json.loads(points_path.read_text(encoding="utf-8"))
    if not isinstance(results, list) or not isinstance(points, list):
        raise SystemExit("归档文件格式无效")
    decision_offset = args.decision_offset_minutes
    max_age = args.max_snapshot_age_minutes
    minimum_coverage = args.minimum_coverage_percent
    if args.protocol:
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        first = protocol.get("decision_windows", {}).get("first", {}) if isinstance(protocol, dict) else {}
        if not isinstance(first, dict):
            raise SystemExit("验收协议格式无效")
        decision_offset = int(first["target_minutes_before_kickoff"])
        max_age = int(first["max_snapshot_age_minutes"])
        minimum_coverage = float(protocol["minimum_coverage_percent"])
    report = audit_history_coverage(
        results, points, decision_offset_minutes=decision_offset,
        max_snapshot_age_minutes=max_age,
        minimum_coverage_percent=minimum_coverage,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "result_matches": report["result_matches"],
        "safe_for_economic_backtest": report["safe_for_economic_backtest"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
