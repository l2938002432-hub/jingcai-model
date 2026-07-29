"""Build a public, append-only report site from explicit daily report inputs."""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


PUBLIC_REPORT_FIELDS = (
    "schema_version",
    "release_id",
    "release_hash",
    "report_date",
    "generated_at",
    "source_as_of",
    "fixtures",
    "candidates",
    "fixture_details",
    "candidate_details",
    "model_state",
)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELEASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _read_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("report JSON is unreadable or invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("report JSON must contain an object")
    missing = [field for field in PUBLIC_REPORT_FIELDS if field not in value]
    if missing:
        raise ValueError(f"report JSON is missing public fields: {', '.join(missing)}")
    report_date = str(value["report_date"])
    if not DATE_PATTERN.fullmatch(report_date):
        raise ValueError("report_date must use YYYY-MM-DD")
    return value


def _public_report(report: dict[str, Any], release_id: str) -> dict[str, Any]:
    if str(report["release_id"]) != release_id:
        raise ValueError("release_id must match the frozen report metadata")
    result = {field: report[field] for field in PUBLIC_REPORT_FIELDS}
    result["historical_path"] = f"reports/{report['report_date']}/{release_id}/"
    return result


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_settlement(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"frozen": 0, "pending": 0, "summary": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("summary", {}), dict):
        raise ValueError("settlement JSON is invalid")
    return value


def _render_review_page(report: dict[str, Any], settlement: dict[str, Any]) -> str:
    summary = settlement.get("summary", {})
    def money(key: str) -> str:
        return f"{float(summary.get(key, 0.0)):.2f} 元"
    rows = []
    for item in settlement.get("settlements", []):
        if not isinstance(item, dict):
            continue
        rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(item.get("match_id", ""))), html.escape(str(item.get("market", ""))),
            html.escape(str(item.get("outcome", ""))), html.escape(str(item.get("settlement_status", "pending"))),
            html.escape(f"{float(item.get('profit', 0.0)):.2f}"),
        ))
    body = "".join(rows) or "<tr><td colspan='5'>暂无已冻结或已结算的候选</td></tr>"
    return f'''<!doctype html><html lang="zh-CN" data-view="review"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>收益复盘</title><style>
:root{{--bg:#f7f5f2;--panel:#fffdfa;--text:#262421;--muted:#746f68;--line:#e6e1da;--brand:#b75e2c}}html[data-theme="night"]{{--bg:#1c1a18;--panel:#282522;--text:#f5f0e8;--muted:#b8b0a7;--line:#48423c;--brand:#ee9562}}html[data-theme="blue"]{{--bg:#edf2f8;--panel:#fff;--text:#14233b;--muted:#61718b;--line:#d6dfec;--brand:#285ea8}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:980px;margin:auto;padding:28px 18px}}nav{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 0 24px}}a,button{{color:var(--text);text-decoration:none;border:1px solid var(--line);border-radius:9px;background:transparent;padding:7px 10px;font:inherit;cursor:pointer}}.links,.themes{{display:flex;gap:7px}}h1{{font-size:2rem;margin:0 0 7px}}p{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}.metric,section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}.metric span{{display:block;color:var(--muted);font-size:.82rem}}.metric strong{{display:block;margin-top:6px;font-size:1.35rem}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 8px;border-bottom:1px solid var(--line);text-align:left}}@media(max-width:700px){{.grid{{grid-template-columns:1fr 1fr}}}} </style></head><body><main><nav><div class="links"><a href="/jingcai-model/">每日比赛</a><a href="/jingcai-model/candidates/">候选决策</a><a href="/jingcai-model/review/">收益复盘</a></div><div class="themes"><button data-theme="warm">暖白</button><button data-theme="night">夜间</button><button data-theme="blue">深蓝</button></div></nav><p>赛前冻结 → 官方赛果结算</p><h1>收益复盘</h1><p>仅已结束且由官方结果确认的比赛计入 ROI；待结算不会美化收益。</p><div class="grid"><div class="metric"><span>冻结候选</span><strong>{int(settlement.get("frozen", 0))}</strong></div><div class="metric"><span>待结算</span><strong>{int(settlement.get("pending", 0))}</strong></div><div class="metric"><span>累计净利润</span><strong>{money("profit")}</strong></div><div class="metric"><span>ROI / 最大回撤</span><strong>{float(summary.get("roi", 0.0)):.1%} / {money("max_drawdown")}</strong></div></div><section><h2>结算明细</h2><table><thead><tr><th>比赛</th><th>玩法</th><th>选择</th><th>状态</th><th>净利润</th></tr></thead><tbody>{body}</tbody></table></section></main><script>const t=localStorage.getItem("jingcai-theme")||"warm";if(t!=="warm")document.documentElement.dataset.theme=t;document.querySelectorAll("[data-theme]").forEach(b=>b.onclick=()=>{{const v=b.dataset.theme;document.documentElement.dataset.theme=v==="warm"?"":v;localStorage.setItem("jingcai-theme",v)}})</script></body></html>'''


