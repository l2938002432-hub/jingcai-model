from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from jingcai import __version__
from jingcai.reporting import render_daily_report, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jingcai", description="竞彩概率研究工具")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="显示当前发布状态")
    demo = subparsers.add_parser("demo-report", help="生成不含真实推荐的示例报告")
    demo.add_argument("--output", default="reports/demo.html")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print(json.dumps({"version": __version__, "state": "RESEARCH"}, ensure_ascii=False))
        return 0
    if args.command == "demo-report":
        content = render_daily_report(
            generated_at=datetime.now(UTC),
            model_state="PAPER_ONLY",
            data_fresh=True,
            candidates=[
                {
                    "label": "演示主队 vs 演示客队",
                    "play": "胜平负-主胜",
                    "probability": 0.51,
                    "conservative_ev": 0.03,
                }
            ],
        )
        output = write_report(args.output, content)
        print(output.resolve())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

