# Source adapters

`runtime/reports/lib/glance_brief/source_adapters/` 是 reports runtime 的来源适配边界。
它的作用是让来源接入逻辑可以独立扩展，而不把来源名称和实现代码散落到
entrypoint、assembly 或 resolver 中。

## 两层边界

```text
input adapter
  文件 / command / shared snapshot
  → 原始 payload

source adapter
  原始 payload + source 配置
  → canonical candidate items + source snapshot + diagnostics
```

- `input_adapters/` 只负责取得 payload，不理解来源业务。
- `source_adapters/` 负责来源字段映射、来源级排除、provenance 和来源特有结构。
- assembly 负责按 Report Plan 合并候选、绑定 section 和执行报告健康门禁。
- resolver 和 renderer 不应读取来源原始字段。

## `source_id` 与 `adapter_id`

两者有意分开：

- `source_id` 表示数据来源，例如 `rss_summary` 或 `aihot`；
- `adapter_id` 表示处理实现，例如 `generic`。

配置中的 `adapter` 是可选字段，缺省值为 `generic`：

```json
{
  "sources": {
    "example_source": {
      "adapter": "generic",
      "driver": "snapshot_json",
      "items_path": "example.items",
      "map": {
        "title": "title",
        "text": "summary",
        "links": []
      }
    }
  }
}
```

因此多个 source 可以复用同一个 adapter；更换 source ID 也不需要修改 registry。

## 当前目录

```text
source_adapters/
├── __init__.py                 # registry 与统一 dispatch
├── generic.py                  # items_path / map / exclude / snapshot
└── local_open_source_radar.py  # 现有 local-radar publication 兼容桥
```

普通字段形态来源使用 `generic.py`，不需要新增 Python 文件。只有来源存在额外
payload 或 publication 语义时，才新增专用 adapter。

## Generic adapter 返回值

```python
{
    "items": [
        # canonical candidates
    ],
    "snapshot": {
        # configured source snapshot fields
    },
    "diagnostics": {
        "excluded": 0,
        "rejections": []
    }
}
```

adapter 可以做来源级校验，但不能：

- 调用模型；
- 生成最终 Markdown；
- 决定报告 section 顺序；
- 负责 Feishu 或其它投递；
- 读取旧报告作为事实兜底。

## Registry

新代码按 adapter ID 调用：

```python
from glance_brief import source_adapters

result = source_adapters.adapt_source(
    source_id,
    source_config,
    payload,
)
```

registry 找不到 adapter 或 adapter 没有统一入口时必须 fail closed。旧的
`get_source_adapter()` 和 `adapt_payload()` 仍保留给 local-radar 兼容桥，新的
通用来源不应使用这两个兼容 API。

## 新增来源的选择

完整的产品接入流程见 [`docs/adding-sources.md`](adding-sources.md)，producer stdout
约束见 [`docs/producer-contract.md`](producer-contract.md)。如果只需要确认一个
捕获 payload 的 mapping，可使用 reports runtime 的 `source check` / `source preview`
命令；它们不调用模型，也不投递消息。

优先级从简单到复杂：

1. 新来源只需字段路径映射：配置 `adapter: generic`，增加 fixture 和测试；
2. 新来源需要特殊 payload 解析：新增 `source_adapters/<name>.py`，注册 adapter，
   增加 fixture 和失败测试；
3. 只有多个来源共享同一套复杂语义时，才考虑进一步抽取公共模块。

不要为每个 RSS、聚合器或字段相似的来源创建专用 adapter。
