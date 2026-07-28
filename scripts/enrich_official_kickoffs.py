"""Attach recent official kickoff times to archived result records by matchId."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jingcai.providers.sporttery import (
    attach_official_kickoffs,
    fetch_result_match_page,
    official_kickoffs_from_match_page,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="按 matchId 补充官方开赛时刻")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page", type=int, action="append", help="官方最近赛果页，可重复")
    parser.add_argument("--offline-page", type=Path, action="append", help="离线官方赛果页 JSON，可重复")
    args = parser.parse_args()
    if not args.page and not args.offline_page:
        raise SystemExit("至少提供一个 --page 或 --offline-page")
    records = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit("输入必须是赛果数组")
    pages = []
    for path in args.offline_page or []:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit(f"无效离线页：{path}")
        pages.append(value)
    for page_no in args.page or []:
        pages.append(fetch_result_match_page(page_no=page_no))
    kickoffs = {}
    for page in pages:
        for match_id, kickoff in official_kickoffs_from_match_page(page).items():
            prior = kickoffs.setdefault(match_id, kickoff)
            if prior != kickoff:
                raise SystemExit(f"官方开赛时刻冲突：{match_id}")
    enriched = attach_official_kickoffs(records, kickoffs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    matched = sum("kickoff" in row for row in enriched)
    print(json.dumps({"matches": len(enriched), "kickoff_matched": matched, "pages": len(pages)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
