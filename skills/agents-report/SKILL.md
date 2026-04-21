---
name: agents-report
description: >-
  每日 OpenClaw 生态报告（agents-radar）定时任务 Skill。
  抓取 agents-radar RSS，格式化后发送至配置的消息渠道。
  使用时机：用户要求查看 OpenClaw 生态日报、Agents 趋势、GitHub Trending。
---

# agents-report

每日 OpenClaw 生态报告（agents-radar）。

## 数据来源

- **脚本：** `python3 skills/agents-report/scripts/agents-radar-daily.py --sections "ai-agents:2,5,6,7,13-18 ai-trending:6,7"`
- **Feed：** https://duanyytop.github.io/agents-radar/feed.xml
- **RSS 分区：**
  - `ai-agents`：OpenClaw 生态日报（13 个项目，119 个 blocks）
  - `ai-cli`：AI CLI 工具横向对比
  - `ai-trending`：GitHub Trending 趋势（9 个 blocks）

## BLOCK 过滤说明

全量输出（119+9 blocks）超过 exec 工具显示限制（~50KB），导致模型捏造内容。
使用 `--sections` 参数精确过滤：

| Source | BLOCK | 内容 |
|--------|-------|------|
| ai-agents | 2 | 今日速览 |
| ai-agents | 5 | 社区热点 |
| ai-agents | 6 | Bug 与稳定性 |
| ai-agents | 7 | 功能请求与路线图信号 |
| ai-agents | 13-18 | 各项目活跃度对比、OpenClaw生态定位、技术方向、趋势信号（6条） |
| ai-trending | 6 | 今日速览 |
| ai-trending | 7 | 各维度热门项目（GitHub Trending） |

输出规模：~23KB（13 blocks）

## 硬约束

**🚫 禁止出现任何 `#` 编号**（如 `#49971`、`PR #123`、`Issue #xxx`）
**✅ 只保留纯文字描述**

示例：
- ❌ `#49971 RFC: 原生代理身份与信任验证`
- ✅ `RFC 原生代理身份与信任验证`

## 报告结构

```
**📡 agents-radar 生态报告 | [日期]**
━━━━━━━━━━━━━━━━━━━━
**🌐 Agents生态趋势**     ← BLOCK 13-18（6条），不含编号
━━━━━━━━━━━━━━━━━━━━
**🦁 OpenClaw 专项**    ← OpenClaw 专项动态
①📊 今日速览（BLOCK 2）
②🔥 社区热点（BLOCK 5），不含编号
③🐛 Bug与稳定性（BLOCK 6），不含编号
④✨ 功能请求（BLOCK 7），不含编号
━━━━━━━━━━━━━━━━━━━━
**📈 开源趋势信号**       ← ai-trending BLOCK 6 今日速览
━━━━━━━━━━━━━━━━━━━━
**🔥 开源热点项目**      ← ai-trending BLOCK 7 各维度热门项目，按★/日分类
```

## 核心格式规则

**GitHub Trending 分类合并：**
- ≥2 个 ★/日项目 → 独立分类
- <2 个 ★/日项目 → 合并为「其他」
- ★/日 仅标记原文有「+X today」的项目

**OpenClaw 专项：**
- 章节用顿号连接，不换行
- 可选章节，无内容则省略
- **禁止出现 `#` 编号**

## 定时任务配置

参见 `INSTALL.md`。

## 详细文档

见 `references/agents-radar-daily-ops.md`