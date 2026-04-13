# noon-news 安装配置

## 环境要求

- Python 3
- 依赖 skills（通过 clawhub 安装）：
  - `news-aggregator-skill`（优先数据源）
  - `news-summary`（RSS 补充）
  - `daily-ai-news-skill`（fallback）
  - `agent-reach`（搜索补齐用）

安装示例：
```bash
clawhub install news-aggregator-skill
clawhub install news-summary
clawhub install daily-ai-news-skill
```

## 定时任务配置

### Cron 模板

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
    "model": "[model]",
    "timeoutSeconds": 600,
    "message": "【定时播报任务｜每日12:30｜硬约束执行】\n目标：输出一条「📰 今日热点简报」，综合多 news skills 结果后发送至配置的消息渠道。\n\n【执行顺序（必须严格遵守）】\n1) 必须先走本地 news skills 抓取（不得先用搜索）：\n   - 优先：python3 ~/.openclaw/skills/news-aggregator-skill/scripts/fetch_news.py --source hackernews,github,producthunt,36kr,tencent,weibo,wallstreetcn,v2ex --limit 8\n   - 补充 RSS：\n     curl -s \"https://feeds.bbci.co.uk/news/world/rss.xml\" | grep -E \"<title>|<description>\" | sed 's/<[^>]*>//g' | sed 's/^[ \\t]*//' | head -30\n     curl -s \"https://www.independent.co.uk/rss\" | grep -E \"<title>|<description>\" | sed 's/<[^>]*>//g' | sed 's/^[ \\t]*//' | head -20\n     curl -s \"https://feeds.npr.org/1001/rss.xml\" | grep -E \"<title>|<description>\" | sed 's/<[^>]*>//g' | sed 's/^[ \\t]*//' | head -20\n     curl -s \"https://www.aljazeera.com/xml/rss/all.xml\" | grep -E \"<title>|<description>\" | sed 's/<[^>]*>//g' | sed 's/^[ \\t]*//' | head -20\n   - 如可用，再补充：daily-ai-news-skill\n2) 仅当某个 skill 执行失败或返回为空时，才允许对缺口使用 fallback 搜索（agent-reach）补齐。\n3) 汇总所有来源后去重（同主题/同事件保留信息最完整一条），按模板生成最终简报。\n4) 最终只发送一次完整简报，不发送过程日志。\n\n【格式要求】\n- 标题固定：📰 今日热点简报\n- 使用 skills/noon-news/prompts/news-brief-v1.md 结构\n- 英文标题中英双行：`**English title**` + `（中文短题）`\n- 每条带来源标签（NS/NA/DA/HN）\n\n【结构】\n📰 今日热点简报\n\n### 通用区域\n**① 国际要闻**\n- **English Title**\n  （中文短题）\n  一句话事实描述。\n  来源 NS·BBC\n\n**② 宏观与商业**\n...\n\n### 科技区域\n**① AI 主线**\n- **English Title**\n  （中文短题）\n  一句话事实描述。\n  来源 DA·TechCrunch\n...\n\n【来源简写】\n- NS = news-summary\n- NA = news-aggregator-skill\n- DA = daily-ai-news-skill\n- HN = hn-digest\n\n【发送约束】\n- 使用 message 工具：action=send, channel=[渠道名], target=[你的目标 ID], accountId=main\n- 禁止使用 telegram channel\n- 不要附加流程说明"
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "[你的目标 ID]",
    "accountId": "main"
  }
}
```

### 关键配置说明

| 字段 | 说明 |
|------|------|
| `sessionTarget: "isolated"` | 必须在独立会话运行，避免被主会话历史卡住 |
| `wakeMode: "now"` | 定时触发后立即执行 |
| `model` | 推荐 `[model]` |
| `timeoutSeconds` | 建议 600s，综合多源约需 5-8 分钟 |
| `delivery.to` | 目标平台的频道 ID（如飞书群 `oc_xxx`、Telegram `@channel` 等） |

## 故障排查

| 症状 | 可能原因 | 处理 |
|------|---------|------|
| 无输出 | news-aggregator-script 执行失败 | 检查 Python 环境 |
| 缺少国际新闻 | news-summary RSS 全部失败 | 确认网络可访问 BBC/Al Jazeera |
| 内容重复 | 去重逻辑未生效 | 确认去重步骤已执行 |
| 发送失败 | 消息平台 API 限流 | 等待后重试 |

## 相关文件

| 文件 | 说明 |
|------|------|
| `prompts/news-brief-v1.md` | 输出模板（固定格式） |
| `references/noon-news-task.md` | 完整运行规范（参考） |
