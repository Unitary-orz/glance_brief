# agents-report changelog

## 0.3.0 — 2026-08-31

- 对外版本统一为 glance_brief v0.3.0，并接入项目级正式 `glance_brief` core。
- 引入 candidate registry、lean semantic payload、resolver、strict validator 和 deterministic renderer。
- 模型不再拥有 URL、来源、项目事实、指标、分类、fresh、Codex block 或 Markdown。
- 增加 required、minimum candidates、quality、GitHub URL、manifest、replay 和 tamper rejection 门禁。

## 0.2.0 — 2026-08-10

- 安装说明增加正式入口：按根目录 `INSTALL.md` 的 Agent 安装契约执行。
- 移除 `data/brief` 与外部 `agents-radar` 目录假设；适配层由 `install/install.py` 生成，业务脚本保持不变。

## 0.1.0

- Synced the current agents-radar collector and prefetch pipeline.
- Added AI HOT v1 and CodexRadar prefetch contracts.
- Added the current three-block report structure and source rules.
- Replaced fixed BLOCK assumptions with content-marker selection.
- Added runtime-independent path configuration.
