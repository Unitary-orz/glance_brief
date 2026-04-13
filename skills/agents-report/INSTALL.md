# agents-report 安装配置

## 环境要求

- Python 3
- 依赖：`pip install feedparser`

## 定时任务配置

### Cron 模板

```json
{
  "id": "[创建后获得的 Job ID]",
  "name": "agents-report",
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
    "model": "[model]",
    "timeoutSeconds": 600,
    "message": "【定时任务｜每日10:00】\n抓取 agents-radar 生态日报，格式化后发送至配置的消息渠道。\n\n【执行步骤】\n1. 执行脚本获取原始数据：\n   python3 skills/agents-report/scripts/agents-radar-daily.py\n\n2. 按下方模板格式化（内容必须基于脚本真实输出）：\n\n📡 agents-radar 生态报告 | [日期]\n━━━━━━━━━━━━━━━━━━━━\n**🌐 Agents生态趋势**\n  ① [趋势1]\n  ② [趋势2]\n  ③ [趋势3]\n  ④ [趋势4]\n  ⑤ [趋势5]\n📊 活跃度：[综合描述]\n━━━━━━━━━━━━━━━━━━━━\n**🦁 OpenClaw 专项**\n①📊 今日速览：[综合描述]\n②🔥 社区热点：[顿号连接]\n③🐛 Bug与稳定性：[顿号连接]\n④✨ 功能请求：[顿号连接]\n━━━━━━━━━━━━━━━━━━━━\n**📈 开源趋势信号**\n  ① [引用RSS「3. 趋势信号分析」第1条，精简]\n  ② [引用RSS「3. 趋势信号分析」第2条，精简]\n  ③ [引用RSS「3. 趋势信号分析」第3条，精简]\n━━━━━━━━━━━━━━━━━━━━\n**🔥 开源热点项目（GitHub Trending）**\n\n【分类规则】\n- ★/日 数字仅标记原文中有「+X today」的项目\n- ≥2 个 ★/日 → 独立分类\n- <2 个 ★/日 → 合并为「其他」\n- 所有项目都无 ★/日 → 只显示「① 其他」\n- 每个分类只显示一个「其他」，不重复\n\n【项目格式】\n- 有 ★/日：① 最热：[名](url)「简介」(+★数★/日)\n- 无 ★/日：② 其他：名「简介」、名「简介」...\n\n【分类示例】\n🤖 Agent基础设施\n① 最热：[hermes-agent](...)「成长型Agent框架」(+7454★/日)\n② 其他：claude-mem「会话记忆」、browser-use「浏览器自动化」\n\n📦 垂直应用\n① 最热：[Kronos](...)「金融基础模型」(+1985★/日)\n\n🧠 大模型/训练 & 🔍 RAG/知识库\n① 最热：[VoxCPM2](...)「无TokenizerTTS」(+1278★/日)\n② 其他：ragflow「RAG融合」\n\n3. 发送（直接发，不要附加说明）：\n   - channel=feishu\n   - target=[你的飞书群 ID]\n   - accountId=main\n   - timeoutSeconds=600\n\n【边界情况】\n- 脚本失败 → 发送「⚠️ agents-radar 报告获取失败，请检查网络」"
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu",  // 示例，改为你的实际渠道
    "to": "[你的目标 ID]",
    "accountId": "main"
  }
}
```

### 关键配置说明

| 字段 | 说明 |
|------|------|
| `sessionTarget: "isolated"` | 必须在独立会话运行，否则被主会话历史卡住 |
| `wakeMode: "now"` | 定时触发后立即执行 |
| `model` | 推荐 `[model]` |
| `timeoutSeconds` | 建议 600s，RSS 抓取+格式化约需 3-5 分钟 |
| `delivery.to` | 目标平台的频道 ID（如飞书群 `oc_xxx`、Telegram `@channel` 等） |

## 故障排查

| 症状 | 可能原因 | 处理 |
|------|---------|------|
| 任务卡住不结束 | 缺少 `sessionTarget: "isolated"` | 添加该字段 |
| 发送失败 | `delivery.to` 不正确或 bot 未加入群 | 确认群 ID，机器人已加入 |
| RSS 获取失败 | 网络问题或 feed 不可用 | 手动运行脚本验证 |

## 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/agents-radar-daily.py` | RSS 抓取脚本 |
| `references/agents-radar-daily-ops.md` | 完整格式规范（参考） |
