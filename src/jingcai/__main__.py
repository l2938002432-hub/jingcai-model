from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jingcai import __version__
from jingcai.daily import DailyLiveError, canonicalize_teams, parse_official_update, validate_freshness
from jingcai.identity import TeamAliases
from jingcai.markets import OFFICIAL_CORRECT_SCORES, correct_score, result_1x2, total_goals
from jingcai.models import ClubEloModel, HalfFullModel
from jingcai.pipeline import build_paper_candidates, matrix_mapping, predict_all_markets, walk_forward_1x2
from jingcai.providers.club_elo_history import ClubEloHistory, ClubEloHistoryError
from jingcai.providers.football_data import load_football_data_csv
from jingcai.providers.club_history import load_club_history_csv
from jingcai.providers.sporttery import fetch_sporttery_payload, normalize_payload, save_snapshot
from jingcai.providers.uefa import UefaError, normalize_match
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
    live = subparsers.add_parser("daily-live", help="获取官方数据并生成严格校验的实时 HTML 日报")
    _add_history_args(live)
    live.add_argument("--snapshot-json", help="使用已保存的官方原始快照，不联网")
    live.add_argument("--club-history-csv", help="MIT 多联赛冷启动历史 CSV")
    live.add_argument("--history-divisions", default="BRA,NOR,USA", help="冷启动联赛代码，逗号分隔")
    live.add_argument("--club-elo-csv", help="ClubElo historical snapshots CSV (UCL only)")
    live.add_argument("--uefa-history-dir", help="UEFA qualifying history JSON directory (UCL only)")
    live.add_argument("--aliases-json", default="config/team-aliases.json")
    live.add_argument("--acceptance-json", default="config/model-acceptance.json")
    live.add_argument("--save-snapshot", default="data/snapshots/sporttery-latest.json")
    live.add_argument("--max-age-minutes", type=int, default=30)
    live.add_argument("--safety-margin", type=float, default=0.03)
    live.add_argument("--output", default="reports/daily-live.html")
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


def _load_uefa_history(directory: str | Path, aliases: TeamAliases) -> list[dict[str, object]]:
    root = Path(directory)
    files = sorted(root.glob("*.json")) if root.is_dir() else []
    if not files:
        raise DailyLiveError("UCL is enabled but the UEFA history directory has no JSON files")
    rows: list[dict[str, object]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyLiveError(f"cannot read UEFA history: {path.name}") from exc
        items = payload.get("matches") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise DailyLiveError(f"invalid UEFA history schema: {path.name}")
        fetched_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        for item in items:
            if not isinstance(item, dict):
                raise DailyLiveError(f"non-object UEFA history record: {path.name}")
            phase = item.get("competitionPhase")
            if isinstance(phase, dict):
                phase = phase.get("code") or phase.get("type") or phase.get("name")
            if str(phase or "").upper() != "QUALIFYING":
                continue
            try:
                row = normalize_match(item, source_url=path.resolve().as_uri(), fetched_at=fetched_at)
            except UefaError as exc:
                raise DailyLiveError(f"invalid UEFA qualifying record in {path.name}: {exc}") from exc
            row["home_team"] = aliases.canonical(str(row["home_team"]))
            row["away_team"] = aliases.canonical(str(row["away_team"]))
            rows.append(row)
    if not rows:
        raise DailyLiveError("UEFA history has no completed qualifying matches")
    return rows


def _build_ucl_predictor(club_elo_csv: str, uefa_history_dir: str, aliases: TeamAliases):
    try:
        elo_history = ClubEloHistory.from_csv(club_elo_csv, aliases)
        matches = _load_uefa_history(uefa_history_dir, aliases)

        def prior(match, team, association):
            try:
                return elo_history.prior_provider(match, team, association)
            except ClubEloHistoryError:
                return 1300.0

        model = ClubEloModel(default_rating=1300.0).fit(matches, prior)
    except (OSError, ClubEloHistoryError, ValueError) as exc:
        raise DailyLiveError(f"invalid UCL ClubElo inputs: {exc}") from exc

    def predict(fixture):
        if str(fixture.get("competition_code", "")) != "UCL":
            return None
        home, away = str(fixture["home_team"]), str(fixture["away_team"])
        context = {
            "home_association": "__FALLBACK__", "away_association": "__FALLBACK__",
            "association_priors": {"__FALLBACK__": 1300.0},
        }
        matrix = matrix_mapping(model.predict_score_matrix(home, away, 10, **context))
        return {
            "match_result": result_1x2(matrix),
            "handicap_result": result_1x2(matrix, int(fixture.get("handicap", 0))),
            "total_goals": total_goals(matrix),
            "correct_score": correct_score(matrix, OFFICIAL_CORRECT_SCORES),
            "half_full": HalfFullModel(model).predict_proba(home, away, 10),
        }
    return predict


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
    if args.command == "daily-live":
        now = datetime.now(UTC)
        if args.snapshot_json:
            payload = json.loads(Path(args.snapshot_json).read_text(encoding="utf-8"))
        else:
            payload = fetch_sporttery_payload()
            save_snapshot(payload, args.save_snapshot)
        try:
            source_as_of = parse_official_update(payload)
            fixtures = normalize_payload(payload, fetched_at=source_as_of)
            history = _load_history(args)
            if args.club_history_csv:
                divisions = {item.strip() for item in args.history_divisions.split(",") if item.strip()}
                history.extend(load_club_history_csv(
                    args.club_history_csv, divisions=divisions, since="2018-01-01"
                ))
            aliases = json.loads(Path(args.aliases_json).read_text(encoding="utf-8"))
            history, fixtures = canonicalize_teams(history, fixtures, aliases)
            acceptance = json.loads(Path(args.acceptance_json).read_text(encoding="utf-8"))
            fixtures = [
                fixture for fixture in fixtures
                if acceptance.get(str(fixture.get("competition_code")), {}).get("approved") is True
            ]
            if bool(args.club_elo_csv) != bool(args.uefa_history_dir):
                raise DailyLiveError("UCL requires both --club-elo-csv and --uefa-history-dir")
            fixture_predictor = None
            if args.club_elo_csv and args.uefa_history_dir:
                fixture_predictor = _build_ucl_predictor(
                    args.club_elo_csv, args.uefa_history_dir, TeamAliases(aliases)
                )
            else:
                fixtures = [row for row in fixtures if str(row.get("competition_code")) != "UCL"]
            validate_freshness(
                source_as_of, now=now, max_age=timedelta(minutes=args.max_age_minutes)
            )
            if not fixtures:
                raise DailyLiveError("no approved fixtures have complete production inputs")
            candidates = build_paper_candidates(
                history, fixtures, prediction_time=now, safety_margin=args.safety_margin,
                acceptance_config=acceptance, fixture_predictor=fixture_predictor,
            )
        except DailyLiveError as exc:
            raise SystemExit(f"daily-live 安全拒绝: {exc}") from exc
        report = render_daily_report(
            generated_at=now, model_state="PAPER_ONLY", candidates=candidates,
            data_fresh=True, source_as_of=source_as_of, fixtures=fixtures,
        )
        output = write_report(args.output, report)
        print(json.dumps({
            "output": str(output.resolve()), "fixtures": len(fixtures),
            "candidates": len(candidates), "source_as_of": source_as_of.isoformat(),
            "fixture_details": fixtures,
            "candidate_details": candidates,
            "cutoff_notice": "sale_cutoff_estimated=true 表示停售时间为开赛前10分钟估算值",
        }, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
