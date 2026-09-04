# glance_brief v0.3.0 Data Contracts

## 版本分层

三个版本概念必须分开：

- 仓库/产品版本：`v0.3.0`；
- producer 预取输入：可为 `schema_version: 1`；
- canonical candidate registry 与 resolved report：`schema_version: 2`。

`schema_version` 是数据协议，不是产品版本；正式业务包版本由仓库 `VERSION` 管理。

## Producer 输入

Producer 只负责采集和原始事实，不输出最终 Markdown。现有 prefetch JSON 顶层保持：

```json
{
  "schema_version": 1
}
```

### agents-report 来源

```text
agents_radar
  ok
  stdout
  selected_blocks
  open_source_quality
aihot
  items[]
codexradar
  ok
  rankings
  markdown
generated_at
```

关键约束：

- AI HOT 条目链接、来源和分类取自原始字段；
- CodexRadar Markdown 是 producer-owned block，验证后逐字插入；
- 开源雷达必须提供 `quality.ok`、`hot_today`、`fresh_hot`、`local_report_categories`；
- `fresh_hot` 是 `hot_today` 的唯一子集，分类唯一完整覆盖 hot；最终报告的每个 `fresh_hot` 项目还携带其程序确定的分类标签，分类榜仍可重复展示该项目；
- Star 展示统一使用 `stars_today`（GitHub Trending 原始日增量）；`stars_delta` 仅用于本地快照差值和排序，不得渲染为 `★/日`；
- GitHub URL 必须与 `owner/repo` 身份一致。

### noon-news 来源

```text
news_aggregator
  ok
  items[]
rss_summary
  ok
  items[]
aihot
  ok
  items[]
```

来源 URL 使用原始条目的 `link` 或 `url`，不得自行拼接。AI HOT 条目页与原文链接是不同 provenance link，应分别保留。

## Source config schema 2

配置支持：

- `json_file`；
- 受限 `command_json`：argv 数组、timeout、受控 cwd、基础环境和显式 `env_allowlist`；
- `map`：title、text、published_at、extra、links；可选 `strip_urls_from_text: true` 只清理正文与 `extra.description` 中的 URL，provenance links 仍从独立字段保留；
- 可选 `exclude`：按原始记录的稳定字段路径做精确字符串集合过滤；在候选构造和 binding `take` 之前执行，过滤命中数写入 assembled diagnostics；
- `required`：必选来源失败时在模型调用前 hard fail；
- `minimum_candidates`：板块候选下限；
- Noon `selection_limits`：最终选择数量的 min/max；
- producer-owned snapshot metadata。

不支持 shell string、动态 import、HTTP driver、模板 DSL 或 legacy converter。

## Candidate registry

每个 canonical candidate 至少包含：

```text
candidate_id
  title
  text
  published_at
  extra
  provenance[]
    channel_id
    channel_label
    links[]
      role
      label
      url
```

`candidate_id` 是候选事实内容的稳定摘要，不依赖列表位置。标题和证据文本中包含明文 URL、unsafe Markdown 或无有效事实的候选不得进入 registry；候选级问题写入 `candidate_rejections`，同来源其余合法候选继续处理。来源读取本身失败才写入 `source_errors`。

## Lean model payload

模型只看到：

- candidate ID；
- 标题和证据文本；
- 报告语义所需的受限 extra；
- section 与 selection limits；
- 程序已经确定要展示的 `open_source_display_ids`，仅包含 candidate ID。

模型不得看到 URL、provenance、来源 metadata、日期、项目指标、Codex Markdown 或最终 Markdown 骨架。payload 出现 URL 时必须 fail closed。

## Resolved schema 2

模型返回的 ID 必须存在于 registry。Resolver 回填：

- 原题、日期和发布时间；
- 精确 URL 与来源层级；
- 项目身份、描述、指标、fresh 和分类；
- producer-owned Codex block。

AI 动态模型字段为 `candidate_ids`、`topic` 和 `summary`：先将候选按事件、进展或明确互补主题聚类，再选择最多三条生态变化切片；每条绑定 1–3 个候选，候选池达到 5 条时默认争取覆盖至少 5 个候选 ID，全文不得复用候选 ID；摘要数字必须由绑定候选证据的并集支持。`topic` 是短导语，`summary` 不超过 140 字，并拒绝 RSS/feed/网页采集等来源管线词。模型还可写英文标题中文对照、项目简介中文翻译、主题和总体趋势。`open_source_descriptions` 必须逐个覆盖 `open_source_display_ids`，简介只能根据对应候选 `text` 翻译；数字只能逐字保留来源支持的内容，不能换算币种、单位、比例或数量级。项目身份、URL、Star、fresh 和分类不由模型提供。

## 失败与 artifacts

来源失败保留结构化状态，禁止用常识或旧缓存伪造。任何 hard gate 失败都不得生成 `report.md`；运行目录保留可用的：

- `assembled.json`；
- `model-payload.json`；
- `model-response.raw.txt`；
- `failure.json`；
- `manifest.json`。

成功 manifest 记录 config、输入和输出 artifact 的 SHA-256。Replay 先验证 manifest，再使用保存的 assembled 与 model response 重建，不读取来源、不调用模型。

## 环境变量

Producer 兼容环境变量包括：

- 通用：`BRIEF_TIMEZONE`、`NEWS_PYTHON`；
- agents-report：`AGENTS_RADAR_COLLECTOR`、`AGENTS_RADAR_FEED_URL`、`AGENTS_RADAR_OUTPUT_DIR`、`AIHOT_V1_BASE`、`CODEXRADAR_CONFIG`、`AGENTS_RADAR_QUALITY_CONFIG`、`AGENTS_RADAR_CRON_OUTPUT_DIR`；
- noon-news：`NEWS_AGGREGATOR_SCRIPT`、`NEWS_SUMMARY_SCRIPT`、`NOON_NEWS_SOURCES`、`NOON_NEWS_LIMIT`、`AIHOT_V1_BASE`、`NOON_AIHOT_WINDOW`、`NOON_AIHOT_LIMIT`。

这些变量属于 producer/runtime adapter，不得进入模型响应或最终报告。
