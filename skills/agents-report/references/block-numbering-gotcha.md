# Block Numbering Gotcha

## 问题

RSS 源的 block 结构**每天可能不同**。cron prompt 里的 block 号可能对不上脚本实际输出。

## 原因

`scripts/agents-radar-daily.py` 的 `split_blocks()` 用 `__HR__`（即 `<hr>` 标签）切分大块。上游 RSS 的 HTML 结构每天由 agents-radar 自动生成，结构不稳定。

## 2026-06-18 实测

### ai-trending（8 blocks）

| Block | 内容 | 有用？ |
|-------|------|--------|
| 1 | 标题/元信息 | ❌ |
| 2 | 引言/preamble | ❌ |
| 3 | AI 相关性筛选（只有项目名列表） | ❌ |
| **4** | **今日速览** | ✅ |
| **5** | **各维度热门项目** | ✅ |
| **6** | **趋势信号分析** | ✅ |
| 7-8 | 末尾内容 | ❌ |

### ai-agents（19 blocks）

| Block | 内容 | 有用？ |
|-------|------|--------|
| 1 | 标题 | ❌ |
| 2 | OpenClaw 深度报告 | 偏专项 |
| 3-4 | OpenClaw 今日速览 | 偏专项 |
| 5-6 | 横向生态对比 | 可选 |
| 7 | 同赛道项目详细报告（仅标题，内容在 8-19） | 标题匹配入口 |
| **10** | **Hermes Agent 项目动态日报** | ✅ |
| 8-9, 11-19 | 其他项目单独日报 | 按需 |

## 历史变迁

| 日期 | ai-agents 正文 | ai-trending 正文 |
|------|---------------|-----------------|
| 2026-06-07 | BLOCK 5 | BLOCK 6, 7 |
| 2026-06-12 | BLOCK 7 | BLOCK 3 |
| 2026-06-18 | BLOCK 10 | BLOCK 4, 5, 6 |
| 2026-07-04 | BLOCK 15-16（Hermes Agent）、BLOCK 13+（同赛道项目详细报告，含 NanoBot / NanoClaw / NullClaw / IronClaw / LobsterAI / CoPaw / ZeroClaw 等） | **BLOCK 3**（今日速览 + 各维度热门项目 + 趋势信号分析三合一），BLOCK 4 仅 footer |

## 2026-07-04 实测：block 结构再次漂移

**关键变化**：
- `ai-agents` 扩到 25 blocks，Hermes Agent 日报下移到 BLOCK 15-16。**标题匹配仍然命中**（"Hermes Agent 项目动态日报"）。
- `ai-trending` 缩到 4 blocks，**正文三段合并到 BLOCK 3**，BLOCK 4 仅 "本日报由 agents-radar 自动生成"。当前 cron prompt 里写死 `ai-trending:4,5,6` 会**全部取到 footer 或空 block**——本次 cron 跑出来的"今日速览/各维度热门项目/趋势信号"段落都缺失。

**修复建议**：把 cron prompt 的 sections 参数改成纯标题匹配：
```bash
--sections "ai-agents:Hermes Agent 项目动态日报,同赛道项目详细报告 ai-trending:今日速览,各维度热门项目,趋势信号分析"
```

如果结构稳定后再切回 block 号（更精确但脆）。

## 处理策略（推荐顺序）

### 1. 用标题匹配代替 block 号（推荐）

`--sections` 参数支持标题子串匹配（case-insensitive），比 block 号更稳定：

```bash
# 最稳：纯标题匹配
python3 skills/agents-report/scripts/agents-radar-daily.py \
  --sections "ai-agents:Hermes Agent 项目动态日报,同赛道项目详细报告 ai-trending:今日速览,各维度热门项目,趋势信号分析"

# 也可只选 ai-trending 的正文标题；不要把当天观察到的 block 号写进长期任务
```

### 2. 拉全文确认 block 结构

```bash
python3 skills/agents-report/scripts/agents-radar-daily.py --source ai-trending
python3 skills/agents-report/scripts/agents-radar-daily.py --source ai-agents
```

看 `BLOCK_COUNT:` 和 `--- BLOCK N | TITLE:` 行，找到目标内容在哪个 block。

### 3. 更新 cron prompt 的 sections 参数

找到正确 block 号/标题后，更新 cron prompt。

## 验证清单

- [ ] 运行脚本看 `BLOCK_COUNT` 和各 block 标题
- [ ] 确认目标内容在哪个 block
- [ ] 优先用标题匹配，其次用 block 号
- [ ] 更新 cron prompt
- [ ] 更新本文件的「历史变迁」表格
