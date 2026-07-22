# Project Memory

## Durable decisions

- 正式目录：`D:\Codex-Workspace\03_Projects\P003_JingCaiModel`。
- 免费运行：GitHub Actions + EdgeOne Pages，Windows 本地运行作为备用。
- 中国竞彩网是受注赛事、固定奖金和赛果的权威口径；第三方站点只作交叉核验。
- 历史训练采用严格时间滚动与一次性 lockbox；无可信官方历史奖金时不宣称竞彩 ROI。
- 主目标是在风险约束下最大化保守预期净利润，不以命中率单独选模。
- 五天线上阶段只验收工程链路，不证明长期盈利。
- 停售后公布的首发不得回填赛前预测。
- 模型状态：RESEARCH、PAPER_ONLY、LIMITED_LIVE、LIVE、PAUSED/ROLLED_BACK。
- 2026-07-22 核验竞彩网 `robots.txt`：禁止自动访问 `.js` 与 `.json`；官方页面数据依赖动态请求，因此生产版保持官方赛事/奖金人工导入，除非未来取得公开授权接口。
- 英超 2020–21 至 2025–26 共 2,280 场真实回测：后 1,520 场样本外 Dixon–Coles Log Loss 1.0037，对比历史频率 1.0701；Brier 0.5992，对比 0.6475。该结果证明概率基线有效，不证明竞彩盈利。
