from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ALLOWED_RECOMMENDATION_STATES = {"LIMITED_LIVE", "LIVE"}
MODEL_STATE_LABELS = {
    "RESEARCH": "研究中",
    "PAPER_ONLY": "模拟验证中",
    "LIMITED_LIVE": "小额验证",
    "LIVE": "正式运行",
    "PAUSED": "已暂停",
    "ROLLED_BACK": "已回滚",
    "PAUSED_CLOUD": "云端已暂停",
}
CHINA_TIMEZONE = timezone(timedelta(hours=8))


def _china_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.strftime("%Y-%m-%d %H:%M")
    return value.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M")

MARKET_NAMES = {
    "match_result": "胜平负",
    "handicap_result": "让球胜平负",
    "correct_score": "比分",
    "total_goals": "总进球",
    "half_full": "半全场",
}
OUTCOME_NAMES = {
    "home": "主胜",
    "draw": "平",
    "away": "客胜",
    "H": "主胜",
    "D": "平",
    "A": "客胜",
    "HH": "胜胜",
    "HD": "胜平",
    "HA": "胜负",
    "DH": "平胜",
    "DD": "平平",
    "DA": "平负",
    "AH": "负胜",
    "AD": "负平",
    "AA": "负负",
}


def _play_name(item: Mapping[str, Any]) -> str:
    market = str(item.get("market", "")).strip()
    outcome = str(item.get("outcome", "")).strip()
    if not market and ":" in str(item.get("play", "")):
        market, outcome = str(item["play"]).split(":", 1)
    if market:
        market_name = MARKET_NAMES.get(market, market)
        outcome_name = OUTCOME_NAMES.get(outcome, outcome)
        return f"{market_name} · {outcome_name}" if outcome_name else market_name
    return str(item.get("play", "-"))


def _safe_json(value: Any) -> str:
    """Serialize JSON for an HTML script data block without enabling tag breakout."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_daily_report(
    *, generated_at: datetime, model_state: str,
    candidates: Sequence[Mapping[str, Any]], data_fresh: bool,
    source_as_of: datetime | None = None,
    fixtures: Sequence[Mapping[str, Any]] = (),
) -> str:
    can_recommend = data_fresh and model_state in ALLOWED_RECOMMENDATION_STATES
    report_date = (source_as_of or generated_at).date().isoformat()
    generated_text = _china_time(generated_at)
    source_text = _china_time(source_as_of) if source_as_of else "未提供"
    model_state_text = MODEL_STATE_LABELS.get(model_state, model_state)
    status_title = "数据正常" if data_fresh else "数据过期：建议已隐藏"
    conclusion = (
        f"发现 {len(candidates)} 个通过当前筛选的候选，请结合预算与停售时间人工判断。"
        if candidates and can_recommend
        else "今日无符合标准的正式投注建议。"
    )
    if candidates and not can_recommend:
        conclusion = f"有 {len(candidates)} 个研究候选，但当前仅供观察/模拟，不构成投注建议。"

    display_candidates: list[dict[str, Any]] = []
    rows: list[str] = []
    cards: list[str] = []
    for index, item in enumerate(candidates):
        label = str(item.get("label", "未知比赛"))
        play = _play_name(item)
        probability = float(item.get("probability", 0.0))
        ev = float(item.get("conservative_ev", 0.0))
        odds_value = item.get("decimal_odds")
        odds = float(odds_value) if odds_value is not None else None
        market_value = item.get("market_probability")
        market_probability = float(market_value) if market_value is not None else None
        action = "候选" if can_recommend and ev > 0 else "观察/模拟"
        cutoff = str(item.get("sale_cutoff", "未提供"))
        cutoff_note = "（估算，非官方停售时间）" if item.get("sale_cutoff_estimated") else ""
        odds_text = f"{odds:.2f}" if odds is not None else "暂无"
        market_text = f"{market_probability:.1%}" if market_probability is not None else "暂无"
        safe_label, safe_play = html.escape(label), html.escape(play)
        safe_cutoff = html.escape(cutoff)
        rows.append(
            f"<tr><th scope='row'>{safe_label}</th><td>{safe_play}</td>"
            f"<td>{probability:.1%}</td><td>{odds_text}</td><td>{ev:.1%}</td>"
            f"<td>{safe_cutoff}{cutoff_note}</td><td><span class='tag'>{action}</span></td></tr>"
        )
        cards.append(
            f"""<article class="match-card">
