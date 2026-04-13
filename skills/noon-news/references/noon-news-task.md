# 午间新闻任务说明

> 本文档定义「午间新闻」定时任务的运行规范、数据来源和输出格式。

---

## 基本信息

| 字段 | 值 |
|------|-----|
| **任务名称** | daily-hot-news-brief-1230 |
| **Job ID** | [创建 cron 任务后获得] |
| **定时** | `30 12 * * *`（每日 12:30 Asia/Shanghai = 04:30 UTC） |
| **发送目标** | [配置为你的目标群/频道 ID] |
| **模型** | [model] |
| **超时** | 600s |
| **运行状态** | 上次 `ok`（2026-04-13 04:30 UTC） |

---

## 数据来源

任务按以下顺序执行，**必须严格遵守顺序**：

### 1. news-aggregator-skill（优先）

```bash
python3 ~/.openclaw/skills/news-aggregator-skill/scripts/fetch_news.py \
  --source hackernews,github,producthunt,36kr,tencent,weibo,wallstreetcn,v2ex \
  --limit 8
```

覆盖：Hacker News、GitHub Trending、Product Hunt、36kr、腾讯新闻、微博、华尔街见闻、V2EX

### 2. news-summary（RSS）

```bash
# BBC World
curl -s "https://feeds.bbci.co.uk/news/world/rss.xml" | grep -E "<title>|<description>" | sed 's/<[^>]*>//g' | sed 's/^[ \t]*//' | head -30

# The Independent（英国）
curl -s "https://www.independent.co.uk/rss" | grep -E "<title>|<description>" | sed 's/<[^>]*>//g' | sed 's/^[ \t]*//' | head -20

# NPR（美国）
curl -s "https://feeds.npr.org/1001/rss.xml" | grep -E "<title>|<description>" | sed 's/<[^>]*>//g' | sed 's/^[ \t]*//' | head -20

# Al Jazeera（全球南方）
curl -s "https://www.aljazeera.com/xml/rss/all.xml" | grep -E "<title>|<description>" | sed 's/<[^>]*>//g' | sed 's/^[ \t]*//' | head -20
```

### 3. daily-ai-news-skill（补充）

作为第三梯队补充。

### 4. Fallback 搜索

仅当上述 skill 执行失败或返回为空时，才允许用 `web-search-prime + web-reader` 补齐缺口。

---

## 输出格式

使用固定模板 `prompts/news-brief-v1.md`：

### 结构

```
📰 今日热点简报

### 通用区域
**① 国际要闻**
- **English Title**
  （中文短题）
  一句话事实描述（发生了什么）。
  来源 NS·BBC

**② 宏观与商业**
...

### 科技区域
**① AI 主线**
- **English Title**
  （中文短题）
  一句话事实描述。
  来源 DA·TechCrunch
...
```

### 事实写作约束

- 每条最多两行：标题 + 事实句
- 事实句不使用"预计/可能/或将/趋势"等推断词
- 国际要闻必须含可核对实体（主体、动作、时间点至少两项）
- 英文标题中英双行显示：`**English title**` + `（中文短题）`
- 信息不足写「信息有限，待更多来源确认」

### 来源标签规范

| 简写 | 来源 |
|------|------|
| `NS` | news-summary |
| `NA` | news-aggregator-skill |
| `DA` | daily-ai-news-skill |
| `HN` | hn-digest |

格式：`来源 <简写>·<媒体或平台>`

---

## 执行约束（硬约束）

1. **必须先走本地 skills 抓取**，不得先用搜索
2. **最终只发送一次完整简报**，不发送过程日志
3. 汇总后需**去重**（同主题/同事件保留信息最完整一条）
4. 发送必须使用 `message` 工具，参数：
   - `action=send`
   - `channel=[渠道名]`（示例：`feishu`）
   - `target=[你的目标 ID]`
   - `accountId=main`
5. 禁止使用 telegram channel

---

## 故障排查

| 症状 | 可能原因 | 处理方式 |
|------|---------|---------|
| 无输出 | news-aggregator-script 执行失败 | 检查 Python 环境 |
| 缺少国际新闻 | news-summary RSS 全部失败 | 确认网络可访问 BBC/Al Jazeera |
| 内容重复 | 去重逻辑未生效 | 手动检查同主题条目 |
| 发送失败 | 消息平台 API 限流 | 等待后重试 |

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `prompts/news-brief-v1.md` | 输出模板 |
| `skills/news-aggregator-skill/` | 新闻聚合 skill |
| `skills/news-summary/` | RSS 国际新闻 skill |
| `skills/daily-ai-news-skill/` | AI 新闻 skill |

---

## 变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-04-13 | 初始版本，建立午间新闻任务说明文档 |
| 2026-04-13 | 新增 news-summary RSS 抓取（BBC + The Independent + NPR + Al Jazeera） |
