"""Fetch the official daily slate, archive it, and notify configured channels."""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from jingcai.notifications import send_configured
from jingcai.providers.sporttery import fetch_sporttery_payload, normalize_payload, save_snapshot


def format_summary(fixtures: list[dict]) -> str:
    complete = sum(len(item.get("odds", {})) == 5 for item in fixtures)
    lines = [f"在售比赛：{len(fixtures)} 场", f"五玩法完整：{complete} 场"]
    lines.extend(f"- {item['match_num']} {item['home_team']} vs {item['away_team']}（{item['kickoff'][11:16]}）" for item in fixtures[:15])
    if len(fixtures) > 15:
        lines.append(f"- 另有 {len(fixtures) - 15} 场")
    lines.append("仅为概率研究，不保证中奖或盈利；没有模型优势时应放弃投注。")
    return "\n".join(lines)


def run(output_dir: Path) -> tuple[Path, Path, list[str]]:
    now = datetime.now().astimezone()
    payload = fetch_sporttery_payload()
    fixtures = normalize_payload(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    raw_path = save_snapshot(payload, output_dir / f"sporttery-{stamp}.json")
    normalized_path = output_dir / f"fixtures-{stamp}.json"
    normalized_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    channels = [r.channel for r in send_configured(f"竞彩数据日报 {now:%Y-%m-%d}", format_summary(fixtures))]
    return raw_path, normalized_path, channels


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/daily"))
    args = parser.parse_args()
    raw_path, normalized_path, channels = run(args.output_dir)
    summary = f"saved={raw_path}\nnormalized={normalized_path}\nnotified={','.join(channels) or 'none'}"
    print(summary)
    if github_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(github_summary).open("a", encoding="utf-8") as handle:
            handle.write("## 每日竞彩数据任务\n\n```text\n" + summary + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
