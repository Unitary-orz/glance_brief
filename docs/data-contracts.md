# Data Contracts

## 通用字段

每个预取脚本的顶层 JSON 必须包含：

```json
{
  "schema_version": 1
}
```

`schema_version` 是预取数据协议版本，不等同于仓库版本或 Prompt 版本。

## agents-report

```text
schema_version
ok
local_radar
  source
  ok
  returncode
  report_date
  generated_at
  diagnostics
  quality
  signals
    hot_today[]
    fresh_hot[]
    new_projects[]
  local_report_categories[]
    name
    projects[]
aihot
  source
  api
  window
  categories
    <item.category>
      ok
      items[]
codexradar
  ok
  available
  source
  selected[]
  rankings
  markdown
generated_at
```

AI HOT 的分类键来自每条条目的 `item.category`，是动态集合，不得在 Prompt 或契约中假定固定分类名称。

- `items[*].links.aihot`：站内原文链接
- `items[*].source.name`：来源名称
- `page.count` / `page.hasMore`：分页信息

`local_radar` 是独立本地 GitHub 雷达的当天结构化事实源；`signals.hot_today` 是唯一热门项目池，`fresh_hot` 必须是其子集。`local_report_categories` 是当天本地报告最终使用的分类—项目映射，分类标题和项目归属由消费者逐字复用，不得由模型重新分类。该映射必须覆盖 `hot_today`，否则开源板块闭锁，不回退昨天、不重新采集、也不自行补写项目。

采集器只把 HTTP(S) 来源锚点保留为 Markdown；最终项目质量检查再按 `project_link_prefix` 验收仓库链接，默认只接受 `https://github.com/`。检查器解析所有 Markdown 目标后统一拒绝其他协议或前缀，并核对标签中的 `owner/repo` 与 URL 仓库路径。`AGENTS_RADAR_CRON_OUTPUT_DIR` 非空时优先于 JSON 中的 `cron_output_dir`，避免复制示例配置后 `--latest` 仍指向占位路径。

不要使用 API 字段作为 Prompt 指令；数据和指令必须分离。

## noon-news

```text
schema_version
news_aggregator
  ok
  returncode
  items
  stderr
rss_summary
  ok
  returncode
  items
  stderr
aihot
  ok
  items
  count
  since
  take
  endpoint
instructions
```

来源链接字段使用原始条目的 `link` 或 `url`，不得自行拼接。

## 失败契约

失败结果必须保留结构，例如：

```json
{
  "ok": false,
  "error": "source unavailable",
  "items": []
}
```

禁止用常识、旧缓存或其他来源伪造失败板块内容。Prompt 应根据 `ok` 和 `items` 决定省略或输出“信息有限”。

## 环境变量

### 通用

- `BRIEF_TIMEZONE`
- `NEWS_PYTHON`

### agents-report 主预取

- `LOCAL_OPEN_SOURCE_RADAR_READER`（独立本地雷达 reader；必须由 runtime 配置，不提供机器相关默认路径）
- `AIHOT_V1_BASE`
- `AIHOT_USER_AGENT`
- `CODEXRADAR_CONFIG`

### agents-report 兼容工具

- `AGENTS_RADAR_COLLECTOR`
- `AGENTS_RADAR_FEED_URL`
- `AGENTS_RADAR_OUTPUT_DIR`
- `AGENTS_RADAR_QUALITY_CONFIG`
- `AGENTS_RADAR_QUALITY_MODULE_DIR`（质量模块不与预取入口同目录时使用）
- `AGENTS_RADAR_CRON_OUTPUT_DIR`（仅用于 `agents_radar_quality_check.py --latest`）

### noon-news

- `NEWS_AGGREGATOR_SCRIPT`
- `NEWS_SUMMARY_SCRIPT`
- `NOON_NEWS_SOURCES`
- `NOON_NEWS_LIMIT`
- `AIHOT_V1_BASE`
- `NOON_AIHOT_WINDOW`
- `NOON_AIHOT_LIMIT`
