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
    return (
        len(parts) == 4
        and parts[0] == "reports"
        and DATE_PATTERN.fullmatch(parts[1]) is not None
        and RELEASE_PATTERN.fullmatch(parts[2]) is not None
        and parts[3:] in (("index.html",), ("report.json",))
    )


def _prune_nonpublic_files(output_dir: Path) -> None:
    for path in output_dir.rglob("*"):
        if path.is_file() and not _is_public_path(path.relative_to(output_dir)):
            path.unlink()


def build_public_site(html_input: Path, json_input: Path, output_dir: Path, release_id: str) -> Path:
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
    dated_dir = output_dir / "reports" / str(report["report_date"]) / release_id
    dated_dir.mkdir(parents=True, exist_ok=True)
    (dated_dir / "index.html").write_text(report_html, encoding="utf-8")
    _write_json(dated_dir / "report.json", public_report)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(report_html, encoding="utf-8")
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
    args = parser.parse_args()
    dated_dir = build_public_site(args.html, args.json, args.output_dir, args.release_id)
    print(dated_dir.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
