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
```

完整设计见 `docs/superpowers/specs/2026-07-22-jingcai-prediction-system-design.md`，实施计划见 `docs/superpowers/plans/2026-07-22-jingcai-implementation-plan.md`。

