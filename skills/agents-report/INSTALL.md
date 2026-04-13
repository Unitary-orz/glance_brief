# agents-report 安装配置

## 环境要求

- Python 3
- RSS 抓取依赖：`pip install feedparser requests`（或参考 `scripts/agents-radar-daily.py` 顶部的 import）

## 定时任务配置

### 1. Cron Job 模板

```json
{
  "id": "[创建后获得的 Job ID]",
  "name": "agents-report",
  "enabled": true,
  "description": "每日 OpenClaw 生态报告",
  "schedule": {
    "kind": "cron",
    "expr": "0 10 * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "model": "minimax-cn/MiniMax-M2.5",
    "timeoutSeconds": 600,
    "message": "[见下方 prompt 模板]"
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "[你的飞书群 ID]",
    "accountId": "main"
  }
}
```

### 2. 关键配置字段说明

| 字段 | 说明 |
|------|------|
| `sessionTarget: "isolated"` | 必须在独立会话运行，否则被主会话历史卡住 |
| `wakeMode: "now"` | 定时触发后立即执行 |
| `model` | 推荐 `minimax-cn/MiniMax-M2.5`，可根据需要调整 |
| `timeoutSeconds` | 建议 600s，RSS 抓取+格式化约需 3-5 分钟 |
| `delivery.to` | 飞书群 ID（以 `oc_` 开头），或用户 open_id（以 `ou_` 开头） |

### 3. Prompt 模板

从 `references/agents-radar-daily-ops.md` 中获取最新的 prompt 模板，替换 `[日期]` 为实际日期后填入。

## 故障排查

- **任务卡住不结束**：检查是否缺少 `sessionTarget: "isolated"`
- **发送失败**：确认 `delivery.to` 为正确的飞书群 ID，且 bot 已加入该群
- **RSS 获取失败**：检查网络连接，或手动运行 `python3 scripts/agents-radar-daily.py` 验证
