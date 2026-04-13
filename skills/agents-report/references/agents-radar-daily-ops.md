# agents-radar 日报 任务操作手册

> **任务 ID：** [创建 cron 任务后获得]
> **定时：** 每日 10:00 Asia/Shanghai（`0 10 * * *`）
> **目标：** [配置为你的目标群/频道 ID]
> **最近更新：** 2026-04-13

> ⚠️ **Cron 配置关键字段（任务卡住的主因）**
> - `sessionTarget: "isolated"` — 必须在独立会话运行，否则被主会话历史卡住
> - `wakeMode: "now"`
> - `payload.model: "[model]"`
> - `payload.timeoutSeconds: 600`
> - `delivery.mode: "announce"`
> - 发送参数必须含 `accountId=main`

---

## 1. 数据来源

**脚本：** `python3 skills/agents-report/scripts/agents-radar-daily.py`

**Feed：** [agents-radar feed.xml](https://duanyytop.github.io/agents-radar/feed.xml)

**RSS 结构：**
- `ai-agents`：OpenClaw 生态日报（OpenClaw 主项目 + 12 个生态项目）
- `ai-cli`：AI CLI 工具横向对比
- `ai-trending`：GitHub Trending 趋势

---

## 2. 报告结构

【格式化要求】
- 去除所有技术编号（如 #62994、PR #123 等）
- 只保留关键信息的文字描述，不要复述技术细节
- 链接格式：[名称](URL)，简介用「」包裹

```
**📡 agents-radar 生态报告 | [日期]**
━━━━━━━━━━━━━━━━━━━━
**🌐 Agents生态趋势**
  ① [趋势1]
  ② [趋势2]
  ③ [趋势3]
  ④ [趋势4]
  ⑤ [趋势5]
📊 活跃度：[综合描述]
━━━━━━━━━━━━━━━━━━━━
**🦁 OpenClaw 专项**
①📊 今日速览：[综合描述]
②🔥 社区热点：[顿号连接]
③🐛 Bug与稳定性：[顿号连接]
④✨ 功能请求：[顿号连接]
━━━━━━━━━━━━━━━━━━━━
**📈 开源趋势信号**
  ① [引用RSS「3. 趋势信号分析」第1条，精简]
  ② [引用RSS「3. 趋势信号分析」第2条，精简]
  ③ [引用RSS「3. 趋势信号分析」第3条，精简]
━━━━━━━━━━━━━━━━━━━━
**🔥 开源热点项目（GitHub Trending）**
[分类及项目列表]
```

---

## 3. GitHub Trending 分类规则

| 条件 | 处理 |
|------|------|
| ≥2 个项目带「+X today」 | 保留独立分类 |
| <2 个项目带「+X today」 | 合并为「其他」 |
| 全部无「+X today」 | 只显示「① 其他」 |

**合并规则：** 多个不足 2 个 ★/日的分类合并为一个「其他」组，标题用 `&` 连接，如：
```
🧠 大模型/训练 & 🔍 RAG/知识库
```

---

## 4. 项目展示格式

| 类型 | 简介规则 |
|------|---------|
| ① 最热 | 一句话简介 |
| ② 其他 | 几个字简介，顿号（、）连接多个项目 |

| 类型 | 格式 |
|------|------|
| 有 ★/日 | `① 最热：[项目名](URL)「一句话简介」(+数字★/日)` |
| 无 ★/日 | `② 其他：项目名「几字简介」、项目名「几字简介」...` |

**示例：**
```
🤖 Agent基础设施
① 最热：[hermes-agent](https://github.com/NousResearch/hermes-agent)「成长型Agent框架」(+7454★/日)
② 其他：claude-mem「会话记忆」、browser-use「浏览器自动化」

🧠 大模型/训练 & 🔍 RAG/知识库
① 最热：[VoxCPM2](https://github.com/OpenBMB/VoxCPM)「无Tokenizer的端到端TTS模型」(+1278★/日)
② 其他：ragflow「RAG融合」、langchain「链式调用」...
```

---

## 5. OpenClaw 专项

**数据来源：** RSS 的 `ai-agents` 节（OpenClaw 主项目 + 12 个生态项目）

**格式：**
```
**🦁 OpenClaw 专项**
①📊 今日速览：[综合描述]
②🔥 社区热点：[顿号连接]
③🐛 Bug与稳定性：[顿号连接]
④✨ 功能请求：[顿号连接]
```

**注意：** 内容根据 RSS 实际输出的章节灵活展示，无内容则省略该节。

---

## 6. 缺失数据处理

| 情况 | 处理 |
|------|------|
| 字段无数据 | 写「信息有限，待确认」 |
| 脚本执行失败 | 发「⚠️ agents-radar 报告获取失败，请检查网络」 |
| 趋势/信号不足 | 按实际数量输出，不凑数 |
| OpenClaw 无某级内容 | 该级省略 |

---

## 7. 发送约束

```
channel: [渠道名]  # 示例：feishu
target: [你的目标 ID]
accountId: main
timeoutSeconds: 600
```

---

## 8. 相关文件

| 文件 | 路径 |
|------|------|
| RSS 脚本 | `scripts/agents-radar-daily.py` |
| Cron 配置 | 在 OpenClaw 管理界面配置 |
| 本文档 | `tasks/news/agents-radar-daily-ops.md` |
| 输出存档 | `data/news/agents-radar-YYYY-MM-DD.md` |