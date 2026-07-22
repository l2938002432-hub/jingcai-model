from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_RECOMMENDATION_STATES = {"LIMITED_LIVE", "LIVE"}


def render_daily_report(
    *,
    generated_at: datetime,
    model_state: str,
    candidates: Sequence[Mapping[str, Any]],
    data_fresh: bool,
) -> str:
    can_recommend = data_fresh and model_state in ALLOWED_RECOMMENDATION_STATES
    banner = "数据正常" if data_fresh else "数据过期：建议已隐藏"
    rows: list[str] = []
    for item in candidates:
        label = html.escape(str(item.get("label", "未知比赛")))
        play = html.escape(str(item.get("play", "-")))
        probability = float(item.get("probability", 0.0))
        conservative_ev = float(item.get("conservative_ev", 0.0))
        decimal_odds = item.get("decimal_odds")
        market_probability = item.get("market_probability")
        action = "候选" if can_recommend and conservative_ev > 0 else "观察/模拟"
        details = ""
        if decimal_odds is not None and market_probability is not None:
            details = f"<br><small>奖金 {float(decimal_odds):.2f} · 市场概率 {float(market_probability):.1%}</small>"
        rows.append(
            "<tr>"
            f"<td>{label}</td><td>{play}</td><td>{probability:.1%}</td>"
            f"<td>{conservative_ev:.1%}{details}</td><td>{action}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='5'>今日无符合门槛的候选</td></tr>")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>竞彩概率研究日报</title><style>
body{{font-family:system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#172033}}
.banner{{padding:1rem;background:#eef5ff;border-radius:10px}}table{{width:100%;border-collapse:collapse;margin-top:1rem}}
th,td{{padding:.65rem;border-bottom:1px solid #ddd;text-align:left}}small{{color:#667085}}
</style></head><body><h1>竞彩概率研究日报</h1>
<div class="banner"><strong>{html.escape(banner)}</strong><br>
<small>生成：{html.escape(generated_at.isoformat())}　模型状态：{html.escape(model_state)}</small></div>
<table><thead><tr><th>比赛</th><th>玩法</th><th>模型概率</th><th>保守EV</th><th>状态</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p><small>仅供个人概率研究，不保证中奖或盈利；系统不会自动投注。</small></p></body></html>"""


def write_report(path: str | Path, content: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def render_probability_report(result: Mapping[str, Any]) -> str:
    market_titles = {
        "match_result": "胜平负",
        "handicap_result": f"让球胜平负（{int(result.get('handicap', 0)):+d}）",
        "total_goals": "总进球",
        "correct_score": "比分",
        "half_full": "半全场",
    }
    sections: list[str] = []
    for key, title in market_titles.items():
        probabilities = result.get(key, {})
        ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        rows = "".join(
            f"<tr><td>{html.escape(str(outcome))}</td><td>{float(probability):.2%}</td></tr>"
            for outcome, probability in ordered
        )
        sections.append(f"<section><h2>{html.escape(title)}</h2><table>{rows}</table></section>")
    fixture = f"{result.get('home_team', '')} vs {result.get('away_team', '')}"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="robots" content="noindex"><title>{html.escape(fixture)} 概率研究</title><style>
body{{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}
.notice{{background:#fff4d6;padding:1rem;border-radius:10px}}.markets{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}}
section{{border:1px solid #e0e6ef;border-radius:10px;padding:1rem}}table{{width:100%;border-collapse:collapse}}td{{padding:.45rem;border-bottom:1px solid #eee}}
td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}</style></head><body>
<h1>{html.escape(fixture)}</h1><div class="notice"><strong>状态：{html.escape(str(result.get('state', 'RESEARCH')))}</strong><br>
当前只展示历史模型研究概率，没有可信竞彩奖金时不计算 ROI，也不构成正式投注建议。</div>
<div class="markets">{''.join(sections)}</div><p><small>模型：{html.escape(str(result.get('model', '')))}；生成：{html.escape(str(result.get('generated_at', '')))}</small></p>
</body></html>"""
