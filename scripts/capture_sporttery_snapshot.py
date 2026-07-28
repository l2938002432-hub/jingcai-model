"""Capture a single official on-sale snapshot without producing recommendations."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from jingcai.providers.sporttery import fetch_sporttery_payload
from jingcai.snapshot_capture import capture_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="采集一份官方在售竞彩快照")
    parser.add_argument("--output-dir", type=Path, default=Path("data/prospective-snapshots"))
    parser.add_argument("--payload-json", type=Path, help="离线重放官方原始 JSON")
    args = parser.parse_args()
    payload = json.loads(args.payload_json.read_text(encoding="utf-8")) if args.payload_json else fetch_sporttery_payload()
    if not isinstance(payload, dict):
        raise SystemExit("官方快照必须是 JSON 对象")
    print(json.dumps(capture_snapshot(args.output_dir, payload=payload, observed_at=datetime.now(UTC)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
