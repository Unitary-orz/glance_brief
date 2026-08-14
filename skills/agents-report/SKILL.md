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

- `agents_radar_prefetch.py`：Agents、AI HOT 和 CodexRadar 预取编排
- `agents-radar-daily.py`：agents-radar RSS 原始采集器
- `codexradar_efficiency.py`：CodexRadar 读取、排序和 Markdown 渲染
- `open_source_quality.py`：离线检查来源项目链接、分类和数量约束
- `agents_radar_quality_check.py`：检查来源文本或最终 Markdown 报告

## 数据来源

- agents-radar：`https://duanyytop.github.io/agents-radar/feed.xml`
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

报告格式变更必须先更新 Prompt、输出契约和测试，不要只改运行时 Cron。

## 失败处理

- agents-radar 失败或正文选择失败：输出 `⚠️ agents-radar 报告获取失败，请检查网络`，不要用常识补齐。
- AI HOT 请求失败或全局精选为空：只影响 AI 生态动态；证据不足时写“信息有限”，不得把固定分类为空表述成整个 AI HOT 没有新条目。
- CodexRadar 失败：原样使用脚本中的“信息有限”提示。
