# agents-radar 日报 任务操作手册

> **任务 ID：** `ed0ceb97-cf5e-4afb-87c5-9148199e3181`
> **定时：** 每日 10:00 Asia/Shanghai（`0 10 * * *`）
> **目标：** 飞书群 `oc_76b918a1da88e33c679d6543d1ebfbe7`
> **最近更新：** 2026-04-15

> ⚠️ **Cron 配置关键字段**
> - `sessionTarget: "isolated"` — 必须在独立会话运行
> - `wakeMode: "now"`
> - `payload.model: "minimax-cn/MiniMax-M2.5"`
> - `payload.timeoutSeconds: 600`
> - `delivery.mode: "none"`（消息由 Agent 自行发送）
> - 发送参数必须含 `accountId=main`

---

## 1. 数据来源

**脚本：** `python3 skills/agents-report/scripts/agents-radar-daily.py --sections "ai-agents:3,6,7,8,13-19 ai-trending:6,7"`

**Feed：** [agents-radar feed.xml](https://duanyytop.github.io/agents-radar/feed.xml)

**RSS 结构：**
- `ai-agents`：OpenClaw 生态日报（13 个项目，119 个 blocks）
- `ai-cli`：AI CLI 工具横向对比
- `ai-trending`：GitHub Trending 趋势（9 个 blocks）

**BLOCK 过滤参数（解决输出截断问题）：**

| Source | BLOCK | 内容 |
|--------|-------|------|
| ai-agents | 3 | 今日速览 |
| ai-agents | 6 | 社区热点 |
| ai-agents | 7 | Bug 与稳定性 |
| ai-agents | 8 | 功能请求与路线图信号 |
| ai-agents | 13-19 | 生态趋势（7条） |
| ai-trending | 6 | 各维度热门项目（GitHub Trending） |
| ai-trending | 7 | 趋势信号分析 |

**输出规模：** ~23KB（13 blocks）vs 全量 ~50KB（128 blocks）

---

## 2. 硬约束（2026-04-15 新增）

**🚫 禁止出现：**
- `#` 开头的编号（如 `#49971`、`PR #123`、`Issue #xxx`）
- 任何 `数字 + 英文` 组合的技术引用格式

**✅ 正确格式：**
- 原：`#49971 RFC: 原生代理身份与信任验证`
- 新：`RFC 原生代理身份与信任验证`

- 原：`#45064 内存泄漏导致 CLI 命令崩溃`
- 新：`内存泄漏导致 CLI 命令崩溃`

---

## 3. 报告结构

```
**📡 agents-radar 生态报告 | [日期]**
━━━━━━━━━━━━━━━━━━━━
**🌐 Agents生态趋势**
  ① [趋势1，不含编号]
  ② [趋势2，不含编号]
  ③ [趋势3，不含编号]
  ④ [趋势4，不含编号]
  ⑤ [趋势5，不含编号]
━━━━━━━━━━━━━━━━━━━━
**🦁 OpenClaw 专项**
①📊 今日速览：[综合描述]
②🔥 社区热点：[顿号连接，不含编号]
③🐛 Bug与稳定性：[顿号连接，不含编号]
④✨ 功能请求：[顿号连接，不含编号]
━━━━━━━━━━━━━━━━━━━━
**📈 开源趋势信号**
  ① [信号1，不含编号]
  ② [信号2，不含编号]
  ③ [信号3，不含编号]
━━━━━━━━━━━━━━━━━━━━
**🔥 开源热点项目（GitHub Trending）**
[分类及项目列表]
```

---

## 4. GitHub Trending 分类规则

| 条件 | 处理 |
|------|------|
| ≥2 个项目带「+X today」 | 保留独立分类 |
| <2 个项目带「+X today」 | 合并为「其他」 |
| 全部无「+X today」 | 只显示「① 其他」 |

**合并规则：** 多个不足 2 个 ★/日的分类合并为一个「其他」组，标题用 `&` 连接。

---

## 5. 项目展示格式

| 类型 | 格式 |
|------|------|
| 有 ★/日 | `① 最热：[项目名](URL)「一句话简介」(+数字★/日)` |
| 无 ★/日 | `② 其他：项目名「几字简介」、项目名「几字简介」...` |

---

## 6. 发送约束

```
channel: feishu
target: oc_76b918a1da88e33c679d6543d1ebfbe7
accountId: main
timeoutSeconds: 600
```

---

## 7. 相关文件

| 文件 | 路径 |
|------|------|
| RSS 脚本 | `scripts/agents-radar-daily.py` |
| Cron 配置 | `/root/.openclaw/cron/jobs.json` |
| 本文档 | `references/agents-radar-daily-ops.md` |
| 输出存档 | `data/news/agents-radar-YYYY-MM-DD.txt` |