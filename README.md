# glance_brief

面向 AI Agent 运行时的结构化简报工具集，提供新闻、Agents 生态、开源趋势和模型效率报告的预取、格式化与任务适配能力。

当前版本：**0.1.0**

## 项目定位

`glance_brief` 不是单一新闻抓取器，而是由三层组成的可复用工具集：

1. **预取脚本**：从真实来源获取结构化 JSON，避免格式化 Agent 自行搜索或编造。
2. **Skill / Prompt**：定义来源、事实边界、报告结构和输出约束。
3. **运行时适配层**：把同一套任务接入 Hermes、OpenClaw 或其他 Agent runtime。

核心脚本可以独立运行；定时投递需要配置对应的运行时适配层和外部 news skills。

## 包含的 Skills

### `agents-report`

每日 AI / Agents 生态报告，整合：

- agents-radar RSS
- AI HOT v1 行业与论文数据
- CodexRadar 模型效率数据

当前报告包含 AI 生态动态、CodexRadar 智力效率和开源热点趋势。

### `noon-news`

每日午间热点简报，预取：

- news-aggregator
- news-summary RSS
- AI HOT public API

输出包含今日要点和分类详情。来源 URL 必须来自原始数据；来源保持独立一行，不把链接并入事实描述。

## 目录结构

```text
skills/                 可独立安装的 Skill
  agents-report/
  noon-news/
adapters/               Hermes / OpenClaw 运行时适配说明和模板
docs/                   架构、数据契约和输出契约
tests/                  离线 fixtures 和跨 Skill 测试
VERSION                 项目版本
CHANGELOG.md            版本变化
```

## 安装

完整项目：

```bash
git clone https://github.com/Unitary-orz/glance_brief.git
cd glance_brief
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

只安装一个 Skill：

```bash
git clone --filter=blob:none --sparse https://github.com/Unitary-orz/glance_brief.git
cd glance_brief
git sparse-checkout set skills/agents-report
# 或：git sparse-checkout set skills/noon-news
```

需要运行时适配层、fixtures 和测试时，使用完整项目 checkout。

## 快速检查

```bash
python3 -m py_compile \
  skills/agents-report/scripts/*.py \
  skills/noon-news/scripts/*.py

python3 -m unittest discover -s tests -p 'test_*.py'
```

运行预取脚本时，通过环境变量提供运行时路径：

```bash
CODEXRADAR_CONFIG=/path/to/codexradar_watch.json \
AGENTS_RADAR_OUTPUT_DIR=/path/to/output \
python3 skills/agents-report/scripts/agents_radar_prefetch.py
```

午间新闻需要配置外部脚本：

```bash
NEWS_AGGREGATOR_SCRIPT=/path/to/fetch_news.py \
NEWS_SUMMARY_SCRIPT=/path/to/fetch_rss.py \
python3 skills/noon-news/scripts/noon_news_prefetch.py
```

## 运行时适配

- `adapters/hermes/`：Hermes Cron、环境变量和投递配置说明
- `adapters/openclaw/`：OpenClaw Cron、Skill 安装和投递配置说明

示例文件只提供模板，不包含真实聊天 ID、凭据、Job ID 或本机绝对路径。

## 版本策略

项目使用语义化版本：

- `0.1.x`：文档、路径、兼容性和小 bug 修复
- `0.2.0`：运行时适配和测试契约稳定
- `1.0.0`：安装、数据契约和输出格式稳定

Prompt 版本独立于项目版本；当前运行版 Prompt 记录为 `agents-report-v2` 和 `news-brief-v2`。

## 许可证

MIT License
