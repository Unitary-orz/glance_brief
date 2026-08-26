# noon-news changelog

## 0.2.1 — 2026-08-26

- 英文原文标题后的中文部分统一称为“中文对照翻译”，同步 active Prompt 与输出契约测试。

## 0.2.0 — 2026-08-10

- 安装说明增加正式入口：按根目录 `INSTALL.md` 的 Agent 安装契约执行。
- 适配层由 `install/install.py` 生成，外部 news skills 在安装时检查，业务脚本保持不变。

## 0.1.0

- Synced the current news, RSS, and AI HOT prefetch pipeline.
- Added the current `今日要点` and `分类详情` structure.
- Preserved the independent source-link line layout.
- Added runtime-independent external script paths.
- Converts AI HOT curl startup failures into structured JSON source failures.
