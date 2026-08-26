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
3. AI HOT v1 全局精选（`/api/v1/items`，默认 `mode=selected&window=24h&by=timeline`）

AI HOT 条目使用 v1 字段：媒体名取 `source.name`，原文链接取 `links.original`，AI HOT 链接取 `links.aihot`；分页信息取 `page.count`、`page.hasMore` 和 `page.nextCursor`。

外部脚本通过环境变量指定，不写死 OpenClaw 或 Hermes 路径。

## Prompt

当前 V1 可见格式与独立 V2 语义契约分别见：

```text
prompts/news-brief-v2.md
v2/prompts/noon-news.md
```

V1 的格式规则保持不变：每条详情固定为连续三行——第 1 行只写原文标题（英文标题可带中文对照翻译），第 2 行只写一句事实描述，第 3 行只写来源引用；禁止把标题与描述合并为“标题：描述”。来源单独一行用引用块（`> 来源：`），不并入事实描述行；链接以 Markdown 嵌入、正文不显示 URL 明文。标题保留脚本原始 `title`：只有英文原始标题才在后面加中文对照翻译括号，中文、日文等非英文标题直接写原题、不加翻译括号。来源链接文字内冒号替换为 `•`（内容保留）、`公众号` 统一替换为 `WX`；所有来源用 `•` 连接，同渠道去重（渠道只写一次），每条最多 2 个渠道，超过时只保留前 2 个并加 `+N`。只增加链接时不得改动标题、章节或换行结构。完整 V1 规则以 `prompts/news-brief-v2.md` 为唯一格式来源。

独立 V2 使用精简模型契约 → `glance_brief.noon-news.v2` 两层流程。模型只返回单个候选 ID、摘要、可选中文对照翻译和全局要点排序；不再返回 `item_ref`、影响说明或证据等级，也不合并多个候选。程序负责回填标题、来源、URL、发布时间、稳定 `item_id`，并只做必要的结构与引用校验。超过 5 条要点取前 5 条，重复或未绑定要点忽略；数字等价写法、摘要长度和额外无害字段不再阻断整份报告。不要把 V2 的语义 JSON 与 `evaluate_outputs.py` 的质量评估结果混用。旧的 `glance_brief.noon-news.model.v2` 仅用于历史离线 fixture 兼容。

## 失败处理

- 单个来源失败：保留其他可用来源，并在数据中保留失败状态。
- 所有来源失败：输出固定失败提示。
- 内容不足：少报或省略，不用无关来源凑数。