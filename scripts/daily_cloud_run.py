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
from jingcai.ledger import Ledger, LedgerKind, ReleaseManifest, freeze_release
from jingcai.frozen_registry import freeze_new_candidates
from jingcai.notifications import NotificationSummary, send_configured
from jingcai.notification_window import select_notification_candidates
from jingcai.projections import public_release_projection
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


def format_summary(report: dict[str, Any], panel_url: str | None = None) -> str:
    lines = [
        f"**报告日期**：{report['report_date']}",
        f"**官方在售比赛**：{report['fixtures']} 场",
        f"**通过玩法级准入的模拟候选**：{report['candidates']} 个",
        f"**官方数据时间**：{report['source_as_of']}",
        f"**运行状态**：{report['model_state']}",
    ]
    details = report.get("candidate_details", [])
    if details:
        lines.append("\n**模拟建议**")
        for item in details[:5]:
            match_number = item.get("match_number") or item.get("match_id", "")
            teams = (
                f"{item.get('home_team', '')} vs {item.get('away_team', '')}"
                if item.get("home_team") or item.get("away_team")
                else item.get("label", "")
            )
            market = item.get("market_label") or item.get("market", "")
            outcome = item.get("outcome_label") or item.get("outcome", "")
            lines.append(
                f"- **{match_number} {teams}**｜{market}：{outcome}｜"
                f"奖金 {float(item.get('decimal_odds', 0)):.2f}｜"
                f"模型 {float(item.get('probability', 0)):.1%}｜"
                f"保守EV {float(item.get('conservative_ev', 0)):.1%}｜"
                f"停售 {item.get('sale_cutoff', '未知')}"
            )
    else:
        lines.append("\n**今日无符合标准的投注建议**，不会为了凑单强行推荐。")
    if panel_url:
        lines.append(f"\n[打开当日完整面板]({panel_url})")
    lines.append("仅用于概率研究和模拟验证；没有通过验收的玩法不会推荐，不保证中奖或盈利。")
    return "\n".join(lines)


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
    snapshot_json: Path | None = None,
) -> tuple[Path, Path, Path, NotificationSummary]:
    """Run one production cycle; raises unless notification was delivered/already sent."""
    if snapshot_json is None:
        payload = fetcher()
    else:
        payload = json.loads(snapshot_json.read_text(encoding="utf-8"))
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

    fixture_details = live_result.get("fixture_details", fixtures)
    candidate_details = live_result.get("candidate_details", [])
    if not isinstance(fixture_details, list):
        fixture_details = fixtures
    if not isinstance(candidate_details, list):
        candidate_details = []
    release_material = {
        "report_date": report_date,
        "source_as_of": live_result.get("source_as_of", source_as_of.isoformat()),
        "fixture_details": fixture_details,
        "candidate_details": candidate_details,
        "model_state": "PAPER_ONLY",
    }
    release_hash = hashlib.sha256(
        json.dumps(release_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    release_id = f"{report_date}-{release_hash[:12]}"
    generated_at = datetime.now().astimezone().isoformat()
    public_projection = public_release_projection(
        {
            "release_id": release_id,
            "release_hash": release_hash,
            "report_date": report_date,
            "generated_at": generated_at,
            "source_as_of": release_material["source_as_of"],
            "model_state": "PAPER_ONLY",
        },
        fixtures=fixture_details,
        candidates=candidate_details,
    )
    config_path = Path("config/model-acceptance.json")
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
    snapshot_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    model_ledger = Ledger(output_dir / "model-ledger.jsonl", LedgerKind.MODEL)
    ledger_head_hash = freeze_release(
        model_ledger,
        ReleaseManifest(
            release_id=release_id,
            idempotency_key=release_id,
            published_at=datetime.fromisoformat(generated_at),
            source_as_of=source_as_of,
            snapshot_sha256=snapshot_sha256,
            model_version="daily-live-v1",
            config_sha256=config_sha256,
            rules_version="sporttery-v1",
            git_sha=os.environ.get("GITHUB_SHA", "local-uncommitted"),
            candidates=tuple(public_projection["candidates"]),
        ),
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "release_id": release_id,
        "release_hash": release_hash,
        "ledger_head_hash": ledger_head_hash,
        "report_date": report_date,
        "generated_at": generated_at,
        "source_as_of": live_result.get("source_as_of", source_as_of.isoformat()),
        "fixtures": int(live_result.get("fixtures", len(fixtures))),
        "candidates": int(live_result.get("candidates", 0)),
        "fixture_details": public_projection["fixtures"],
        "candidate_details": public_projection["candidates"],
        "model_state": "PAPER_ONLY",
        "html": html_path.name,
        "raw_snapshot": raw_path.name,
        "normalized_snapshot": fixtures_path.name,
    }
    notification_candidates = select_notification_candidates(candidate_details, observed_at=source_as_of)
    report["notification_candidates"] = len(notification_candidates)
    frozen_candidates = freeze_new_candidates(
        output_dir / "prospective-candidates.jsonl", notification_candidates,
        frozen_at=source_as_of,
    )
    report["newly_frozen_candidates"] = len(frozen_candidates)
    json_path = output_dir / f"report-{report_date}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    dedupe_key = f"daily-report:{release_id}"
    base_url = os.environ.get("PUBLIC_REPORT_BASE_URL", "").rstrip("/")
    panel_url = f"{base_url}/reports/{report_date}/{release_id}/" if base_url else None
    if not notification_candidates:
        notifier = lambda *args, **kwargs: NotificationSummary((), duplicate=True, dedupe_key=dedupe_key)
    delivery = notifier(
        f"竞彩研究日报 {report_date}", format_summary(report, panel_url), require_configured=True,
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
    parser.add_argument("--snapshot-json", type=Path)
    args = parser.parse_args()
    html_path, json_path, raw_path, delivery = run(
        args.output_dir, csv_path=args.csv, club_history_csv=args.club_history_csv,
        club_elo_csv=args.club_elo_csv, uefa_history_dir=args.uefa_history_dir,
        snapshot_json=args.snapshot_json,
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
