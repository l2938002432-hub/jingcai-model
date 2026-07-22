"""Reproduce the six-season EPL probability baseline validation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC
from pathlib import Path

from jingcai.pipeline import walk_forward_1x2
from jingcai.providers.football_data import load_football_data_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="data/raw/football-data")
    parser.add_argument("--min-train", type=int, default=760)
    args = parser.parse_args()
    paths = sorted(Path(args.directory).glob("E0_*.csv"))
    if not paths:
        raise SystemExit("未找到 E0_*.csv 历史数据")
    matches = []
    for path in paths:
        season = path.stem.removeprefix("E0_")
        matches.extend(
            load_football_data_csv(path, season=season, competition="E0", source_timezone=UTC)
        )
    result = walk_forward_1x2(matches, min_train=args.min_train)
    print(json.dumps({"total_matches": len(matches), **result.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

