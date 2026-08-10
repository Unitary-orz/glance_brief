---
name: noon-news
description: >-
  每日午间热点简报 Skill。
  预取多源新闻和 AI HOT 数据，按固定模板生成可追溯简报；
  来源以引用块单独一行呈现，链接可点击、不显示 URL 明文。
triggers:
  - noon-news
  - 今日热点简报
  - 午间新闻
  - 今日新闻
---

# noon-news

## 运行入口

```bash
python3 skills/noon-news/scripts/noon_news_prefetch.py
```

脚本输出一个 `schema_version: 1` 的 JSON，供 Prompt 格式化。它不会发送消息。

## 数据来源

按当前配置预取：

1. news-aggregator
2. news-summary RSS
3. AI HOT public API

外部脚本通过环境变量指定，不写死 OpenClaw 或 Hermes 路径。

## Prompt

当前格式契约见：

```text
prompts/news-brief-v2.md
```

特别注意：来源单独一行用引用块（`> 来源：`），不并入事实描述行；链接以 Markdown 嵌入、正文不显示 URL 明文。来源链接文字内冒号替换为 `•`（内容保留）、`公众号` 统一替换为 `WX`；所有来源用 `•` 连接，同渠道去重（渠道只写一次），每条最多 2 个渠道，超过时只保留前 2 个并加 `+N`。只增加链接时不得改动标题、章节或换行结构。完整规则以 `news-brief-v2.md` 为唯一格式来源。

## 失败处理

- 单个来源失败：保留其他可用来源，并在数据中保留失败状态。
- 所有来源失败：输出固定失败提示。
- 内容不足：少报或省略，不用无关来源凑数。
