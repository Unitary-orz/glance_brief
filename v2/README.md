# glance_brief V2

V2 是独立、不可兼容旧实验协议的 Brief pipeline。它不接入生产 Cron、Hermes runtime 或飞书投递。

## 架构边界

```text
producer JSON
→ bounded adapters + stable candidate registry
→ lean semantic model payload
→ model JSON only
→ immutable resolved schema
→ strict validator
→ deterministic Markdown renderer
→ local preview artifacts
```

**模型只拥有语义：**候选选择、忠实摘要、英文标题中文对照、总体趋势。

**程序拥有事实和格式：**日期、原题、URL、来源层级、发布时间、项目身份、Star、fresh 标记、分类、CodexRadar block 和 Markdown 骨架。模型看不到 URL，也不能创建或修改这些字段。

## 两份报告

### noon-news

固定三段：

1. `international`：国际要闻；
2. `macro_business`：宏观与商业；
3. `ai`：AI 主线。

每条详情只绑定一个 `candidate_id`，最终固定三行：原题、事实句、来源引用。英文原题可附约 12–28 字中文对照；长度越界记录 soft warning，但不会掩盖事实与 provenance hard gate。中文、日文等非英文原题不翻译。AIHOT 条目页和原文 URL 分层保存并逐字渲染。

### agents-report

模型只返回最多三条 AI 生态摘要和恰好两条开源总体趋势。程序原样插入 producer 提供并已验证的 `codexradar.markdown`，并从 `hot_today`、`fresh_hot`、`local_report_categories` 确定项目事实和分类。主报告保留 `**✨新热门开源**`，不显示 `new_projects`。

## 配置

配置 schema 固定为 `2`，接受脱敏本地 `json_file` 快照，或使用 argv 数组和超时约束的 `command_json` producer adapter：

- `sources.<id>.path` / `items_path`；
- 可选 `required: true`，失败时在模型调用前 hard fail；
- `command_json` 可配 `env_allowlist`，默认只透传基础运行变量；
- 受限字段 `map` 和精确 links provenance；
- 可选 producer-owned `snapshot`；
- `reports.<report>.minimum_candidates` 板块候选下限与 `sections` 的来源绑定、精确 `match` 和 `take`；
- agents metadata 指向 CodexRadar 和本地开源雷达来源。

不支持旧 schema、HTTP driver、strict/lean/legacy 分支、动态插件、样式配置或兼容转换器。参考 [`config/brief.example.json`](config/brief.example.json)。

## 命令

```bash
python3 v2/run_v2.py check \
  --config v2/config/brief.example.json

python3 v2/run_v2.py probe \
  --config v2/config/brief.example.json \
  --report noon-news
```

离线 fixture run：

```bash
python3 v2/run_v2.py run \
  --config v2/config/brief.example.json \
  --report noon-news \
  --model-response /path/to/model-response.json \
  --date YYYY-MM-DD \
  --output-dir /tmp/glance-v2-noon
```

非投递 live model run（默认 `MiniMax-M3` / `minimax-cn`）：

```bash
python3 v2/run_v2.py run \
  --config /path/to/read-only-live-config.json \
  --report agents-report \
  --model MiniMax-M3 \
  --provider minimax-cn \
  --date YYYY-MM-DD \
  --output-dir /tmp/glance-v2-agents-live
```

模型调用走 `hermes chat -q` 单轮边界，使用 `--toolsets safe --ignore-rules --max-turns 1`；不调用 producer 工具，不投递。

## Artifacts

成功 run 写入：

- `assembled.json`
- `model-payload.json`
- `model-prompt.txt`
- `model-response.raw.txt`
- `model-response.json`
- `resolved.json`
- `warnings.json`
- `report.md`
- `usage.json`

失败时保留已生成的输入、prompt、原始响应和 `failure.json`，并删除旧的 `resolved.json` / `warnings.json` / `report.md`，确保 fail closed。

每次成功或失败运行都会写入 `manifest.json`：包含报告、状态、生成时间和全部输入/输出 artifact 的 SHA-256，以及 config 哈希与模型参数，用于生产审计与回放。

## 验证

```bash
python3 -B -m unittest tests.test_v2_contracts tests.test_v2_pipeline -v
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile v2/*.py tests/test_v2_contracts.py tests/test_v2_pipeline.py
git diff --check
```

生产接入边界见 [`STATUS.md`](STATUS.md)。
