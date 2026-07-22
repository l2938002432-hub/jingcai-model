from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jingcai import __version__
from jingcai.pipeline import build_paper_candidates, predict_all_markets, walk_forward_1x2
from jingcai.providers.football_data import load_football_data_csv
from jingcai.providers.sporttery import fetch_sporttery_payload, normalize_payload, save_snapshot
from jingcai.reporting import render_daily_report, render_probability_report, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jingcai", description="竞彩概率研究工具")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch = subparsers.add_parser("fetch-today", help="读取当天官方竞彩五玩法数据")
    fetch.add_argument("--output", default="data/snapshots/sporttery-latest.json")
    fetch.add_argument("--normalized-output", default="data/snapshots/fixtures-latest.json")
    subparsers.add_parser("status", help="显示当前发布状态")
    demo = subparsers.add_parser("demo-report", help="生成不含真实推荐的示例报告")
    demo.add_argument("--output", default="reports/demo.html")
    backtest = subparsers.add_parser("backtest-history", help="对 Football-Data CSV 做时间滚动概率回测")
    _add_history_args(backtest)
    backtest.add_argument("--min-train", type=int, default=30)
    predict = subparsers.add_parser("predict", help="用历史 CSV 训练并输出五类玩法研究概率")
    _add_history_args(predict)
    predict.add_argument("--home", required=True)
    predict.add_argument("--away", required=True)
    predict.add_argument("--handicap", type=int, default=0)
    predict.add_argument("--output")
    serve = subparsers.add_parser("serve", help="启动本地只读报告网页")
    serve.add_argument("--directory", default="reports")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    daily = subparsers.add_parser("daily-paper", help="根据人工导入的官方奖金生成模拟盈利日报")
    _add_history_args(daily)
    daily.add_argument("--fixtures-json", required=True)
    daily.add_argument("--safety-margin", type=float, default=0.03)
    daily.add_argument("--output", default="reports/daily-paper.html")
    return parser


def _add_history_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--csv", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--competition")
    parser.add_argument("--source-timezone", default="UTC")


def _load_history(args: argparse.Namespace) -> list[dict[str, object]]:
    timezone_name = args.source_timezone.strip()
    if timezone_name.upper() in {"UTC", "ETC/UTC", "Z"}:
        source_timezone = UTC
    else:
        try:
            source_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise SystemExit(
                f"时区 {timezone_name!r} 不可用；请安装 tzdata，或先使用 --source-timezone UTC"
            ) from exc
    return list(
        load_football_data_csv(
            args.csv,
            season=args.season,
            competition=args.competition,
            source_timezone=source_timezone,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fetch-today":
        payload = fetch_sporttery_payload()
        raw_path = save_snapshot(payload, args.output)
        fixtures = normalize_payload(payload)
        normalized = Path(args.normalized_output)
        normalized.parent.mkdir(parents=True, exist_ok=True)
        normalized.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "raw": str(raw_path.resolve()), "normalized": str(normalized.resolve()),
            "matches": len(fixtures), "last_update": payload["value"].get("lastUpdateTime"),
        }, ensure_ascii=False))
        return 0
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
    if args.command == "backtest-history":
        result = walk_forward_1x2(_load_history(args), min_train=args.min_train)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "predict":
        result = predict_all_markets(
            _load_history(args), home_team=args.home, away_team=args.away, handicap=args.handicap
        )
        if args.output:
            output = Path(args.output)
            if output.suffix.lower() == ".html":
                write_report(output, render_probability_report(result))
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(output.resolve())
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        directory = Path(args.directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
        server = ThreadingHTTPServer((args.host, args.port), handler)
        print(f"http://{args.host}:{args.port}/")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.command == "daily-paper":
        fixtures = json.loads(Path(args.fixtures_json).read_text(encoding="utf-8"))
        if not isinstance(fixtures, list):
            raise SystemExit("fixtures JSON 顶层必须是数组")
        candidates = build_paper_candidates(
            _load_history(args), fixtures, safety_margin=args.safety_margin
        )
        report = render_daily_report(
            generated_at=datetime.now(UTC),
            model_state="PAPER_ONLY",
            candidates=candidates,
            data_fresh=True,
        )
        output = write_report(args.output, report)
        print(json.dumps({"output": str(output.resolve()), "candidates": len(candidates)}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
