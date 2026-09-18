---
name: noon-news
description: >-
  每日午间热点简报 Skill。预取国际、宏观商业和 AI 来源，按
  glance_brief v0.3.0 契约生成单候选、可追溯、确定性渲染的简报。
triggers:
  - noon-news
  - 今日热点简报
  - 午间新闻
  - 今日新闻
---

# noon-news — glance_brief v0.3.0

## 正式入口

本 Skill、顶层 `glance_brief/prompts/*` 和 `glance-brief/*` 入口都属于
schema 2 legacy compatibility line；在这条兼容线上，两份报告共享项目级
`glance_brief` core。仓库 CLI 用于配置检查、离线运行和 replay：

```bash
python3 -m glance_brief check --config config/brief.example.json
python3 -m glance_brief probe --config config/brief.example.json --report noon-news
```

当前正式 reports production 不使用顶层 `glance_brief/prompts/*` 作为唯一
语义契约；它使用 `runtime/reports/lib/glance_brief/prompts/*` 及其所在的
reports core。两条运行线有意并存：schema 2 legacy 安装后使用
`glance-brief/noon-news.py`；当前 reports production 安装后使用
`glance-brief-reports/news.py`，完成一次来源快照、外层 Agent semantic handoff、
严格 resolver、确定性渲染和 artifacts。

`noon_news_prefetch.py` 是可选 producer，不是最终报告入口，也不发送报告。

## 数据来源

- news-summary：国际新闻；
- news-aggregator：宏观、商业与综合新闻；
- AI HOT：AI 主线；必要时可使用 producer 提供的 V2EX 条目。

URL、来源标签、发布时间和原题必须来自 producer，不得搜索、猜测或拼接。

## 所有权边界

模型只返回：

- 每条唯一 `candidate_id`；
- 有独立正文时的单候选事实摘要；纯标题候选省略摘要；
- 英文原题的可选中文对照；
- 绑定已选详情的今日要点。

模型不得返回 URL、来源、日期、Markdown，不得跨候选合并事实或换算数字。

程序负责回填原题、来源、精确 URL、发布时间，根据规范化后的标题/正文派生 `title_only`，验证数字 provenance、selection limits 和安全文本，并生成固定 Markdown。`title_only` 不改变筛选、配额、优先级或排序。schema 2 legacy compatibility line 的完整语义契约见
`glance_brief/prompts/noon-news.md`；当前正式 reports production 的语义 Prompt 位于
`runtime/reports/lib/glance_brief/prompts/noon-news.md`，由
`glance-brief-reports/news.py` 入口使用。可见格式见 `docs/output-contracts.md`。

## 固定结构

1. `国际要闻`；
2. `宏观与商业`；
3. `AI 主线`。

有独立正文的详情固定三行：

1. 原始标题；仅英文标题可附约 12–28 字中文对照；
2. 一句候选支持的事实；
3. 独立来源引用块。

纯标题详情只输出原始标题（英文题可附中文对照）和独立来源引用块，不生成同义摘要。

来源链接正文不显示 URL 明文；同渠道去重，每条最多两个渠道，更多显示 `+N`。AI HOT 条目页与原文链接分层保留。

## 失败处理

- 含 URL 或 unsafe Markdown 的候选语义字段在 adapter 边界拒绝并记录 `candidate_rejections`；同来源其他合法候选继续；
- required 来源失败、板块低于 `minimum_candidates`、最终选择超出 `selection_limits`：hard fail；
- malformed 模型响应或数字/ID/provenance 契约失败：保留 raw response、`failure.json` 和 failed manifest，不生成 `report.md`；
- 不用常识、旧缓存或其他来源伪造失败板块。

## 配置与发布边界

- `config/brief.example.json` 只用于离线结构示例；安装后必须创建真实 schema 2 `brief.json`；
- 模型/provider/timeout、schedule 和 delivery 属于 runtime adapter；
- OpenClaw 在 v0.3.0 仅有 adapter contract，没有可运行 Job；
- 真实配置不得提交；正式 Cron 切换必须先 dry-run、审查并获得明确授权。
