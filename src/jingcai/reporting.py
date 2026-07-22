from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_RECOMMENDATION_STATES = {"LIMITED_LIVE", "LIVE"}


def render_daily_report(
    *, generated_at: datetime, model_state: str,
    candidates: Sequence[Mapping[str, Any]], data_fresh: bool,
    source_as_of: datetime | None = None,
) -> str:
    can_recommend = data_fresh and model_state in ALLOWED_RECOMMENDATION_STATES
    banner = "\u6570\u636e\u6b63\u5e38" if data_fresh else "\u6570\u636e\u8fc7\u671f\uff1a\u5efa\u8bae\u5df2\u9690\u85cf"
    rows: list[str] = []
    for item in candidates:
        label = html.escape(str(item.get("label", "\u672a\u77e5\u6bd4\u8d5b")))
        play = html.escape(str(item.get("play", "-")))
        probability = float(item.get("probability", 0.0))
        ev = float(item.get("conservative_ev", 0.0))
        action = "\u5019\u9009" if can_recommend and ev > 0 else "\u89c2\u5bdf/\u6a21\u62df"
        details = ""
        if item.get("decimal_odds") is not None and item.get("market_probability") is not None:
            details = (
                f"<br><small>\u5956\u91d1 {float(item['decimal_odds']):.2f} &middot; "
                f"\u5e02\u573a\u6982\u7387 {float(item['market_probability']):.1%}</small>"
            )
        if item.get("sale_cutoff"):
            estimate = "\uff08\u4f30\u7b97\uff0c\u975e\u5b98\u65b9\u505c\u552e\u65f6\u95f4\uff09" if item.get("sale_cutoff_estimated") else ""
            details += f"<br><small>\u505c\u552e\uff1a{html.escape(str(item['sale_cutoff']))}{estimate}</small>"
        rows.append(
            f"<tr><td>{label}</td><td>{play}</td><td>{probability:.1%}</td>"
            f"<td>{ev:.1%}{details}</td><td>{action}</td></tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='5'>\u4eca\u65e5\u65e0\u7b26\u5408\u95e8\u69db\u7684\u5019\u9009</td></tr>")
    source_text = f"\u3000\u6570\u636e\u65f6\u95f4\uff1a{html.escape(source_as_of.isoformat())}" if source_as_of else ""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>\u7ade\u5f69\u6982\u7387\u7814\u7a76\u65e5\u62a5</title><style>
body{{font-family:system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#172033}}
.banner{{padding:1rem;background:#eef5ff;border-radius:10px}}table{{width:100%;border-collapse:collapse;margin-top:1rem}}
th,td{{padding:.65rem;border-bottom:1px solid #ddd;text-align:left}}small{{color:#667085}}</style></head><body>
<h1>\u7ade\u5f69\u6982\u7387\u7814\u7a76\u65e5\u62a5</h1><div class="banner"><strong>{banner}</strong><br>
<small>\u751f\u6210\uff1a{html.escape(generated_at.isoformat())}\u3000\u6a21\u578b\u72b6\u6001\uff1a{html.escape(model_state)}{source_text}</small></div>
<table><thead><tr><th>\u6bd4\u8d5b</th><th>\u73a9\u6cd5</th><th>\u6a21\u578b\u6982\u7387</th><th>\u4fdd\u5b88EV</th><th>\u72b6\u6001</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><p><small>\u4ec5\u4f9b\u4e2a\u4eba\u6982\u7387\u7814\u7a76\uff0c\u4e0d\u4fdd\u8bc1\u4e2d\u5956\u6216\u76c8\u5229\uff1b\u7cfb\u7edf\u4e0d\u4f1a\u81ea\u52a8\u6295\u6ce8\u3002</small></p></body></html>"""


def write_report(path: str | Path, content: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def render_probability_report(result: Mapping[str, Any]) -> str:
    titles = {
        "match_result": "\u80dc\u5e73\u8d1f",
        "handicap_result": f"\u8ba9\u7403\u80dc\u5e73\u8d1f\uff08{int(result.get('handicap', 0)):+d}\uff09",
        "total_goals": "\u603b\u8fdb\u7403", "correct_score": "\u6bd4\u5206", "half_full": "\u534a\u5168\u573a",
    }
    sections = []
    for key, title in titles.items():
        ordered = sorted(result.get(key, {}).items(), key=lambda item: item[1], reverse=True)
        rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td>{float(v):.2%}</td></tr>" for k, v in ordered)
        sections.append(f"<section><h2>{title}</h2><table>{rows}</table></section>")
    fixture = f"{result.get('home_team', '')} vs {result.get('away_team', '')}"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>{html.escape(fixture)} \u6982\u7387\u7814\u7a76</title><style>body{{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}.notice{{background:#fff4d6;padding:1rem;border-radius:10px}}.markets{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}}section{{border:1px solid #e0e6ef;border-radius:10px;padding:1rem}}table{{width:100%;border-collapse:collapse}}td{{padding:.45rem;border-bottom:1px solid #eee}}td:last-child{{text-align:right}}</style></head><body>
<h1>{html.escape(fixture)}</h1><div class="notice"><strong>\u72b6\u6001\uff1a{html.escape(str(result.get('state', 'RESEARCH')))}</strong><br>\u5f53\u524d\u53ea\u5c55\u793a\u5386\u53f2\u6a21\u578b\u7814\u7a76\u6982\u7387\uff0c\u6ca1\u6709\u53ef\u4fe1\u7ade\u5f69\u5956\u91d1\u65f6\u4e0d\u8ba1\u7b97 ROI\uff0c\u4e5f\u4e0d\u6784\u6210\u6b63\u5f0f\u6295\u6ce8\u5efa\u8bae\u3002</div>
<div class="markets">{''.join(sections)}</div><p><small>\u6a21\u578b\uff1a{html.escape(str(result.get('model', '')))}\uff1b\u751f\u6210\uff1a{html.escape(str(result.get('generated_at', '')))}</small></p></body></html>"""
