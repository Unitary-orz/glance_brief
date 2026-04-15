# agents-report 安装配置

## 环境要求

- Python 3
- 依赖：`pip install feedparser`

## 定时任务配置

### Cron 模板

```json
{
  "id": "ed0ceb97-cf5e-4afb-87c5-9148199e3181",
  "name": "agents-radar daily",
  "enabled": true,
  "description": "每日 OpenClaw 生态报告",
  "schedule": {
    "kind": "cron",
    "expr": "0 10 * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "model": "minimax-cn/MiniMax-M2.5",
    "timeoutSeconds": 600,
    "message": "【定时任务｜每日10:00】\n目标：抓取 agents-radar 生态日报，格式化后发送飞书群。\n\n【执行步骤】\n1. 执行脚本获取数据（一次获取两个来源，按 section 精确过滤）：\n   python3 skills/agents-report/scripts/agents-radar-daily.py \\\n     --sections \"ai-agents:3,6,7,8,13-19 ai-trending:6,7\"\n\n2. 按下方模板格式化（内容必须基于脚本真实输出）：\n\n【硬约束｜必须逐条检查】\n- 🚫 禁止出现任何 `#` 开头的编号（如 #49971、PR #123、Issue #xxx 等）\n- 🚫 禁止出现任何 `数字 + 英文` 组合的技术引用格式\n- ✅ 只保留纯文字描述：趋势名、功能名、项目名、Bug 现象等\n- ✅ 如需引用 GitHub 条目，写「[名称](链接)」，不要带编号\n\n【格式化示例】\n❌ 错误：#49971 RFC: 原生代理身份与信任验证\n✅ 正确：原生代理身份与信任验证（RFC讨论）\n\n❌ 错误：#45064 2026.3.12 内存泄漏\n✅ 正确：内存泄漏导致 CLI 命令崩溃\n\n【各板块数据来源严格映射】\n- 🌐 Agents生态趋势 → ai-agents BLOCK 13-19（趋势 1-7）\n- 🦁 今日速览 → ai-agents BLOCK 3\n- 🦁 社区热点 → ai-agents BLOCK 6（取前 5 条，去编号）\n- 🦁 Bug与稳定性 → ai-agents BLOCK 7（取前 5 条，去编号）\n- 🦁 功能请求 → ai-agents BLOCK 8（取前 5 条，去编号）\n- 📈 开源趋势信号 → ai-trending BLOCK 7（趋势 1-3）\n- 🔥 开源热点项目 → ai-trending BLOCK 6\n\n**📡 agents-radar 生态报告 | [日期]**\n━━━━━━━━━━━━━━━━━━━━\n**🌐 Agents生态趋势**\n  ① [趋势1，不含编号]\n  ② [趋势2，不含编号]\n  ③ [趋势3，不含编号]\n  ④ [趋势4，不含编号]\n  ⑤ [趋势5，不含编号]\n━━━━━━━━━━━━━━━━━━━━\n**🦁 OpenClaw 专项**\n①📊 今日速览：[综合描述]\n②🔥 社区热点：[顿号连接列表，不含编号]\n③🐛 Bug与稳定性：[顿号连接列表，不含编号]\n④✨ 功能请求：[顿号连接列表，不含编号]\n━━━━━━━━━━━━━━━━━━━━\n**📈 开源趋势信号**\n  ① [信号1，不含编号]\n  ② [信号2，不含编号]\n  ③ [信号3，不含编号]\n━━━━━━━━━━━━━━━━━━━━\n**🔥 开源热点项目（GitHub Trending）**\n\n【分类规则】\n- ★/日 数字仅标记**原文中有「+X today」**的项目\n- 分类下有 ≥2 个 ★/日 项目 → 保留独立分类\n- 分类下有 <2 个 ★/日 项目 → 与其他小分类合并为「其他」\n- 所有项目都无 ★/日 → 只显示一个「① 其他」\n\n【项目格式】\n- 有 ★/日：① 最热：[名](url)「一句话简介」(+★数★/日)\n- 无 ★/日：② 其他：名「简介」、名「简介」...\n\n3. 发送（直接发，不要附加任何说明）：\n   - channel=feishu\n   - accountId=main\n   - target=oc_76b918a1da88e33c679d6543d1ebfbe7\n   - timeoutSeconds=600\n   - **禁止附加执行摘要**\n\n【边界情况】\n- 脚本失败 → 发送「⚠️ agents-radar 报告获取失败，请检查网络」"
  },
  "delivery": {
    "mode": "none",
    "channel": "feishu",
    "to": "oc_76b918a1da88e33c679d6543d1ebfbe7",
    "accountId": "main"
  }
}
```

### 关键配置说明

| 字段 | 值 | 说明 |
|------|-----|------|
| `sessionTarget` | `"isolated"` | 必须在独立会话运行 |
| `wakeMode` | `"now"` | 定时触发后立即执行 |
| `model` | `minimax-cn/MiniMax-M2.5` | 推荐模型 |
| `timeoutSeconds` | `600` | RSS 抓取+格式化约需 3-5 分钟 |
| `delivery.mode` | `"none"` | 消息由 Agent 自行发送 |
| `delivery.to` | `oc_76b918a1da88e33c679d6543d1ebfbe7` | 飞书群 ID |

### 问题修复记录

| 日期 | 问题 | 修复 |
|------|------|------|
| 2026-04-15 | 全量输出 119+ blocks 超过 exec 显示限制 (~50KB)，导致模型捏造内容 | 添加 `--sections` 参数按 BLOCK 精确过滤，输出从 ~50KB 缩减至 ~23KB |
| 2026-04-15 | 模型生成的报告出现 `#49971` 等技术编号 | 在 prompt 中添加硬约束，禁止 `#` 编号 |

## 故障排查

| 症状 | 可能原因 | 处理 |
|------|---------|------|
| 任务卡住不结束 | 缺少 `sessionTarget: "isolated"` | 添加该字段 |
| 发送失败 | `delivery.to` 不正确或 bot 未加入群 | 确认群 ID，机器人已加入 |
| RSS 获取失败 | 网络问题或 feed 不可用 | 手动运行脚本验证 |
| 输出被截断 | 未使用 `--sections` 参数 | 添加参数过滤 block |

## 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/agents-radar-daily.py` | RSS 抓取脚本（含 `--sections` 参数） |
| `references/agents-radar-daily-ops.md` | 完整格式规范 |
| `SKILL.md` | Skill 定义（含硬约束说明） |