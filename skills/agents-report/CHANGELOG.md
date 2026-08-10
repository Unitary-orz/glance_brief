# agents-report changelog

## 0.2.0 — 2026-08-10

- 安装说明增加正式入口：按根目录 `INSTALL.md` 的 Agent 安装契约执行。
- 移除 `data/brief` 与外部 `agents-radar` 目录假设；适配层由 `install/install.py` 生成，业务脚本保持不变。

## 0.1.0

- Synced the current agents-radar collector and prefetch pipeline.
- Added AI HOT v1 and CodexRadar prefetch contracts.
- Added the current three-block report structure and source rules.
- Replaced fixed BLOCK assumptions with content-marker selection.
- Added runtime-independent path configuration.
