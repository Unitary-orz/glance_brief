# 新增来源指南

这份指南面向希望把一个新的 RSS、API、文件快照或本地 producer 接入
`glance_brief` 的使用者。先判断来源属于哪一层，再开始改配置。

## 先选接入层级

| 情况 | 做法 | 是否需要改 Python |
|---|---|---:|
| 数据已经在 schema-1 snapshot 中，记录是一组普通 items | `snapshot_json` + `generic` + `map` | 否 |
| 需要调用 API、RSS、分页、重试或认证 | 写一个 producer，让它输出 schema-1 snapshot | producer 需要 |
| payload 不是普通 items，拥有独立 publication 语义 | 注册专用 source adapter | 需要维护者扩展 |
| 想新增完全不同的报告组件类型 | 扩展 Report Plan、resolver、renderer 和测试 | 需要维护者扩展 |

**推荐原则：**先把外部来源标准化为 producer JSON，再用配置接入；不要为了
一个字段名不同的来源新建 Python adapter，也不要把 HTTP、shell 或模板表达式
塞进 source 配置。

## Tier 1：只用配置接入普通来源

### 1. 准备一个 schema-1 snapshot

producer stdout 必须是一个 JSON object，顶层包含 `schema_version: 1` 和至少
一个来源 namespace：

```json
{
  "schema_version": 1,
  "new_feed": {
    "items": [
      {
        "headline": "New source headline",
        "summary": "Evidence from the source.",
        "url": "https://example.com/article"
      }
    ]
  }
}
```

完整约束见 [`producer-contract.md`](producer-contract.md) 和
[`../config/producer-output.schema.json`](../config/producer-output.schema.json)。
日志写 stderr，不要混入 stdout。

### 2. 在 `sources` 中声明字段映射

把下面的 source 加入 reports 配置的 `sources`：

```json
{
  "new_feed": {
    "driver": "snapshot_json",
    "items_path": "new_feed.items",
    "channel_id": "new-feed",
    "channel_label": "NF",
    "map": {
      "title": "headline",
      "text": ["summary", "headline"],
      "links": [
        {
          "role": "article",
          "label": "New Feed",
          "path": "url"
        }
      ]
    }
  }
}
```

支持的通用能力：

- 点路径：`a.b.c`；
- fallback 路径：`["summary", "headline"]`；
- `published_at`；
- `extra` 中的受限语义字段；
- `exclude` 原始字段精确匹配；
- `links` 中的 provenance URL；
- `snapshot` 中的 producer-owned metadata。

不要把 URL 拼进 `title` 或 `text`。可见链接必须从 `links` 映射恢复。

### 3. 把 source 绑定到报告组件

只声明 source 不会让它进入报告。还要在目标 report 的 component 中增加 binding：

```json
{
  "id": "technology_society",
  "order": 3,
  "title": "科技与社会",
  "kind": "editorial_items",
  "editorial_hint": "科技影响社会和日常生活的事件",
  "bindings": [
    {"source": "new_feed", "take": 10}
  ],
  "health": {"minimum_candidates": 1},
  "policy": {"selection_limit": {"min": 1, "max": 3}}
}
```

如果只想把来源加入已有 section，保留该 section 的其他字段，只增加 binding。
如果要新增全新的 component，先确认它属于当前 profile 支持的 component kind；
新增 component kind 不是普通来源接入，而是维护者开发任务。

### 4. 离线检查和预览

`source check` 只读取捕获的 payload，不调用 producer、模型或投递：

```bash
PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py \
  source check \
  --config config/brief.reports.example.json \
  --source new_feed \
  --payload /tmp/new-feed-snapshot.json \
  --report noon-news
```

输出包括：

- 原始记录数；
- accepted / excluded / rejected 数；
- candidate ID 和 provenance；
- source 被哪些 report component 引用；
- 每个 binding 的匹配数和 `take` 后数量。

需要人工快速阅读时使用：

```bash
PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py \
  source preview \
  --config config/brief.reports.example.json \
  --source new_feed \
  --payload /tmp/new-feed-snapshot.json \
  --limit 5
```

这是 preview，不是日报预览：它不会调用模型，不会生成 `report.md`，也不会发送
消息。它只检查来源映射和候选证据。

### 5. 运行配置和报告级检查

```bash
PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py \
  check \
  --config config/brief.reports.example.json

PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py \
  probe \
  --config config/brief.reports.example.json \
  --report noon-news
```

`check` 校验配置结构；`probe` 走完整 source assembly 和 health gate，但不调用模型。

## Tier 2：为实时外部来源写 producer

当前正式 reports runtime 推荐所有来源通过一次 prefetch 进入不可变 snapshot：

```text
producer / prefetch
  → schema-1 JSON stdout
  → report input snapshot
  → snapshot_json source view
  → generic adapter
```

producer 应负责：

- 网络/API/RSS 访问；
- timeout、重试和认证；
- 原始字段保留；
- source-specific pagination 和清洗；
- stdout 只输出一个 JSON envelope。

producer 不应负责：

- 调用模型；
- 生成最终日报 Markdown；
- 修改 Hermes Cron；
- 发送 Feishu 或其它消息；
- 根据旧报告补事实。

如果需要把 producer 接入现有 News/Agents prefetch，增加一个稳定的顶层
namespace，再在 config 中用 `items_path` 指向它。不要让 source config 和 prefetch
各自重复抓同一个来源。

`command_json` 是受限的独立输入 driver，适合明确需要单独执行 argv 命令的场景；
对于共享 snapshot 的正式 reports 运行，优先使用 `snapshot_json`，避免一次报告中
各 source 重复采集或无法 replay 同一份输入。

## Tier 3：何时才写专用 adapter

只有 generic 无法表达以下语义时才写专用 adapter：

- payload 不是普通 item 集合；
- source 自带独立 publication / category coverage 约束；
- 需要把多个 producer-owned 结构挂载到 snapshot；
- 有无法安全表达为字段映射的来源契约。

专用 adapter 必须：

1. 注册明确的 `adapter_id`；
2. 保持 source mapping 与报告 renderer 分离；
3. 添加成功 fixture 和失败 fixture；
4. 记录 provenance 和结构化 diagnostics；
5. 不调用模型、不生成最终 Markdown。

## 发布前清单

- [ ] producer stdout 是单个 schema-1 JSON envelope；
- [ ] `schema_version` 为 `1`，至少有一个 namespace；
- [ ] source 使用 `snapshot_json` 或已明确说明独立 driver 的原因；
- [ ] `items_path` 和所有 map path 在 fixture 上有值；
- [ ] 每条可发布候选都有合法 provenance URL；
- [ ] exclude 在 binding `take` 前生效；
- [ ] source 已绑定到目标 report component；
- [ ] `source check` 通过；
- [ ] `source preview` 人工看过标题、正文和链接；
- [ ] `check` 和目标 report 的 `probe` 通过；
- [ ] 增加 fixture / regression test；
- [ ] runtime 同步和 Cron 触发是独立操作，未把 live 路径、凭据或投递 ID 写入仓库。

配置编辑器可使用 [`../config/brief.reports.schema.json`](../config/brief.reports.schema.json)
获得字段补全和基础类型检查；最终规则以运行时 Python validator 为准。
