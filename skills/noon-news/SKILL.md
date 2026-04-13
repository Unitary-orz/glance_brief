---
name: noon-news
description: >-
  每日午间热点简报定时任务 Skill。
  综合多 news skills 输出「📰 今日热点简报」，发送飞书群。
  使用 when: 用户要求查看今日新闻、热点简报、午间新闻。
---

# noon-news

每日午间热点简报（📰 今日热点简报）。

## 定时任务

- **Job ID：** `d37a6348-0322-433c-bf41-36176e169fab`
- **定时：** 每日 12:30 Asia/Shanghai（`30 12 * * *`）
- **发送目标：** 飞书群 `oc_76b918a1da88e33c679d6543d1ebfbe7`

## 数据来源（执行顺序，必须严格遵守）

### 1. news-aggregator-skill（优先）

```bash
python3 ~/.openclaw/workspace-lionclaw/skills/news-aggregator-skill/scripts/fetch_news.py \
  --source hackernews,github,producthunt,36kr,tencent,weibo,wallstreetcn,v2ex --limit 8
```

### 2. news-summary RSS（补充）

```bash
# BBC World
curl -s "https://feeds.bbci.co.uk/news/world/rss.xml" | ...
# The Independent
curl -s "https://www.independent.co.uk/rss" | ...
# NPR
curl -s "https://feeds.npr.org/1001/rss.xml" | ...
# Al Jazeera
curl -s "https://www.aljazeera.com/xml/rss/all.xml" | ...
```

### 3. daily-ai-news-skill（如可用）

仅在前两者失败或内容不足时 fallback 使用。

### 4. 搜索补齐（如仍有缺口）

仅当某个 skill 执行失败或返回为空时，才允许使用 `agent-reach` 搜索补齐。

## 输出格式

固定标题：**📰 今日热点简报**

```
## 📰 今日热点简报

### 通用区域 General
**① 国际要闻**
  - **标题**
    一句话事实描述。
    `来源 NS·BBC`

**② 宏观与商业**
  ...

### 科技区域 Tech
**① AI 主线**
  ...
**② 平台与产品**
  ...
**③ 开发者与生态**
  ...
```

## 写作约束

- 每条最多两行：标题 + 事实句
- 事实句不使用"预计/可能/或将/趋势"等推断词
- 信息不足必须写：信息有限，待更多来源确认
- 每条都带来源标签（NS/NA/DA/HN）

## 详细文档

见 `references/noon-news-task.md`
