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
agents_radar
  ok
  stdout
  stderr
  attempts
  selected_blocks
  selection_mode
  open_source_quality
    ok
    source_project_count
    source_linked_project_count
    source_unlinked_projects[]
    categories[]
    other_projects_max
    warnings[]
aihot
  source
  api
  window
  categories
    industry
      ok
      items[]
    paper
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

AI HOT 关键字段：

- `items[*].links.aihot`：站内原文链接
- `items[*].source.name`：来源名称
- `page.count` / `page.hasMore`：分页信息

`agents_radar.open_source_quality` 是离线机器检查结果：它记录来源项目的真实 GitHub 链接覆盖情况和每行 `其他项目` 上限。Prompt 可以据此省略无法链接的项目，但不得猜测或拼接 URL。

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

### agents-report

- `AGENTS_RADAR_COLLECTOR`
- `AGENTS_RADAR_FEED_URL`
- `AGENTS_RADAR_OUTPUT_DIR`
- `AIHOT_V1_BASE`
- `AIHOT_USER_AGENT`
- `CODEXRADAR_CONFIG`
- `AGENTS_RADAR_QUALITY_CONFIG`
- `AGENTS_RADAR_QUALITY_MODULE_DIR`（质量模块不与预取入口同目录时使用）
- `AGENTS_RADAR_CRON_OUTPUT_DIR`（仅用于 `agents_radar_quality_check.py --latest`）

### noon-news

- `NEWS_AGGREGATOR_SCRIPT`
- `NEWS_SUMMARY_SCRIPT`
- `NOON_NEWS_SOURCES`
- `NOON_NEWS_LIMIT`
- `AIHOT_PUBLIC_BASE`
- `NOON_AIHOT_SINCE_HOURS`
- `NOON_AIHOT_TAKE`
