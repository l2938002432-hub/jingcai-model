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
        action = "候选" if can_recommend and conservative_ev > 0 else "观察/模拟"
        rows.append(
            "<tr>"
            f"<td>{label}</td><td>{play}</td><td>{probability:.1%}</td>"
            f"<td>{conservative_ev:.1%}</td><td>{action}</td>"
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

