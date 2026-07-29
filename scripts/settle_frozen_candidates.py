"""Update the PAPER_ONLY prospective ROI report from official results."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jingcai.prospective_settlement import settle_registry
from jingcai.providers.sporttery import fetch_uniform_results, normalize_uniform_results
from jingcai.storage import AppendOnlyJsonlStore


def _dates(frozen: list[dict[str, object]]) -> tuple[str, str]:
    cutoffs = [datetime.fromisoformat(str(row["sale_cutoff"]).replace("Z", "+00:00")) for row in frozen]
    if not cutoffs or any(value.tzinfo is None for value in cutoffs):
        raise ValueError("frozen records require timezone-aware sale_cutoff")
    return min(cutoffs).date().isoformat(), (max(cutoffs).date() + timedelta(days=1)).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle frozen PAPER_ONLY candidates")
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stake", type=float, default=2.0)
    parser.add_argument("--results-json", type=Path, help="offline official results JSON")
    args = parser.parse_args()
    frozen = AppendOnlyJsonlStore(args.frozen).read_verified() if args.frozen.exists() else []
    if not frozen:
        report = {"model_state": "PAPER_ONLY", "frozen": 0, "settlements": [], "summary": {"bets": 0, "wins": 0, "stake": 0.0, "payout": 0.0, "profit": 0.0, "roi": 0.0, "max_drawdown": 0.0}, "pending": 0, "conflicts": 0}
    else:
        payload = json.loads(args.results_json.read_text(encoding="utf-8")) if args.results_json else fetch_uniform_results(*_dates(frozen), page_size=100)
        report = settle_registry(frozen, normalize_uniform_results(payload, ingested_at=datetime.now(UTC)), stake=args.stake)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "frozen": report["frozen"], "pending": report["pending"], **report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
