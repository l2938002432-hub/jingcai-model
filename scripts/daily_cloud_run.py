"""Generate the strict daily-live report, archive it, and notify safely."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jingcai.__main__ import main as jingcai_main
from jingcai.daily import parse_official_update
from jingcai.notifications import NotificationSummary, send_configured
from jingcai.providers.sporttery import fetch_sporttery_payload, normalize_payload, save_snapshot


class FileDedupeStore:
    """Small persistent store suitable for a retained CI artifact directory."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _keys(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return {str(item) for item in value} if isinstance(value, list) else set()

    def contains(self, key: str) -> bool:
        return key in self._keys()

    def add(self, key: str) -> None:
        keys = self._keys() | {key}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(keys), ensure_ascii=False), encoding="utf-8")


def format_summary(report: dict[str, Any]) -> str:
    return "\n".join([
        f"**报告日期**：{report['report_date']}",
        f"**官方在售比赛**：{report['fixtures']} 场",
        f"**通过玩法级准入的模拟候选**：{report['candidates']} 个",
        f"**官方数据时间**：{report['source_as_of']}",
        f"**运行状态**：{report['model_state']}",
        "仅用于概率研究；没有通过验收的玩法不会推荐，不保证中奖或盈利。",
    ])


def _run_daily_live(arguments: list[str]) -> dict[str, Any]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = jingcai_main(arguments)
    if exit_code != 0:
        raise RuntimeError(f"daily-live failed with exit code {exit_code}")
    lines = [line for line in output.getvalue().splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("daily-live produced no machine-readable result")
    result = json.loads(lines[-1])
    if not isinstance(result, dict):
        raise RuntimeError("daily-live returned an invalid result")
    return result


def run(
    output_dir: Path,
    *,
    csv_path: Path = Path("data/raw/football-data/E0_2025-26.csv"),
    club_history_csv: Path = Path("data/raw/club-history/Matches.csv"),
    club_elo_csv: Path = Path("data/raw/club-history/EloRatings.csv"),
    uefa_history_dir: Path = Path("data/raw/uefa"),
    fetcher: Callable[[], dict[str, Any]] = fetch_sporttery_payload,
    live_runner: Callable[[list[str]], dict[str, Any]] = _run_daily_live,
    notifier: Callable[..., NotificationSummary] = send_configured,
) -> tuple[Path, Path, Path, NotificationSummary]:
    """Run one production cycle; raises unless notification was delivered/already sent."""
    payload = fetcher()
    source_as_of = parse_official_update(payload)
    china_timezone = timezone(timedelta(hours=8))
    report_date = source_as_of.astimezone(china_timezone).date().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = save_snapshot(payload, output_dir / f"sporttery-{report_date}.json")
    fixtures = normalize_payload(payload, fetched_at=source_as_of)
    fixtures_path = output_dir / f"fixtures-{report_date}.json"
    fixtures_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = output_dir / f"report-{report_date}.html"

    live_result = live_runner([
        "daily-live", "--csv", str(csv_path), "--season", "2025-26",
        "--club-history-csv", str(club_history_csv),
        "--history-divisions", "BRA,NOR,USA", "--snapshot-json", str(raw_path),
        "--aliases-json", "config/team-aliases.json",
        "--acceptance-json", "config/model-acceptance.json", "--output", str(html_path),
        "--club-elo-csv", str(club_elo_csv), "--uefa-history-dir", str(uefa_history_dir),
    ])
    if not html_path.exists():
        raise RuntimeError("daily-live did not create the HTML report")

    report: dict[str, Any] = {
        "report_date": report_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_as_of": live_result.get("source_as_of", source_as_of.isoformat()),
        "fixtures": int(live_result.get("fixtures", len(fixtures))),
        "candidates": int(live_result.get("candidates", 0)),
        "model_state": "PAPER_ONLY",
        "html": html_path.name,
        "raw_snapshot": raw_path.name,
        "normalized_snapshot": fixtures_path.name,
    }
    json_path = output_dir / f"report-{report_date}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Hash the decision-bearing content, not generated timestamps or absolute paths,
    # so a retry of the same report is idempotent across runners.
    hash_material = {
        key: report[key]
        for key in ("report_date", "source_as_of", "fixtures", "candidates", "model_state")
    }
    content_hash = hashlib.sha256(
        json.dumps(hash_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    dedupe_key = f"daily-report:{report_date}:{content_hash}"
    delivery = notifier(
        f"竞彩研究日报 {report_date}", format_summary(report), require_configured=True,
        dedupe_key=dedupe_key, dedupe_store=FileDedupeStore(output_dir / ".notification-dedupe.json"),
    )
    if not delivery.delivered and not delivery.duplicate:
        raise RuntimeError("all configured notification channels failed")
    if delivery.failures:
        raise RuntimeError("one or more configured notification channels failed")
    return html_path, json_path, raw_path, delivery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/daily"))
    parser.add_argument("--csv", type=Path, default=Path("data/raw/football-data/E0_2025-26.csv"))
    parser.add_argument("--club-history-csv", type=Path, default=Path("data/raw/club-history/Matches.csv"))
    parser.add_argument("--club-elo-csv", type=Path, default=Path("data/raw/club-history/EloRatings.csv"))
    parser.add_argument("--uefa-history-dir", type=Path, default=Path("data/raw/uefa"))
    args = parser.parse_args()
    html_path, json_path, raw_path, delivery = run(
        args.output_dir, csv_path=args.csv, club_history_csv=args.club_history_csv,
        club_elo_csv=args.club_elo_csv, uefa_history_dir=args.uefa_history_dir,
    )
    summary = (
        f"html={html_path}\njson={json_path}\nraw={raw_path}\n"
        f"notified={','.join(item.channel for item in delivery.successes) or 'duplicate'}"
    )
    print(summary)
    if github_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(github_summary).open("a", encoding="utf-8") as handle:
            handle.write("## 每日竞彩研究任务\n\n```text\n" + summary + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
