---
name: agents-report
description: >-
  每日 AI / Agents 生态报告 Skill。
  整合 agents-radar、AI HOT 和 CodexRadar 数据，输出 AI 生态动态、
  模型效率和开源热点趋势。核心脚本可独立运行，定时投递由 runtime adapter 配置。
triggers:
  - agents-report
  - agents-radar
  - AI 开源雷达
  - AI 生态日报
---

# agents-report

## 运行入口

```bash
python3 skills/agents-report/scripts/agents_radar_prefetch.py
```

脚本输出一个 `schema_version: 1` 的 JSON，供 Prompt 格式化。它不会发送消息。

## 脚本

- `agents_radar_prefetch.py`：本地 GitHub 雷达、AI HOT 和 CodexRadar 预取编排；本地雷达只读取当天快照
- `agents-radar-daily.py`：agents-radar RSS 原始采集器
- `codexradar_efficiency.py`：CodexRadar 读取、排序和 Markdown 渲染
- `open_source_quality.py`：离线检查来源项目链接、分类和数量约束
- `agents_radar_quality_check.py`：检查来源文本或最终 Markdown 报告

## 数据来源

- 本地 GitHub 开源雷达：由独立本地雷达 Cron 生成当天快照；本报告只消费当天快照和其中的本地报告分类映射
- AI HOT v1：`/api/v1/items?mode=selected&window=24h&by=timeline&limit=20`；分类读取 `items[*].category`，不假定固定分类名称
- CodexRadar：公开 snapshot，失败时回退原始评测表

## 配置

复制：

```text
config/codexradar_watch.example.json
config/agents_radar_quality.example.json
```

为：

```text
config/codexradar_watch.json
config/agents_radar_quality.json
```

分别通过 `CODEXRADAR_CONFIG` 和 `AGENTS_RADAR_QUALITY_CONFIG` 指定。真实配置不要提交到公共仓库。

## 输出规则

完整格式契约见：

```text
prompts/agents-report-v2.md
```

当前固定板块为：

1. `🤖 AI 生态动态`
2. `🧠 CodexRadar 智力效率`
3. `🔥 开源热点趋势`

开源分类规则：

- 分类标题和项目归属必须逐字复用当天快照的 `local_report_categories`；不得根据项目描述、Topics 或模型知识自行分类、改名、合并、拆分或新建分类。
- 每个分类只展示映射中第一项，固定一行 `热门项目`；不展示其余项目，不生成“其他项目”或“新发现项目”区域。
- `local_report_categories` 缺失、不完整或未覆盖 `hot_today` 时，开源项目板块闭锁并写“信息有限”，不得自行补分类。

报告格式变更必须先更新 Prompt、输出契约和测试，不要只改运行时 Cron。

## 失败处理

- 本地雷达当天快照、质量检查或最终分类映射失败：只影响开源热点板块，写“信息有限”，不得回退到昨天或重新采集。
- AI HOT 请求失败或全局精选为空：只影响 AI 生态动态；证据不足时写“信息有限”，不得把固定分类为空表述成整个 AI HOT 没有新条目。
- CodexRadar 失败：原样使用脚本中的“信息有限”提示。
