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
python -m jingcai fetch-today

# 联网读取官方数据、严格校验新鲜度和球队覆盖后生成实时报告
python -m jingcai daily-live --csv path\to\league.csv --season 2025-26 --output reports\daily-live.html

# 叠加多联赛冷启动历史与显式中英文球队映射
python -m jingcai daily-live --csv data\raw\football-data\E0_2025-26.csv --season 2025-26 `
  --club-history-csv data\raw\club-history\Matches.csv --history-divisions BRA,NOR,USA `
  --aliases-json config\team-aliases.json --output reports\daily-live.html

# 无网络时重放已保存的官方原始快照（仍执行过期校验）
python -m jingcai daily-live --csv path\to\league.csv --season 2025-26 --snapshot-json data\snapshots\sporttery-latest.json
python -m jingcai demo-report --output reports\demo.html
python -m jingcai predict --csv path\to\league.csv --season 2025-26 --home "Home" --away "Away" --output reports\prediction.html
python -m jingcai serve --directory reports
python -m jingcai daily-paper --csv path\to\league.csv --season 2025-26 --fixtures-json config\daily-fixtures.example.json --output reports\daily-paper.html
```

`fetch-today` 低频读取中国体育彩票移动端计算器使用的公开数据接口，保存原始快照与规范化五玩法数据。数据源无公开稳定性承诺；接口异常、字段变化或数据过期时必须停止推荐并退回人工导入。海外云机房可能被地域/WAF限制，自动任务优先运行在国内网络或国内云节点。

`daily-live` 遇到快照超过默认 30 分钟或官方更新时间异常时会拒绝整份报告；历史模型未覆盖的单场比赛会被跳过，只有经过显式球队别名匹配且有历史覆盖的比赛才参与计算。当前接口没有提供可信的官方停售字段，因此报告中的停售时间按开赛前 10 分钟估算并明确标记，实际操作必须以销售终端为准。

实时竞彩采集与字段解析参考 MIT 项目 [Johnserf-Seed/SportteryAPI](https://github.com/Johnserf-Seed/SportteryAPI)，项目内实现为独立 Python 提供器。

完整设计见 `docs/superpowers/specs/2026-07-22-jingcai-prediction-system-design.md`，实施计划见 `docs/superpowers/plans/2026-07-22-jingcai-implementation-plan.md`。

真实历史基线结果见 `docs/validation/epl-baseline-2020-2026.md`。当前基础模型在英超六赛季的 1,520 场样本外预测中，Log Loss 相对历史频率基线改善约 6.2%，但尚未获得可信中国竞彩历史奖金，不能宣称已验证盈利。
