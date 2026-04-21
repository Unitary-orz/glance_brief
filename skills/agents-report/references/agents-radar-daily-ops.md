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

**脚本：** `python3 skills/agents-report/scripts/agents-radar-daily.py --sections "ai-agents:2,5,6,7,13-18 ai-trending:6,7"`

**Feed：** [agents-radar feed.xml](https://duanyytop.github.io/agents-radar/feed.xml)

**RSS 结构：**
- `ai-agents`：OpenClaw 生态日报（13 个项目，119 个 blocks）
- `ai-cli`：AI CLI 工具横向对比
- `ai-trending`：GitHub Trending 趋势（9 个 blocks）

**BLOCK 过滤参数（解决输出截断问题）：**

| Source | BLOCK | 内容 |
|--------|-------|------|
| ai-agents | 2 | 今日速览 |
| ai-agents | 5 | 社区热点 |
| ai-agents | 6 | Bug 与稳定性 |
| ai-agents | 7 | 功能请求与路线图信号 |
| ai-agents | 13-18 | 各项目活跃度/OpenClaw生态定位/技术方向/差异化/社区分层/趋势信号（6条） |
| ai-trending | 6 | 今日速览 |
| ai-trending | 7 | 各维度热门项目（GitHub Trending） |

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

## 5. 项目展示格式（2026-04-15 修复）

**所有项目必须有完整链接！**

| 类型 | 格式 |
|------|------|
| 有 ★/日 | `① 最热：[项目名](https://github.com/owner/repo)「一句话简介」(+数字★/日)` |
| 无 ★/日 | `② 其他：[项目名](https://github.com/owner/repo)「简介」、[项目名](https://github.com/owner/repo)「简介」...` |

**示例：**
```
🔧 AI 基础工具
① 最热：[hermes-agent](https://github.com/NousResearch/hermes-agent)「可进化Agent框架」(+8301★/日)
② 其他：[claude-mem](https://github.com/thedotmack/claude-mem)「会话记忆」、[markitdown](https://github.com/microsoft/markitdown)「文档转换」

📦 AI 应用 & 🧠 大模型/训练 & 🔍 RAG/知识库
① 最热：[voicebox](https://github.com/jamiepine/voicebox)「开源语音合成」(+1162★/日)
② 其他：[Kronos](https://github.com/shiyu-coder/Kronos)「金融基础模型」、[ragflow](https://github.com/infiniflow/ragflow)「RAG引擎」
```

---

## 6. 发送约束

```
channel: feishu
target: oc_76b918a1da88e33c679d6543d1ebfbe7
accountId: main
timeoutSeconds: 600
```

---

## 7. 已知问题修复历史

| 日期 | 问题 | 修复 |
|------|------|------|
| 2026-04-15 | exec 输出截断（~50KB） | 新增 `--sections` 参数精确过滤 BLOCK |
| 2026-04-15 | #编号残留 | 添加禁止编号硬约束 |
| 2026-04-15 | "其他"项目无链接 | 明确要求所有项目必须有链接 |
| 2026-04-15 | hermes-agent 重复显示 | 规则优化，合并小分类 |

---

## 8. 相关文件

| 文件 | 路径 |
|------|------|
| RSS 脚本 | `scripts/agents-radar-daily.py` |
| Cron 配置 | `/root/.openclaw/cron/jobs.json` |
| 本文档 | `references/agents-radar-daily-ops.md` |
| 输出存档 | `data/news/agents-radar-YYYY-MM-DD.txt` |
