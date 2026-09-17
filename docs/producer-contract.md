# Producer contract

`glance_brief` 的 producer / prefetch 是来源访问边界。它可以调用 API、RSS、文件
或本地脚本，但必须把结果交给 reports runtime 的统一 source adapter，而不是直接
生成日报或发送消息。

这份 contract 约束的是 `runtime/reports` 的 News / Agents shared snapshot producer。
独立的 `producers/local-open-source-radar/` 有自己的 publication handoff contract，
不要把两种 payload 互相替换。

## stdout contract

每次 producer invocation 的 stdout 必须是**唯一一个** schema-1 JSON envelope：

```json
{
  "schema_version": 1,
  "source_namespace": {
    "items": []
  }
}
```

规则：

- 顶层必须是 JSON object；
- `schema_version` 必须是整数 `1`；
- 可以带可选的控制字段 `ok`、`error`、`instructions`、`generated_at`；这些字段不属于 source namespace，类型由 schema 固定（其中 `instructions` 可为字符串、对象或数组）；
- 除 `schema_version` 和上述控制字段外，至少有一个 source namespace；
- namespace 的值必须是 object 或 array；
- stdout 不得混入日志、进度、Markdown、模型响应或投递结果；
- 调试和诊断写 stderr；失败时使用非零退出码；
- namespace 名称由配置的 `items_path` 引用，保持稳定，不要随意改名。

机器可读辅助 schema：[`../config/producer-output.schema.json`](../config/producer-output.schema.json)。schema 与 runtime 都要求至少一个非控制字段作为 source namespace；运行时的最终校验由 `runtime/reports/lib/glance_brief/producer_contract.py` 执行。

## producer owns / runtime owns

### Producer owns

- API、RSS、文件和网络访问；
- pagination、retry、timeout、认证和 source-specific exceptions；
- 原始标题、正文、发布时间、URL 和 source metadata；
- 把不同上游响应整理为稳定的 JSON namespace；
- 不可恢复错误的退出码和 stderr 诊断。

### Reports runtime owns

- source `items_path` 和 field mapping；
- candidate ID、去重、provenance 安全校验；
- exclude、binding `take` 和 minimum candidate health gate；
- 模型可见 payload；
- semantic response validation、事实回填和最终 Markdown；
- artifact、manifest、replay 和投递前 fail-closed。

Producer 不应：

- 调用模型或启动另一个 Hermes session；
- 生成最终报告 Markdown；
- 修改 Cron、配置、凭据或投递目标；
- 读取旧报告来补当前来源事实。

## source namespace 设计

namespace 应按来源或 producer 能力划分，例如：

```json
{
  "schema_version": 1,
  "news_aggregator": {"items": []},
  "aihot": {"items": []},
  "codexradar": {"selected": [], "markdown": "..."}
}
```

不要把多个不相关来源压成一个 Markdown 字符串。普通 item 来源优先保留结构化
`items`，让 generic adapter 通过 `items_path`、`map` 和 `links` 接入。只有已经拥有
独立 publication 语义的 producer，才保留额外的结构化 metadata 或专用 adapter。

## 错误和空结果

- **transport / parse / auth 失败**：producer 返回非零退出码，stderr 提供简短原因；
  runtime 将其记录为 source error，并由 `required` 决定是否 hard fail。
- **合法空结果**：producer 仍返回 schema-1 envelope，namespace 的 `items` 可以为空；
  runtime 再由 report component 的 health policy 判断是否可生成报告。
- **部分坏记录**：尽量保留合法记录；source adapter 会把候选级拒绝写进 diagnostics，
  不应为了一个坏记录把整个 stdout 变成非 JSON。

不要用昨天的缓存或常识伪造失败来源，也不要把“空结果”和“请求失败”写成同一种
状态。

## 本地验证

先把 producer stdout 捕获到文件，再运行 source check：

```bash
python3 path/to/my_prefetch.py > /tmp/my-source-snapshot.json

PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py source check \
  --config config/brief.reports.example.json \
  --source my_source \
  --payload /tmp/my-source-snapshot.json
```

如果 producer 混入日志，contract parser 会拒绝整个 stdout。可以单独用 Python
校验固定样本：

```python
from glance_brief.producer_contract import parse_stdout

payload = parse_stdout(stdout_text)
```

source preview 是只读的，不调用模型，也不发送外部消息：

```bash
PYTHONPATH=runtime/reports/lib \
python3 runtime/reports/lib/glance_brief/cli.py source preview \
  --config config/brief.reports.example.json \
  --source my_source \
  --payload /tmp/my-source-snapshot.json \
  --limit 5
```

## 版本策略

`schema_version: 1` 是 producer envelope 的协议版本，不是仓库产品版本，也不是
candidate registry 的版本。新增可选 namespace 或 namespace 内部字段时，优先保持
schema-1 兼容；如果改变 envelope 形状、stdout 语义或 namespace 的基本类型，应提升
producer schema，并同步 runtime contract、fixture、文档和安装闭包。
