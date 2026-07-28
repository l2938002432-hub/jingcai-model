"""Create a deterministic decision-time coverage report from archived history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jingcai.history_audit import audit_history_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="审计官方历史竞彩奖金覆盖率")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/history-coverage.json"))
    parser.add_argument("--decision-offset-minutes", type=int, default=105)
    parser.add_argument("--max-snapshot-age-minutes", type=int, default=30)
    args = parser.parse_args()
    results_path = args.input_dir / "normalized-results.json"
    points_path = args.input_dir / "normalized-bonus-points.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    points = json.loads(points_path.read_text(encoding="utf-8"))
    if not isinstance(results, list) or not isinstance(points, list):
        raise SystemExit("归档文件格式无效")
    report = audit_history_coverage(
        results, points, decision_offset_minutes=args.decision_offset_minutes,
        max_snapshot_age_minutes=args.max_snapshot_age_minutes,
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