<div class="card-top"><span class="rank">#{index + 1}</span><span class="tag">{action}</span></div>
<h3>{safe_label}</h3><p class="play">{safe_play}</p>
<dl><div><dt>模型概率</dt><dd>{probability:.1%}</dd></div>
<div><dt>参考奖金</dt><dd>{odds_text}</dd></div>
<div><dt>市场概率</dt><dd>{market_text}</dd></div>
<div><dt>保守 EV</dt><dd>{ev:.1%}</dd></div></dl>
<p class="cutoff">停售：{safe_cutoff}{cutoff_note}</p></article>"""
        )
        if odds is not None and odds > 1:
            display_candidates.append({
                "id": str(item.get("match_id", index)),
                "label": label,
                "play": play,
                "odds": odds,
            })

    empty = "" if candidates else (
        "<div class='empty'><strong>今日无符合门槛的候选</strong>"
        "<p>这不是系统故障；没有保守正期望机会时，不投注也是正式结论。</p></div>"
    )
    table_body = "".join(rows) or "<tr><td colspan='7'>今日无符合门槛的候选</td></tr>"
    candidate_json = _safe_json(display_candidates)
    fresh_class = "ok" if data_fresh else "danger"
    recommend_class = "" if can_recommend else " research"
    fixture_cards: list[str] = []
    status_labels = {
        "candidate_eligible": "可进入候选筛选",
        "research_observation": "研究观察",
        "data_insufficient": "数据不足",
        "safety_rejected": "安全拒绝",
    }
    coverage = {key: 0 for key in status_labels}
    for fixture in fixtures:
        home = str(fixture.get("display_home_team") or fixture.get("home_team", "主队"))
        away = str(fixture.get("display_away_team") or fixture.get("away_team", "客队"))
        number = str(fixture.get("match_number") or fixture.get("match_num") or fixture.get("match_id", ""))
        competition = str(fixture.get("competition", ""))
        kickoff = str(fixture.get("scheduled_start") or fixture.get("kickoff") or "未提供")
        cutoff = str(fixture.get("sale_cutoff", "未提供"))
        approved_markets = set(fixture.get("approved_markets", ()))
        recommendation_eligible = fixture.get("recommendation_eligible", False) is True
        analysis_status = str(fixture.get("analysis_status", "data_insufficient"))
        analysis_reason = str(fixture.get("analysis_reason", "未提供分析状态"))
        coverage[analysis_status] = coverage.get(analysis_status, 0) + 1
        market_blocks: list[str] = []
        odds_by_market = fixture.get("odds", {})
        if isinstance(odds_by_market, Mapping):
            for market in ("match_result", "handicap_result", "correct_score", "total_goals", "half_full"):
                values = odds_by_market.get(market, {})
                if not isinstance(values, Mapping) or not values:
                    continue
                market_name = MARKET_NAMES.get(market, market)
                if market == "handicap_result":
                    market_name += f"（{int(fixture.get('handicap', 0)):+d}）"
                options = []
                for outcome, odd in values.items():
                    outcome_text = OUTCOME_NAMES.get(str(outcome), str(outcome))
                    if market == "total_goals":
                        outcome_text = f"{outcome}球"
                    options.append(
                        f"<span><b>{html.escape(outcome_text)}</b> {float(odd):.2f}</span>"
                    )
                market_blocks.append(
                    f"<div class='market-row'><strong>{html.escape(market_name)} "
                    f"<em class='market-status {'approved' if market in approved_markets and recommendation_eligible else 'display-only'}'>"
                    f"{'模型已验收' if market in approved_markets and recommendation_eligible else ('输入不足' if market in approved_markets else '仅展示')}</em></strong>"
                    f"<div>{''.join(options)}</div></div>"
                )
        fixture_cards.append(
            f"""<article class="fixture-card"><div class="fixture-head">