def _history_entries(site_dir: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for metadata_path in site_dir.glob("reports/*/*/report.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(metadata, dict):
            continue
        report_date = str(metadata.get("report_date", ""))
        release_id = str(metadata.get("release_id", ""))
        if DATE_PATTERN.fullmatch(report_date) and RELEASE_PATTERN.fullmatch(release_id):
            entries.append({
                "report_date": report_date,
                "release_id": release_id,
                "path": f"{report_date}/{release_id}/",
                "generated_at": str(metadata.get("generated_at", "")),
            })
    return sorted(entries, key=lambda row: (row["report_date"], row["release_id"]), reverse=True)


def _render_history(entries: list[dict[str, str]]) -> str:
    rows = "".join(
        "<li><a href='{path}'>{date}</a><small>发布 {release}</small></li>".format(
            path=html.escape(row["path"], quote=True),
            date=html.escape(row["report_date"]),
            release=html.escape(row["release_id"]),
        )
        for row in entries
    )
    if not rows:
        rows = "<li>暂无历史报告</li>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>竞彩研究历史报告</title><style>
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#172033}}
ul{{list-style:none;padding:0}}li{{display:flex;justify-content:space-between;gap:1rem;padding:.8rem 0;border-bottom:1px solid #e3e8ef}}
small{{color:#667085}}</style></head><body><h1>竞彩研究历史报告</h1>
<p>历史奖金和数据可能已经变化，仅用于审计与复盘。</p><ul>{rows}</ul><p><a href="../">返回最新报告</a></p></body></html>"""


def _is_public_path(relative: Path) -> bool:
    parts = relative.parts
    if parts and parts[0] == ".git":
        return True  # workflow metadata is removed after persistence and before Pages upload
    if parts in (("index.html",), ("report.json",), ("reports", "index.html"), ("reports", "index.json")):
        return True
    if len(parts) == 2 and parts[0] in {"matches", "candidates", "review"} and parts[1] == "index.html":
        return True
    return (
        len(parts) == 4
        and parts[0] == "reports"
        and DATE_PATTERN.fullmatch(parts[1]) is not None
        and RELEASE_PATTERN.fullmatch(parts[2]) is not None
        and parts[3:] in (("index.html",), ("report.json",))
    ) or (
        len(parts) == 5
        and parts[0] == "reports"
        and DATE_PATTERN.fullmatch(parts[1]) is not None
        and RELEASE_PATTERN.fullmatch(parts[2]) is not None
        and parts[3] in {"matches", "candidates", "review"}
        and parts[4] == "index.html"
    )


def _prune_nonpublic_files(output_dir: Path) -> None:
    for path in output_dir.rglob("*"):
        if path.is_file() and not _is_public_path(path.relative_to(output_dir)):
            path.unlink()


def build_public_site(html_input: Path, json_input: Path, output_dir: Path, release_id: str, settlement_input: Path | None = None) -> Path:
    if not RELEASE_PATTERN.fullmatch(release_id):
        raise ValueError("release_id contains unsafe characters")
    report = _read_report(json_input)
    try:
        report_html = html_input.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("report HTML is unreadable") from exc
    if "<html" not in report_html.lower():
        raise ValueError("report HTML does not look like an HTML document")

    public_report = _public_report(report, release_id)
    settlement = _read_settlement(settlement_input)
    dated_dir = output_dir / "reports" / str(report["report_date"]) / release_id
    dated_dir.mkdir(parents=True, exist_ok=True)
    (dated_dir / "index.html").write_text(report_html, encoding="utf-8")
    _write_json(dated_dir / "report.json", public_report)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(report_html, encoding="utf-8")
    for view in ("matches", "candidates", "review"):
        variant = _render_review_page(report, settlement) if view == "review" else report_html.replace("<html", f'<html data-view="{view}"', 1)
        for parent in (output_dir, dated_dir):
            destination = parent / view / "index.html"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(variant, encoding="utf-8")
    _write_json(output_dir / "report.json", public_report)
    entries = _history_entries(output_dir)
    reports_dir = output_dir / "reports"
    (reports_dir / "index.html").write_text(_render_history(entries), encoding="utf-8")
    _write_json(reports_dir / "index.json", {"reports": entries})
    _prune_nonpublic_files(output_dir)
    return dated_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--settlement", type=Path)
    args = parser.parse_args()
    dated_dir = build_public_site(args.html, args.json, args.output_dir, args.release_id, args.settlement)
    print(dated_dir.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
