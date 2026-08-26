# glance_brief V2

V2 是与现有 V1 并行的本地实现，不接入生产 Cron、Hermes jobs 或 runtime。新闻 V2 使用独立的语义协议：模型只做编辑选择和受约束的文字表达，程序负责事实元数据、引用恢复、必要结构校验和 Markdown 渲染。

当前边界、目录分工和接入门槛见 [`STATUS.md`](STATUS.md)。

## 固定流程

```text
JSON 来源 → 机械映射 / 精确匹配 / take / URL 去重
         → 四个新闻候选池 + 稳定 candidate_id
         → 模型返回单候选详情和 candidate_id 要点排序
         → 必要校验：JSON、板块、候选 ID 和引用关系
         → 程序回填标题 / URL / 来源 / 发布时间 / item_id
         → 固定 renderer 输出 Markdown
```

新闻模型看到标题和正文证据，但看不到 URL、来源 metadata。它只负责筛选、有限重分类、单候选摘要、可选中文对照翻译和全局今日要点；不同候选不由模型合并，避免把同主题但不同事件拼成一条。`top_points` 不是板块第一条的拼接，而是独立引用已选详情的全局排序。

## 新闻语义协议

午间新闻候选固定分为四个池：

- `international`：国际要闻；
- `domestic`：国内要闻；
- `business`：宏观与商业；
- `ai`：AI 主线。

模型输入和输出契约见 `prompts/noon-news.md`。精简模型契约只要求 `candidate_id`、摘要、可选中文对照翻译和要点排序；解析后的报告协议为 `glance_brief.noon-news.v2`。精简校验器只拦截无法渲染或无法恢复引用的结构问题：缺少必要板块、详情候选不存在或重复、要点无法绑定详情等会被处理；要点超过 5 条取前 5 条，重复或未绑定要点忽略，不因数字等价写法、摘要长度或额外无害字段阻断整份报告。旧的 `glance_brief.noon-news.model.v2` 仍仅用于读取历史离线 fixture，并保留旧的严格校验。

报告语义对象至少包含：

```text
semantic_protocol
report
report_date
generated_at
top_points[]         → item_ids / topic / fact
sections[]           → item_id / candidate_ids / headline / headline_zh /
                         summary / sources / published_at
```

来源、URL、发布时间和原始标题由程序从候选回填，不接受模型自由填写。模型原始响应在校验失败时保留在输出目录，正式 Markdown 不会静默生成。

## 配置

单个 JSON 文件只包含：

- `schema_version: 1`
- `sources`：`json_file`、`command_json` 或 `http_json`
- 每个来源的 `items_path` 和受限 `map`
- `reports.<report>.sections`：来源数组、可选精确 `match`、可选 `take`

参考：`config/brief.example.json`。午间新闻示例配置显式包含四个板块，国内候选不会因为缺少板块绑定而丢失。

不支持 priority、primary/fallback、semantic hints、过滤 DSL、样式配置、Prompt 注入、动态 Python 插件或多 schema 兼容。

## 命令

```bash
python3 v2/run_v2.py check --config v2/config/brief.example.json
python3 v2/run_v2.py probe --config v2/config/brief.example.json
python3 v2/run_v2.py run \
  --config v2/config/brief.example.json \
  --report noon-news \
  --output-dir /tmp/glance-v2
```

Agents 报告日期由代码传入：

```bash
python3 v2/run_v2.py run \
  --config v2/config/brief.example.json \
  --report agents-report \
  --date YYYY-MM-DD \
  --output-dir /tmp/glance-v2
```

`run` 通过 Hermes `context_engine` 空工具集调用模型；模型不能联网或调用其他工具。

## Legacy agents-radar

旧 Markdown 只由专用转换器处理，不进入通用 mapper：

```bash
python3 v2/convert_agents_radar.py \
  --input <v1-agents-input.json> \
  --output <agents-radar-structured.json>
```

转换器只接受固定 section 和 5 个固定分类，格式异常直接失败，不猜测或修复。
