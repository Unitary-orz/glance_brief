# noon-news changelog

## 0.3.0 — 2026-08-31

- 对外版本统一为 glance_brief v0.3.0，并接入项目级正式 `glance_brief` core。
- 引入单候选语义协议、candidate registry、元数据恢复、selection limits 和 deterministic renderer。
- 增加 unsafe candidate rejection、required、minimum candidates、manifest、replay 和 tamper rejection 门禁。
- 英文原题后的中文部分统一称为“中文对照翻译”。
- 当前 reports production 使用 `runtime/reports/` source tree，并通过 `hermes-reports` 安装到 `glance-brief-reports`。

## 0.2.0 — 2026-08-10

- 安装说明增加正式入口：按根目录 `INSTALL.md` 的 Agent 安装契约执行。
- 适配层由 `install/install.py` 生成，外部 news skills 在安装时检查，业务脚本保持不变。

## 0.1.0

- Synced the current news, RSS, and AI HOT prefetch pipeline.
- Added the current `今日要点` and `分类详情` structure.
- Preserved the independent source-link line layout.
- Added runtime-independent external script paths.
- Converts AI HOT curl startup failures into structured JSON source failures.
