# 竞彩预测系统实施计划

> 2026-07-26 更新：原工作包 1–7 已完成大部分基础能力。本轮按下述工作包 8–14 实现已批准的产品闭环。未通过票型规则和结算验收的功能只能展示为研究/模拟，不得提前开放为建议。

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

## 工作包 8：冻结发布与双账本底座

目标：先建立可重放事实源，再让页面、推送和结算消费同一发布。

文件：

- 修改 `src/jingcai/domain.py`
- 修改 `src/jingcai/storage.py`
- 新增 `src/jingcai/ledger.py`
- 新增 `tests/test_ledger.py`
- 扩展 `tests/test_storage.py`

步骤：

1. 为 Release、账本事件、成交确认和赛果修订增加强类型领域对象。
2. 为 JSONL 存储增加前序哈希、内容哈希、序号和全链验证。
3. 增加 `append_once` 幂等写入；相同键不同内容必须报冲突。
4. 实现模型账本和个人账本的事件白名单及隔离。
5. 实现更正只追加、禁止原地修改的测试。

验收：

- 删行、换序、篡改内容均被检测；
- 同一发布重复运行返回同一事件；
- 个人事件不能改变模型发布；
- 旧 v1 文件只读迁移，不原地改写。

## 工作包 9：票据、组合优化与奖金分布

目标：用官方合法子票表达单关、2串1和容错票，给出可复算的预算和奖金区间。

文件：

- 修改 `src/jingcai/domain.py`
- 新增 `src/jingcai/portfolio.py`
- 修改 `src/jingcai/settlement.py`
- 修改 `src/jingcai/backtest.py`
- 新增 `tests/test_portfolio.py`
- 新增 `tests/test_backtest_tickets.py`
- 扩展结算测试

步骤：

1. 保留 `Ticket` 作为单张合法子票，增加 `TicketBundle` 和奖金分布领域对象。
2. 容错过关展开成多张子票，不创建虚构票型。
3. 实现2元粒度预算分配；70/20/10是上限，候选不足保留现金，只允许高风险桶向单关转移。
4. 实现“独立乘积基线 + 冻结相关性扣减”的联合概率；证据不足失败关闭。
5. 枚举互斥赛果状态，逐票舍入后汇总离散返奖分布。
6. 输出返奖概率、保本概率、盈利概率、期望净利润、90%区间和尾部损失。
7. 增加单腿概率门、联合概率门、票型规则门、组合经济门。
8. 按实际 stake/payout 序列回测 ROI 和峰值回撤。

验收：

- 单关、2串1、3选2容错的子票数量正确；
- 预算永不超支，金额均满足规则粒度；
- 奖金状态概率和为1，上下界和EV与手算金丝雀一致；
- 一腿取消、全取消、延期、退款和逐票舍入正确；
- 组合不能绕过单玩法验收门。

## 工作包 10：公开投影与完整中文数据

目标：Pages、飞书和微信消费相同的脱敏发布投影，中文名称可与竞彩界面直接对应。

文件：

- 新增 `src/jingcai/projections.py`
- 修改 `src/jingcai/pipeline.py`
- 修改 `src/jingcai/__main__.py`
- 新增 `tests/test_projections.py`
- 扩展 pipeline/CLI 测试

步骤：

1. 候选增加赛事中文名、周编号、开赛时间、中文玩法和中文选择。
2. 机器可读 manifest 包含全部官方比赛、五玩法开售状态、合格建议和拒绝原因。
3. 公开 DTO 采用白名单，只允许官方比赛、模型账本聚合、release ID/hash。
4. 私人 DTO 只用于本机，不进入公开构建或通知。

验收：

- 内部枚举不直接出现在用户界面；
- 未映射球队和未验收玩法不能进入建议；
- 注入个人字段后公开 DTO 仍无泄漏；
- manifest 中的建议与冻结 release 完全一致。

## 工作包 11：中文响应式面板与模拟预算

目标：实现已批准的“驾驶舱 + 完整表格 + 手机卡片”组合页面。

文件：

- 重构 `src/jingcai/reporting.py`
- 扩展 `tests/test_reporting.py`
- 新增浏览器验收 fixture/脚本

步骤：

