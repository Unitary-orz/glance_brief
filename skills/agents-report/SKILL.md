---
name: agents-report
description: >-
  每日 OpenClaw 生态报告（agents-radar）定时任务 Skill。
  抓取 agents-radar RSS，格式化后发送飞书群。
  使用 when: 用户要求查看 OpenClaw 生态日报、Agents 趋势、GitHub Trending。
---

# agents-report

每日 OpenClaw 生态报告（agents-radar）。

## 定时任务

- **Job ID：** `ed0ceb97-cf5e-4afb-87c5-9148199e3181`
- **定时：** 每日 10:00 Asia/Shanghai（`0 10 * * *`）
- **发送目标：** 飞书群 `oc_76b918a1da88e33c679d6543d1ebfbe7`

## Cron 配置关键字段

```json
{
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "model": "minimax-cn/MiniMax-M2.5",
    "timeoutSeconds": 600
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "oc_76b918a1da88e33c679d6543d1ebfbe7",
    "accountId": "main"
  }
}
```

## 数据来源

- **脚本：** `scripts/agents-radar-daily.py`
- **Feed：** https://duanyytop.github.io/agents-radar/feed.xml
- **RSS 分区：**
  - `ai-agents`：OpenClaw 生态日报（主项目 + 12 个生态项目）
  - `ai-cli`：AI CLI 工具横向对比
  - `ai-trending`：GitHub Trending 趋势

## 报告结构

```
**📡 agents-radar 生态报告 | [日期]**
━━━━━━━━━━━━━━━━━━━━
**🌐 Agents生态趋势**     ← 5条趋势
📊 活跃度：[综合描述]
━━━━━━━━━━━━━━━━━━━━
**🦁 OpenClaw 专项**    ← OpenClaw 专项动态
①📊 今日速览
②🔥 社区热点
③🐛 Bug与稳定性
④✨ 功能请求
━━━━━━━━━━━━━━━━━━━━
**📈 开源趋势信号**       ← 3条趋势信号
━━━━━━━━━━━━━━━━━━━━
**🔥 开源热点项目**      ← GitHub Trending，按★/日分类
```

## 核心格式规则

**GitHub Trending 分类合并：**
- ≥2 个 ★/日项目 → 独立分类
- <2 个 ★/日项目 → 合并为「其他」
- ★/日 仅标记原文有「+X today」的项目

**OpenClaw 专项：**
- 章节用顿号连接，不换行
- 可选章节，无内容则省略

## 详细文档

见 `references/agents-radar-daily-ops.md`
