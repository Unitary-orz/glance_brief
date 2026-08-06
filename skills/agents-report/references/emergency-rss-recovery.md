# RSS 应急恢复工作流（历史参考）

> 当前版本不依赖本文件中的私有 Hermes 应急脚本。预取入口会自动按正文标记选择章节；需要人工检查时，请从仓库根目录运行 `skills/agents-report/scripts/agents-radar-daily.py`。

历史上如果用 `--sections "ai-trending:4,5,6"` 跑出来后：

- `BLOCK_COUNT: 4`（不是预期的 6+）
- `--- BLOCK 4 | TITLE: 本日报由 agents-radar 自动生成。 ---`（仅 footer）
- `--- BLOCK 5 | TITLE:` 或 `BLOCK 6` 不存在 / 是空块

→ cron prompt 里的 block 号已与 RSS 实际结构不匹配，**直接基于这个输出编造简报 = 错报**。

## 应急恢复步骤

### 1. 用应急脚本拿真实正文

```bash
python3 skills/agents-report/scripts/agents-radar-daily.py --source ai-trending
python3 skills/agents-report/scripts/agents-radar-daily.py --source ai-agents
```

脚本会输出当前采集器的正文 blocks；下方内容形态来自历史应急脚本，仅用于识别目标 section，不是当前 JSON/文本契约。

```
=== SOURCE: ai-trending | DATE: 2026-07-10 ===
TITLE: AI 开源趋势日报 2026-07-10
LINK: https://duanyytop.github.io/agents-radar/#2026-07-10/ai-trending
SECTION_COUNT: 5

--- [前言] (len=92) ---
数据来源: GitHub Trending + GitHub Search API | 生成时间: 2026-07-10 01:49 UTC
...

--- 1. 今日速览 (len=429) ---
今日 AI 开源社区的热点高度聚焦于 AI Agent 的应用落地与生态构建...
...

--- 2. 各维度热门项目 (len=3500) ---
🔧 AI 基础工具
- addyosmani/agent-skills ⭐0 (+2554 today)
...
```

### 2. 在输出里找目标 section

用户简报模板要的是这三段（看 h3 标题前缀）：

- 「今日速览」 → 今日速览
- 「各维度热门项目」 → 各维度热门项目
- 「趋势信号分析」 → 趋势信号分析

### 3. 格式化输出

完全基于 emergency-rss-recover.py 的 stdout 内容，按 cron prompt 模板生成最终简报。不要混用 agents-radar-daily.py 这次的空 BLOCK 4/5/6 输出。

## 应急脚本 vs 官方脚本

| 维度 | agents-radar-daily.py | emergency-rss-recover.py |
|------|----------------------|--------------------------|
| 切分依据 | `<hr />` + block 序号 | h1-h6 标题层级 |
| 链接处理 | 丢弃 URL，只留文字 | 保留 `[text](url)` 供 LLM 引用 |
| Block 漂移鲁棒性 | 脆（block 号写死就废） | 鲁棒（按标题切） |
| 用途 | 正常 cron 抓取 | 漂移后人工救场 |

## 后续动作

1. 用真实正文生成当日报
2. 同步更新 cron prompt：`--sections` 从 `4,5,6` 改成 `今日速览,各维度热门项目,趋势信号分析`
3. 在 SKILL.md 的漂移表里加一行记录新结构
4. 下次 cron 自动跑出新结构对应内容

## 已验证日期

- **2026-07-10**：ai-trending 仍是 4 blocks，正文全在 BLOCK 3，BLOCK 4 footer。emergency-rss-recover.py 成功切出 5 个 h3 sections。