<div><b>{html.escape(number)} · {html.escape(competition)}</b>
<h3>{html.escape(home)} <span>vs</span> {html.escape(away)}</h3></div>
<div class="fixture-time">开赛 {html.escape(kickoff)}<br>停售 {html.escape(cutoff)}</div></div>
<p class="hint"><span class="tag">{html.escape(status_labels.get(analysis_status, analysis_status))}</span> {html.escape(analysis_reason)}</p>
<div class="market-list">{''.join(market_blocks) or '<p>暂无在售玩法</p>'}</div></article>"""
        )
    coverage_text = (
        f"官方在售 {len(fixtures)} 场；可进入候选筛选 {coverage['candidate_eligible']} 场；"
        f"研究观察 {coverage['research_observation']} 场；数据不足 {coverage['data_insufficient']} 场；"
        f"安全拒绝 {coverage['safety_rejected']} 场。"
    )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>竞彩概率研究日报 {report_date}</title>
<style>
:root{{--bg:#f4f7fb;--panel:#fff;--text:#172033;--muted:#667085;--line:#e3e8ef;--brand:#155eef;--ok:#087443;--warn:#9a6700;--danger:#b42318}}
html[data-theme="night"]{{--bg:#171716;--panel:#242321;--text:#f5f2eb;--muted:#b5afa4;--line:#45413b;--brand:#e98a4f;--ok:#6ecf9b;--danger:#ff9a8d}}
html[data-theme="blue"]{{--bg:#eef3fa;--panel:#ffffff;--text:#152238;--muted:#60708a;--line:#d6dfec;--brand:#285ea8;--ok:#167a58;--danger:#bb3f3f}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.55}}
.shell{{max-width:1180px;margin:auto;padding:24px}}header{{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}}
.top-nav{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 18px;padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-radius:14px}}.nav-links,.theme-switch{{display:flex;gap:7px;flex-wrap:wrap}}.nav-links a,.theme-switch button{{border:1px solid var(--line);background:transparent;color:var(--text);border-radius:9px;padding:7px 10px;text-decoration:none;font:inherit;font-size:.85rem;cursor:pointer}}.nav-links a:hover,.theme-switch button:hover{{border-color:var(--brand);color:var(--brand)}}
h1{{font-size:clamp(1.55rem,4vw,2.25rem);margin:0}}h2{{font-size:1.2rem;margin:0 0 14px}}h3{{font-size:1rem;margin:8px 0}}p{{margin:.35rem 0}}
.meta,.hint,.cutoff{{color:var(--muted);font-size:.88rem}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:16px;box-shadow:0 3px 12px rgba(16,24,40,.04)}}
.dashboard{{display:grid;grid-template-columns:1.4fr repeat(3,1fr);gap:12px}}.metric{{background:#f8faff;border-radius:12px;padding:14px}}.metric strong{{display:block;font-size:1.25rem}}
.status{{border-left:5px solid var(--ok)}}.status.danger{{border-left-color:var(--danger)}}.research{{background:#fff9e8}}.tag{{display:inline-block;border-radius:99px;padding:3px 9px;background:#e8f0ff;color:#174ea6;font-size:.78rem;font-weight:700}}
.history-alert{{display:none;background:#fff3cd;color:#7a4b00;border-radius:10px;padding:10px 12px;margin-top:12px}}.history-alert.show{{display:block}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:850px}}th,td{{padding:11px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}thead th{{font-size:.82rem;color:var(--muted)}}tbody th{{font-weight:650}}
.cards{{display:none}}.card-top{{display:flex;justify-content:space-between}}.rank{{color:var(--muted);font-size:.82rem}}.play{{color:var(--brand);font-weight:700}}
dl{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:12px 0}}dl div{{background:#f8faff;border-radius:8px;padding:8px}}dt{{font-size:.75rem;color:var(--muted)}}dd{{margin:2px 0 0;font-weight:700}}
.budget-grid{{display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:18px}}label{{font-weight:700}}input{{display:block;width:100%;min-height:44px;margin-top:7px;border:1px solid #98a2b3;border-radius:9px;padding:9px 11px;font:inherit}}input:focus{{outline:3px solid #b9d2ff;border-color:var(--brand)}}
.error{{min-height:1.5em;color:var(--danger);font-size:.88rem}}.results{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}.result{{background:#f8faff;border-radius:10px;padding:10px}}.result strong{{display:block;font-size:1.08rem}}.allocation{{margin-top:12px;padding:0;list-style:none}}.allocation li{{padding:8px 0;border-bottom:1px solid var(--line)}}
.empty{{text-align:center;padding:30px 12px;color:var(--muted)}}footer{{padding:8px 2px 28px;color:var(--muted);font-size:.84rem}}
.fixture-list{{display:grid;gap:12px}}.fixture-card{{border:1px solid var(--line);border-radius:12px;padding:14px}}.fixture-head{{display:flex;justify-content:space-between;gap:16px}}.fixture-head h3 span{{color:var(--muted);font-weight:400}}.fixture-time{{text-align:right;color:var(--muted);font-size:.82rem}}.market-list{{display:grid;gap:7px;margin-top:10px}}.market-row{{display:grid;grid-template-columns:170px 1fr;gap:10px;padding:8px;background:#f8faff;border-radius:8px}}.market-row div{{display:flex;flex-wrap:wrap;gap:6px 14px}}.market-row span{{white-space:nowrap}}.market-status{{display:inline-block;margin-left:4px;border-radius:99px;padding:1px 6px;font-size:.68rem;font-style:normal;font-weight:700}}.market-status.approved{{background:#dcfae6;color:#087443}}.market-status.display-only{{background:#eef2f6;color:#667085}}
details.market-row{{display:block}}details.market-row summary{{cursor:pointer;font-weight:700;list-style:none}}details.market-row summary::-webkit-details-marker{{display:none}}details.market-row summary::after{{content:"展开";float:right;color:var(--muted);font-size:.78rem}}details.market-row[open] summary::after{{content:"收起"}}details.market-row>div{{margin-top:9px}}html[data-view="matches"] main>section:nth-of-type(4),html[data-view="matches"] main>section:nth-of-type(5),html[data-view="matches"] main>section:nth-of-type(6){{display:none}}html[data-view="candidates"] main>section:nth-of-type(3),html[data-view="candidates"] main>section:nth-of-type(6){{display:none}}html[data-view="review"] main>section:nth-of-type(3),html[data-view="review"] main>section:nth-of-type(4),html[data-view="review"] main>section:nth-of-type(5){{display:none}}
@media(max-width:760px){{.shell{{padding:14px}}header{{display:block}}.dashboard{{grid-template-columns:1fr 1fr}}.dashboard .status{{grid-column:1/-1}}.table-wrap{{display:none}}.cards{{display:grid;gap:12px}}.match-card{{border:1px solid var(--line);border-radius:12px;padding:14px}}.budget-grid{{grid-template-columns:1fr}}.results{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{.fixture-head{{display:block}}.fixture-time{{text-align:left;margin-top:6px}}.market-row{{grid-template-columns:1fr}}}}
@media(max-width:360px){{.dashboard,.results{{grid-template-columns:1fr}}.dashboard .status{{grid-column:auto}}}}
</style></head><body><main class="shell">
<header><div><p class="meta">报告日期 {report_date}</p><h1>竞彩决策驾驶舱</h1></div>
<p class="meta">北京时间显示 · 仅供概率研究</p></header>
<nav class="top-nav" aria-label="页面导航"><div class="nav-links"><a href="/jingcai-model/">每日比赛</a><a href="/jingcai-model/candidates/">候选决策</a><a href="/jingcai-model/review/">收益复盘</a></div><div class="theme-switch" aria-label="主题"><button type="button" data-theme="warm">暖白</button><button type="button" data-theme="night">夜间</button><button type="button" data-theme="blue">深蓝</button></div></nav>
<section class="panel dashboard">
<div class="metric status {fresh_class}{recommend_class}"><span>今日结论</span><strong>{html.escape(conclusion)}</strong></div>
<div class="metric"><span>研究候选</span><strong>{len(candidates)} 个</strong></div>
<div class="metric"><span>模型状态</span><strong>{html.escape(model_state_text)}</strong></div>
<div class="metric"><span>数据状态</span><strong>{status_title}</strong></div>
</section>
<section class="panel"><h2>数据状态</h2><p>生成时间：{html.escape(generated_text)}</p>
<p>官方数据时间：{html.escape(source_text)}</p>
<p class="hint">{html.escape(coverage_text)}</p><div id="history-alert" class="history-alert" role="status">你正在查看历史报告，数据和奖金可能已变化，请勿当作今日建议。</div></section>
<section class="panel"><h2>今日全部竞彩比赛</h2>
<p class="hint">以下按竞彩官方中文名称展示全部在售比赛和五类玩法参考奖金；未通过模型验收的玩法只展示，不推荐。</p>
<div class="fixture-list">{''.join(fixture_cards) or '<div class="empty">暂无官方在售比赛</div>'}</div></section>
<section class="panel"><h2>候选详情</h2>{empty}
<div class="table-wrap"><table><thead><tr><th>比赛</th><th>玩法与选择</th><th>模型概率</th><th>参考奖金</th><th>保守 EV</th><th>停售</th><th>状态</th></tr></thead>
<tbody>{table_body}</tbody></table></div><div class="cards">{''.join(cards)}</div></section>
<section class="panel"><h2>模拟总预算试算</h2>
<p class="hint">仅对上方有参考奖金的候选进行等额单关模拟，每注按 2 元整数步长分配。金额只在当前页面内计算，不保存、不上传，也不会自动购票。</p>
<div class="budget-grid"><div><label for="budget">模拟总预算（元）</label><input id="budget" type="number" inputmode="decimal" min="2" step="2" placeholder="例如 100" autocomplete="off">
<p id="budget-error" class="error" role="alert" aria-live="polite"></p></div>
<div><div class="results" aria-live="polite">
<div class="result"><span>实际模拟投入</span><strong id="used">—</strong></div>
<div class="result"><span>未使用零头</span><strong id="unused">—</strong></div>
<div class="result"><span>全错最大损失</span><strong id="loss">—</strong></div>
</div><ul id="allocation" class="allocation"></ul></div></div>
<p class="hint">单项返奖 = 该项模拟投入 × 参考奖金；单项命中时的组合净盈亏 = 该项返奖 − 全部模拟投入。返奖不是利润，且奖金可能在购买前变化。</p>
</section>
<footer>仅供个人概率研究，不保证中奖或盈利；系统不自动投注。未知、过期或未通过验收的数据不会生成正式建议。</footer>
</section>
<section class="panel review-panel"><h2>收益复盘</h2><p class="hint">只有赛前冻结、赛后由官方结果确认的比赛才会计入收益。未结束比赛不会写入 ROI。</p><div class="results"><div class="result"><span>已结算场次</span><strong>等待赛果</strong></div><div class="result"><span>累计 ROI</span><strong>—</strong></div><div class="result"><span>最大回撤</span><strong>—</strong></div></div></section>
</main>
<script id="candidate-data" type="application/json">{candidate_json}</script>
<script>
(()=>{{"use strict";
const reportDate={json.dumps(report_date)}, today=new Intl.DateTimeFormat("en-CA",{{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit"}}).format(new Date());
if(reportDate!==today)document.getElementById("history-alert").classList.add("show");
const candidates=JSON.parse(document.getElementById("candidate-data").textContent);
const savedTheme=localStorage.getItem("jingcai-theme")||"warm";if(savedTheme!=="warm")document.documentElement.dataset.theme=savedTheme;
document.querySelectorAll("[data-theme]").forEach(button=>button.addEventListener("click",()=>{{const theme=button.dataset.theme;document.documentElement.dataset.theme=theme==="warm"?"":theme;localStorage.setItem("jingcai-theme",theme);}}));
document.querySelectorAll(".fixture-card").forEach(card=>{{card.querySelectorAll(".market-row").forEach((row,index)=>{{if(index===0)return;const details=document.createElement("details");details.className="market-row";const title=row.querySelector("strong"),body=row.querySelector("div"),summary=document.createElement("summary");summary.innerHTML=title?title.innerHTML:"玩法赔率";details.append(summary);if(body)details.append(body);row.replaceWith(details);}});}});
const input=document.getElementById("budget"),error=document.getElementById("budget-error"),list=document.getElementById("allocation");
const money=n=>n.toLocaleString("zh-CN",{{minimumFractionDigits:2,maximumFractionDigits:2}});
const set=(id,value)=>document.getElementById(id).textContent=value;
function clear(){{set("used","—");set("unused","—");set("loss","—");list.replaceChildren();}}
function calculate(){{
 error.textContent="";clear();const raw=input.value.trim();if(!raw)return;
 const budget=Number(raw);
 if(!Number.isFinite(budget)||budget<=0){{error.textContent="请输入大于 0 的有效金额。";return;}}
 if(!Number.isInteger(budget)||budget%2!==0){{error.textContent="模拟预算必须是 2 元的整数倍。";return;}}
 if(!candidates.length){{error.textContent="当前没有带参考奖金的候选，无法试算。";return;}}
 const units=Math.floor(budget/2),base=Math.floor(units/candidates.length),extra=units%candidates.length;
 const allocations=candidates.map((item,i)=>({{...item,stake:(base+(i<extra?1:0))*2}})).filter(item=>item.stake>0);
 const used=allocations.reduce((sum,item)=>sum+item.stake,0),unused=budget-used;
 set("used",money(used)+" 元");set("unused",money(unused)+" 元");set("loss","-"+money(used)+" 元");
 for(const item of allocations){{
  const payout=item.stake*item.odds,profit=payout-used,li=document.createElement("li");
  const title=document.createElement("strong"),detail=document.createElement("span");
  title.textContent=item.label+"｜"+item.play;
  detail.textContent="：投入 "+money(item.stake)+" 元；该项命中返奖 "+money(payout)+" 元；组合净盈亏 "+(profit>=0?"+":"")+money(profit)+" 元";
  li.append(title,detail);list.append(li);
 }}
}}
input.addEventListener("input",calculate);
}})();
</script></body></html>"""