1. 首页显示今日结论、建议、回避原因、模型状态、昨日模型结算和数据时点。
2. 完整比赛页展示周编号、赛事、主客队、停售和五类中文玩法。
3. 手机端逐场卡片，次要玩法折叠，关键停售与建议保持可见。
4. 公开页预算计算只存浏览器内存，支持总预算和分桶微调。
5. 即时显示实际可用金额、未用余额、返奖上下限、净盈亏、保本/盈利概率和回撤警告。
6. 无建议、数据过期、部分玩法失败、待结算和历史报告各有独立状态。

验收：

- 320、390、768和1440宽度无页面级横向溢出；
- 输入空值、负数、小数、超限和赔率变化均正确阻止确认；
- 触控目标不少于44px，键盘可完成试算；
- 长中文队名和10场以上比赛可读；
- 页面中不存在密钥、原始快照路径或个人字段。

## 工作包 12：本机个人账本与自动结算

目标：允许用户记录真实票据，次日自动显示真实盈亏，同时不污染模型验收。

文件：

- 新增 `scripts/settle_ledgers.py`
- 增加本机私密账本页面/CLI
- 修改 `.gitignore`
- 新增 `tests/test_settlement_replay.py`

步骤：

1. 本机确认逐腿成交奖金、票型、注数、倍数和实付金额。
2. 快照过期、已停售或数据冲突时禁止保存为已购。
3. 获取权威赛果；冲突只进入人工复核。
4. 分别重放模型与个人账本。
5. 赛果更正产生冲销和替代结算事件。
6. 输出昨日投入、返奖、净盈亏、本金、累计ROI、当前/最大回撤和未结算暴露。

验收：

- 模型与个人账本指标分开；
- 缺失、延期和冲突不计作亏损；
- 重复结算不重复入账；
- 个人文件被 Git 和公开构建排除。

## 工作包 13：详细推送与稳定历史深链

目标：让飞书和个人微信消息可直接用于查看当天结论，并保留历史日报。

文件：

- 修改 `scripts/daily_cloud_run.py`
- 新增 `scripts/build_public_site.py`
- 修改 `.github/workflows/daily.yml`
- 扩展通知、云运行和站点测试

步骤：

1. 推送包含中文比赛、玩法、选择、奖金、概率、EV、停售、风险、模型账本结算和历史链接。
2. 飞书与PushPlus逐通道去重；失败隔离。
3. 建立 `/reports/YYYY-MM-DD/{release_id}/` 历史深链和最新首页。
4. 构建脚本仅复制公开白名单产物。
5. 建立免费且可回溯的公开历史分支；模型私密账本仍以本机为权威，不把Actions缓存冒充永久账本。

验收：

- Pages和推送引用同一release；
- 旧消息始终打开原日期版本；
- 无建议和暂停状态不发送旧建议；
- 一个通道失败不会重复发送成功通道；
- 公开目录扫描无secret和个人字段。

## 工作包 14：预测准确率、组合策略和最终验收

目标：在不降低门槛、不泄漏未来信息的前提下持续提高预测和风险调整收益。

步骤：

1. 先保存当前冠军模型和冻结基线。
2. 对可用联赛逐一评估时间衰减、Elo/Dixon–Coles集成、市场概率集成和概率校准。
3. 对新增特征执行时间外消融；停售后首发不得进入赛前特征。
4. 对单关、2串1、容错和70/20/10分别做相同窗口回测。
5. 异常风险规则只保留在新时间外样本中复现的信号。
6. 报告Log Loss、Brier、ECE、ROI、置信区间、最大回撤、最长连败和分层稳定性。
7. 跑官方快照→发布→页面/推送→赛果→结算→更正的完整回放。
8. 完成一次真实云任务、两通道测试消息、Pages HTTP/浏览器和本地私密账本验收。

晋级规则：

- 没有可信历史竞彩时点奖金时，只验收概率，不宣称竞彩盈利；
- 未达到玩法门槛继续 `RESEARCH`；
- 概率门通过但盈利证据不足保持 `PAPER_ONLY`；
- 只有独立经济价值门和10%回撤约束同时通过，才建议用户另行批准 `LIMITED_LIVE`；
- 功能完成与盈利证明分开报告。

## 本轮提交顺序

1. `feat: add immutable release and ledger events`
2. `feat: add ticket portfolio and payout distributions`
3. `feat: add public release projections`
4. `feat: redesign Chinese daily dashboard`
5. `feat: add private wager ledger and settlement replay`
6. `feat: publish detailed notifications and report history`
7. `test: validate portfolio, privacy and end-to-end replay`
8. `docs: record validation results and remaining model gates`
