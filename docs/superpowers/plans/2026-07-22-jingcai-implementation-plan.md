# 竞彩预测系统实施计划

## 目标

先交付一个可运行、可测试、可回放的本地 MVP：导入免费历史比赛数据，完成统一 schema、时点校验、Dixon–Coles/Elo 基线、五类玩法概率、滚动回测、盈利候选筛选、CLI 与本地报告。云端和推送在本地闭环验证后接入。

## 开发原则

- 测试先行；每个模块先建立失败样例再实现。
- 所有输入必须带时点，任何未来信息触发硬失败。
- 模型结果必须与基线同窗比较，不以训练集效果验收。
- 免费、无需密钥的离线样例必须能完整运行。
- 正式仓库位于 `D:\Codex-Workspace\03_Projects\P003_JingCaiModel`；当前工作目录作为受限环境下的编辑镜像，每个提交后同步并校验 Git SHA。

## 工作包 1：工程骨架与领域 schema

负责人：总设计师集成，工程 Agent 实现。

交付：

- `pyproject.toml`、包结构、pytest/ruff 配置。
- 比赛、球队、赛事、赔率快照、停售时间、预测、票据、结算的 Pydantic/dataclass schema。
- UTC 存储与北京时间展示工具。
- `event_time <= retrieved_at <= prediction_created_at <= sale_cutoff` 校验。

验收：schema round-trip、非法时间链、玩法级停售、幂等键均有测试。

## 工作包 2：数据适配与本地存储

负责人：数据 Agent。

交付：

- Football-Data CSV 适配器和稳定的本地 fixture。
- 竞彩网 provider 接口、人工 JSON/CSV 导入兜底；网络抓取作为可选插件，不进入离线 CI。
- 队名别名、三重赛事匹配、歧义拒绝。
- DuckDB/Parquet 存储接口；若 DuckDB 不可用则测试使用内存仓储。
- provider registry 与数据 manifest。

验收：重复、时区、改期、歧义、缺字段、快照哈希和幂等写入测试通过。

## 工作包 3：玩法规则与结算

负责人：回测 Agent。

交付：

- 胜平负、让球胜平负、比分/其他、总进球封顶档、半全场九类映射。
- 单关票据、奖金、取消/返还、规则版本。
- 两串一接口和联合概率占位；未验证前保持禁用。

验收：概率非负且和为 1；比分聚合与派生玩法一致；官方规则固定样例可重放。

## 工作包 4：模型与概率校准

负责人：模型 Agent。

交付：

- 简单联赛频率、Poisson、动态 Elo 基线。
- 时变 Dixon–Coles 训练与 0–10 球联合矩阵。
- 比例去水与幂法敏感性接口。
- 校准器严格使用晚于训练窗的数据。
- 半全场初版联合模型。

验收：可重复训练；无 NaN/负概率；新队收缩；比分尾部质量守恒；校准数据隔离测试。

## 工作包 5：滚动回测与盈利组合

负责人：回测 Agent，模型 Agent 复核。

交付：

- development walk-forward、calibration、lockbox 三段协议。
- Log Loss、Brier、RPS、校准摘要。
- 使用可信奖金样本计算净利润、ROI、最大回撤、最长连败。
- 比赛日 block bootstrap 置信区间。
- 固定单位与 1/8 Kelly 模拟；约束日/场/联赛暴露。
- `RESEARCH/PAPER_ONLY/LIMITED_LIVE/LIVE/PAUSED` 输出状态。

验收：未来数据注入测试必须失败；无官方时点奖金时禁止输出“竞彩 ROI”；没有正保守 EV 时输出空组合。

## 工作包 6：CLI、HTML 与本地网页

负责人：工程 Agent，总设计师做体验验收。

交付：

- `python -m jingcai import-history`、`train`、`backtest`、`daily-report`、`serve`。
- Jinja2 静态报告，显示数据时点、模型状态、概率、市场基线、保守 EV、风险和不推荐原因。
- Streamlit 可选本地页面；未安装时 CLI 仍完整可用。

验收：固定 fixture 从导入到报告端到端通过；过期数据隐藏建议；PAPER_ONLY 只显示虚拟票。

## 工作包 7：自动化与通知

在本地 MVP 通过后实施：

- GitHub Actions 离线测试和定时工作流。
- 飞书机器人主通道；企业微信或 Server酱辅助。
- EdgeOne 脱敏静态站发布说明。
- 配额 80%/95% 保护、幂等重试和本地接管。

此工作包需要用户提供对应账号/webhook 才能做真实发送验收；无凭据时使用 mock notifier 验证。

## 提交与集成顺序

1. `build: scaffold project and schemas`
2. `feat: add historical data and identity pipeline`
3. `feat: implement market rules and settlement`
4. `feat: add baseline probability models`
5. `feat: add walk-forward evaluation and portfolio selection`
6. `feat: add cli and local reports`
7. `ci: add quality gates and scheduled workflow`

每个提交必须通过 `pytest` 和 `ruff check`；缺少可选依赖时需明确跳过原因，不能静默失败。
