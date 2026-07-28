"""Create an auditable PAPER_ONLY ROI report from frozen predictions.

This command intentionally does not fetch odds or generate selections.  It can
only settle records that were frozen before each sale cutoff, against the
official-result samples produced by ``settle_prospective_snapshots.py``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jingcai.prospective_roi import prospective_return_summary, settle_frozen_candidates


def _load_list(path: Path, *, label: str) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SystemExit(f"{label} must be a JSON array of objects: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Report PAPER_ONLY prospective ROI")
    parser.add_argument("--frozen", type=Path, required=True, help="pre-cutoff frozen candidate JSON")
    parser.add_argument("--samples", type=Path, required=True, help="official result sample JSON")
    parser.add_argument("--stake", type=float, default=2.0, help="fixed stake for every single selection")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = settle_frozen_candidates(
        _load_list(args.frozen, label="frozen candidates"),
        _load_list(args.samples, label="official result samples"),
        stake=args.stake,
    )
    summary = prospective_return_summary(rows, stake=args.stake)
    report = {
        "model_state": "PAPER_ONLY",
        "method": "fixed-stake singles; only pre-cutoff frozen predictions and official results",
        "settlements": rows,
        "summary": summary,
        "pending": sum(row["settlement_status"] == "pending" for row in rows),
        "void": sum(row["settlement_status"] == "void" for row in rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), **summary, "pending": report["pending"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
