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
- `fresh_hot` 是 `hot_today` 的唯一子集，分类唯一完整覆盖 hot；
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
- `map`：title、text、published_at、extra、links；
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
- section 与 selection limits。

模型不得看到 URL、provenance、来源 metadata、日期、项目指标、Codex Markdown 或最终 Markdown 骨架。payload 出现 URL 时必须 fail closed。

## Resolved schema 2

模型返回的 ID 必须存在于 registry。Resolver 回填：

- 原题、日期和发布时间；
- 精确 URL 与来源层级；
- 项目身份、描述、指标、fresh 和分类；
- producer-owned Codex block。

模型字段只允许进入摘要、英文标题中文对照、主题和总体趋势。数字只能做等值格式规范化，不能换算币种、单位、比例或数量级。

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
