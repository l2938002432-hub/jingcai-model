# 每日自动运行与推送

## 免费云端：GitHub Actions

`Daily Sporttery Feed` 每天北京时间 10:25 尝试读取当天官方在售数据，保存审计快照，并向飞书和企业微信群机器人推送摘要，也可在 Actions 页面手动运行。

在仓库 `Settings > Secrets and variables > Actions` 中按需新增 `FEISHU_WEBHOOK_URL`、`WECOM_WEBHOOK_URL`、`SERVERCHAN_SENDKEY` 和 `PUSHPLUS_TOKEN`。不配置就跳过该渠道。Webhook、SendKey 和 Token 都是密码，不可写入代码、日志或普通变量。产物保留 30 天。GitHub 定时任务可能延迟，海外运行器也可能无法稳定访问国内官方接口，因此这是免费尝试节点，不是可用性保证。

个人微信使用 [Server酱 Turbo](https://sct.ftqq.com/docs/getting-started/sendkey/)：微信扫码登录后取得 SendKey，保存为 `SERVERCHAN_SENDKEY`。免费额度目前每天 5 条，任务把摘要合并成每天一条；SendKey 泄露后应立即重置。

若 Server酱网络不稳定，个人微信优先使用 [PushPlus](https://www.pushplus.plus/doc/guide/api.html)：微信扫码登录并关注其公众号，在个人中心复制 Token，保存为 `PUSHPLUS_TOKEN`。系统会把它作为独立通道发送并单独去重；Token 泄露后应立即在 PushPlus 关闭或重置。

## 国内稳定后备：Windows 任务计划程序

国内常开电脑无需科学上网。先在项目目录手动验证：

```powershell
$env:PYTHONPATH = "src"
$env:FEISHU_WEBHOOK_URL = "你的飞书机器人地址"
$env:WECOM_WEBHOOK_URL = "你的企业微信机器人地址"
$env:SERVERCHAN_SENDKEY = "你的 Server酱 SendKey"
$env:PUSHPLUS_TOKEN = "你的 PushPlus Token"
python scripts\daily_cloud_run.py
```

验证后可创建每天 10:25、失败后每 15 分钟重试两次的 Windows 定时任务。Webhook 应由用户级环境变量或仅本人可读的本地配置注入，不要提交 `.env`。创建系统级任务属于持久化修改，必须得到用户明确批准。

当前任务只完成真实数据获取、留档和赛程摘要推送；只有当模型覆盖当日联赛且通过验收门槛后，才可加入 PAPER_ONLY 候选。不得因当天没有候选而强行推荐。
