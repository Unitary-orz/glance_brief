# noon-news 安装配置

## 环境要求

- Python 3
- 依赖 skills：
  - `news-aggregator-skill`（优先数据源）
  - `news-summary`（RSS 补充）
  - `daily-ai-news-skill`（fallback）
  - `agent-reach`（搜索补齐用）

## 定时任务配置

### 1. Cron Job 模板

```json
{
  "id": "[创建后获得的 Job ID]",
  "name": "noon-news",
  "enabled": true,
  "description": "每日午间热点简报",
  "schedule": {
    "kind": "cron",
    "expr": "30 12 * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "model": "minimax-cn/Miniimax-M2.5",
    "timeoutSeconds": 600,
    "message": "[见 references/noon-news-task.md 中的 prompt 模板]"
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
| `sessionTarget: "isolated"` | 必须在独立会话运行，避免被主会话历史卡住 |
| `wakeMode: "now"` | 定时触发后立即执行 |
| `model` | 推荐 `minimax-cn/MiniMax-M2.5` |
| `timeoutSeconds` | 建议 600s，综合多源约需 5-8 分钟 |
| `delivery.to` | 飞书群 ID（以 `oc_` 开头），或用户 open_id（以 `ou_` 开头） |

### 3. Prompt 模板

从 `references/noon-news-task.md` 中获取最新的 prompt 模板。

## 故障排查

- **某数据源失败**：系统设计为多源 fallback，单个源失败不影响整体输出
- **发送失败**：确认 `delivery.to` 为正确的飞书群 ID，且 bot 已加入该群
- **内容过短**：检查各依赖 skill 是否正常安装，网络是否通畅
