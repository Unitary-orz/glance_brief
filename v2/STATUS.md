# Brief V2 状态与边界

## 当前状态

V2 当前用于**独立、非投递验证**：代码、fixture、只读 live producer 快照和本地 preview 均位于独立 worktree。它不修改 `$HOME/.hermes` runtime、Cron、模型配置或飞书目标。

## 目录

```text
v2/
├── adapters.py              # producer JSON → bounded candidate registry
├── contracts.py             # immutable schema 与安全校验
├── resolve.py               # semantic JSON → trusted resolved report
├── render_report.py         # deterministic Markdown renderer
├── run_v2.py                # check / probe / run artifact pipeline
├── config/                  # 脱敏 schema v2 示例配置
├── fixtures/                # 当前协议离线 source fixtures
└── prompts/                 # 模型只写语义 JSON 的契约
```

V2 不含 legacy converter、legacy fixtures、legacy tests 或多协议运行分支。

## 验证门槛

```bash
python3 v2/run_v2.py check --config v2/config/brief.example.json
python3 -B -m unittest tests.test_v2_contracts tests.test_v2_pipeline -v
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile v2/*.py tests/test_v2_contracts.py tests/test_v2_pipeline.py
git diff --check
```

当前独立验收已覆盖：

1. 脱敏 fixture 两报告端到端 preview；
2. 同日只读 producer 快照 preview；
3. 正式模型的非投递 live run；
4. URL provenance、Codex block、分类覆盖、项目事实和可见样式机器复核；
5. 与当日 V1 正式产物做结构对比，但不复制 V1 中无法核验的链接或偶然排版错误。

## Fail-closed

以下问题不生成 `report.md`：非法 JSON、未知或复用 candidate ID、候选外数字、URL 或 Markdown 注入、不合格 AIHOT provenance、Codex block 缺失、local-radar quality 非 `ok`、fresh 不是 hot 子集、分类未唯一完整覆盖 hot、模型输出项目名/Star/Codex 内容。

失败目录保留原始响应及 `failure.json`，不得把失败结果当作空报告投递。

## 生产接入条件

只有同时满足以下条件才讨论接入 runtime：

1. fixture、快照、live model 与完整仓库测试全部通过；
2. 正式 producer adapter 的路径和原子快照读取方式经过验证；
3. 失败回退、超时、费用和投递 adapter 有明确设计；
4. installer/runtime 同步形成单独、可审查变更；
5. 用户明确批准修改 Cron 与正式投递。
