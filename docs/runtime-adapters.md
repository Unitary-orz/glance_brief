# Runtime Adapters

## 原则

Skill 和预取脚本不保存运行时状态。运行时 adapter 才提供：

- 脚本实际路径
- 外部 Skill 路径
- 本地配置路径
- Cron schedule
- 模型和投递目标

## Hermes

参考 `adapters/hermes/`：

- Job 脚本使用 `skills/agents-report/scripts/agents_radar_prefetch.py` 和 `skills/noon-news/scripts/noon_news_prefetch.py`
- `CODEXRADAR_CONFIG` 指向 Hermes data 下的用户配置
- `AGENTS_RADAR_OUTPUT_DIR` 指向 Hermes data 下的输出目录
- `NEWS_AGGREGATOR_SCRIPT` 和 `NEWS_SUMMARY_SCRIPT` 指向已安装 Skill

## OpenClaw

参考 `adapters/openclaw/`：

- 使用项目中对应 Skill 的脚本路径
- 通过环境变量提供 OpenClaw workspace 下的外部 Skill 路径
- 不把 `/root/.openclaw` 写入业务脚本

## 配置边界

可以提交：

- `*.example.json`
- `*.example.env`
- 不含真实目标的 Cron 模板

不能提交：

- 真实聊天 ID
- 真实 Job ID
- API key、token、密码
- 本地生成报告
- 用户私有模型配置
