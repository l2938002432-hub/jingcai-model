# 竞彩预测模型

一个以历史样本外验证、概率校准和保守期望收益为核心的足球竞彩研究工具。系统支持本地命令行和静态 HTML 报告；任何玩法只有通过冻结验收协议后才能从研究状态进入模拟建议。

> 本项目用于个人概率研究，不保证中奖或盈利，不自动投注，也不会为了每天有结果而强行推荐。

## 当前阶段

正在建设本地 MVP：数据导入、统一比赛 schema、五类玩法概率、滚动回测和 PAPER_ONLY 报告。云端定时、EdgeOne、飞书与微信推送在本地闭环通过后接入。

## 快速检查

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m jingcai status
python -m jingcai demo-report --output reports\demo.html
python -m jingcai predict --csv path\to\league.csv --season 2025-26 --home "Home" --away "Away" --output reports\prediction.html
python -m jingcai serve --directory reports
python -m jingcai daily-paper --csv path\to\league.csv --season 2025-26 --fixtures-json config\daily-fixtures.example.json --output reports\daily-paper.html
```

完整设计见 `docs/superpowers/specs/2026-07-22-jingcai-prediction-system-design.md`，实施计划见 `docs/superpowers/plans/2026-07-22-jingcai-implementation-plan.md`。

真实历史基线结果见 `docs/validation/epl-baseline-2020-2026.md`。当前基础模型在英超六赛季的 1,520 场样本外预测中，Log Loss 相对历史频率基线改善约 6.2%，但尚未获得可信中国竞彩历史奖金，不能宣称已验证盈利。