def write_report(path: str | Path, content: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def render_probability_report(result: Mapping[str, Any]) -> str:
    titles = {
        "match_result": "胜平负",
        "handicap_result": f"让球胜平负（{int(result.get('handicap', 0)):+d}）",
        "total_goals": "总进球", "correct_score": "比分", "half_full": "半全场",
    }
    sections = []
    for key, title in titles.items():
        ordered = sorted(result.get(key, {}).items(), key=lambda item: item[1], reverse=True)
        rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td>{float(v):.2%}</td></tr>" for k, v in ordered)
        sections.append(f"<section><h2>{title}</h2><table>{rows}</table></section>")
    fixture = f"{result.get('home_team', '')} vs {result.get('away_team', '')}"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>{html.escape(fixture)} 概率研究</title><style>body{{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}.notice{{background:#fff4d6;padding:1rem;border-radius:10px}}.markets{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}}section{{border:1px solid #e0e6ef;border-radius:10px;padding:1rem}}table{{width:100%;border-collapse:collapse}}td{{padding:.45rem;border-bottom:1px solid #eee}}td:last-child{{text-align:right}}</style></head><body>
<h1>{html.escape(fixture)}</h1><div class="notice"><strong>状态：{html.escape(str(result.get('state', 'RESEARCH')))}</strong><br>当前只展示历史模型研究概率，没有可信竞彩奖金时不计算 ROI，也不构成正式投注建议。</div>
<div class="markets">{''.join(sections)}</div><p><small>模型：{html.escape(str(result.get('model', '')))}；生成：{html.escape(str(result.get('generated_at', '')))}</small></p></body></html>"""
