# Cron 任务操作手册

> 本文档是 OpenClaw Cron 任务的完整操作指南，面向人类用户和大模型 Agent。包含创建、测试、配置、故障排查的全面说明。
>
> **适用版本：** OpenClaw Cron 系统
> **最近更新：** 2026-04-13

---

## 目录

1. [核心概念](#1-核心概念)
2. [任务结构](#2-任务结构)
3. [创建任务](#3-创建任务)
4. [测试任务](#4-测试任务)
5. [配置参数详解](#5-配置参数详解)
6. [投递配置](#6-投递配置)
7. [故障排查](#7-故障排查)
8. [最佳实践](#8-最佳实践)
9. [文件位置](#9-文件位置)

---

## 1. 核心概念

### Cron 任务

定时任务，由 OpenClaw 的 cron 系统管理，在指定时间自动运行。

### 关键组件

| 组件 | 说明 |
|------|------|
| `schedule` | 时间调度：cron 表达式 |
| `payload` | 任务内容：发给 Agent 的消息 |
| `delivery` | 投递配置：结果发到哪里 |
| `sessionTarget` | 会话模式：isolated / main |
| `state` | 运行状态：上次运行时间、状态、错误计数 |

### 会话模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `"isolated"` | 独立新会话 | **推荐**。长时间任务、后台任务 |
| `"main"` | 主会话 | 短任务，不影响其他操作 |

**注意**：`sessionTarget: "isolated"` 时必须设置 `payload.kind: "agentTurn"`，否则任务被跳过。

---

## 2. 任务结构

```json
{
  "id": "unique-job-id",
  "name": "任务名称",
  "description": "任务描述",
  "enabled": true,
  "createdAtMs": 1776084000000,
  "updatedAtMs": 1776084000000,
  "schedule": {
    "kind": "cron",
    "expr": "0 17 * * 1",
    "tz": "UTC"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "kind": "agentTurn",
    "message": "【任务描述】...",
    "model": "minimax-cn/MiniMax-M2.5",
    "timeoutSeconds": 600
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "user:ou_xxx 或 chat:oc_xxx",
    "accountId": "main"
  },
  "state": {
    "nextRunAtMs": 1776144120000,
    "lastRunAtMs": 1776058189516,
    "lastRunStatus": "ok",
    "consecutiveErrors": 0,
    "lastError": null
  }
}
```

---

## 3. 创建任务

### 3.1 完整创建示例

```python
import json
import time
from datetime import datetime

d = json.load(open('/root/.openclaw/cron/jobs.json'))

job_id = f"my-task-{int(time.time())}"
run_time = int(time.time() * 1000) + 300000  # 5分钟后

new_job = {
    "id": job_id,
    "name": "我的定时任务",
    "description": "任务详细描述",
    "enabled": True,
    "createdAtMs": int(time.time() * 1000),
    "updatedAtMs": int(time.time() * 1000),
    "schedule": {
        "kind": "cron",
        "expr": "0 10 * * *",       # 每天 10:00 UTC
        "tz": "UTC"
    },
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "agentTurn",
        "message": "【任务内容】...\n\n请直接输出内容，不要加解释。",
        "model": "minimax-cn/MiniMax-M2.5",
        "timeoutSeconds": 600
    },
    "delivery": {
        "mode": "announce",
        "channel": "feishu",
        "to": "user:ou_xxxxxxxx",   # 用户 open_id
        "accountId": "main"
    },
    "state": {
        "nextRunAtMs": run_time,
        "lastRunAtMs": None,
        "lastRunStatus": None,
        "consecutiveErrors": 0,
        "lastError": None
    }
}

d['jobs'].append(new_job)
json.dump(d, open('/root/.openclaw/cron/jobs.json', 'w'), ensure_ascii=False, indent=2)
```

### 3.2 常用 Cron 表达式

| 表达式 | 说明 |
|--------|------|
| `"0 10 * * *"` | 每天 10:00 UTC |
| `"0 17 * * 1"` | 每周一 17:00 UTC |
| `"30 9 * * *"` | 每天 09:30 UTC |
| `"0 10,18 * * *"` | 每天 10:00 和 18:00 UTC |

**时区**：`tz` 字段支持 `UTC`、`Asia/Shanghai` 等。

### 3.3 目标格式

| 类型 | `to` 值格式 | 说明 |
|------|-------------|------|
| 用户 DM | `"user:ou_xxxxxxxx"` | 飞书用户 open_id |
| 群聊 | `"chat:oc_xxxxxxxx"` | 飞书群 chat_id |

---

## 4. 测试任务

### 4.1 创建测试任务

```python
# 设置 2-5 分钟后运行，给 cron 系统足够的调度时间
temp_id = f"temp-test-{int(time.time())}"
run_time = int(time.time() * 1000) + 120000  # 2分钟后

temp_job = {
    "id": temp_id,
    "name": "测试任务",
    "enabled": True,
    "schedule": {
        "kind": "cron",
        "expr": f"{minute} {hour} * * *",
        "tz": "UTC"
    },
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "agentTurn",
        "message": "测试内容...",
        "model": "minimax-cn/MiniMax-M2.5",
        "timeoutSeconds": 600
    },
    "delivery": {
        "mode": "announce",
        "channel": "feishu",
        "to": "user:ou_xxxxxxxx",
        "accountId": "main"
    },
    "state": {
        "nextRunAtMs": run_time,
        "lastRunAtMs": None,
        "lastRunStatus": None,
        "consecutiveErrors": 0
    }
}
```

### 4.2 检查测试结果

```python
import os
import json
from datetime import datetime

log_file = f'/root/.openclaw/cron/runs/{job_id}.jsonl'

if os.path.exists(log_file):
    lines = open(log_file).readlines()
    if lines:
        last = json.loads(lines[-1])
        print(f"状态: {last.get('status')}")           # ok / error / skipped
        print(f"投递: {last.get('deliveryStatus')}")    # delivered / failed
        print(f"错误: {last.get('error')}")
        print(f"内容: {last.get('summary', '')[:200]}")
```

### 4.3 测试任务状态含义

| 状态 | 含义 |
|------|------|
| `skipped` | 任务被跳过（缺少 `payload.kind`） |
| `ok` | 任务执行成功 |
| `error` | 任务执行出错（看 `error` 字段） |
| `delivered` | 结果已投递 |
| `failed` | 投递失败 |

---

## 5. 配置参数详解

### 5.1 必须配置对的字段

| 字段 | 值 | 为什么必须 |
|------|-----|-----------|
| `sessionTarget` | `"isolated"` | 防止被主会话阻塞 |
| `wakeMode` | `"now"` | 立即触发 |
| `payload.kind` | `"agentTurn"` | isolated 模式必须指定 |
| `delivery.channel` | `"feishu"` | 指定飞书 channel |
| `delivery.accountId` | `"main"` | 多账号时必须指定 |
| `payload.timeoutSeconds` | `>= 300` | bitable 等操作需要时间 |

### 5.2 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `isolated job requires payload.kind=agentTurn` | 缺少 `payload.kind` | 添加 `"kind": "agentTurn"` |
| `Channel is required when multiple channels configured` | 缺少 `delivery.accountId` | 添加 `"accountId": "main"` |
| `Request failed with status code 400` | 内容格式问题或权限问题 | 检查 content 和 accountId |
| 任务从未运行，`lastRunAtMs` 为 null | `nextRunAtMs` 被设为过去时间 | 用未来的 cron 表达式 |

### 5.3 可选配置

| 字段 | 默认值 | 说明 |
|------|-------|------|
| `payload.model` | `minimax-cn/MiniMax-M2.5` | 指定模型 |
| `delivery.mode` | `"announce"` | 投递模式 |

---

## 6. 投递配置

### 6.1 delivery.mode

| 模式 | 说明 |
|------|------|
| `"announce"` | 发送任务结果，带系统标识 |
| `"forward"` | 直接转发结果 |
| `"none"` | 不投递 |

### 6.2 飞书投递参数

```json
"delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "user:ou_xxxxxxxx",       // 或 "chat:oc_xxxxxxxx"
    "accountId": "main"              // 必须指定
}
```

**注意**：`accountId` 必须与机器人配置的多账号匹配。常见值：`"main"`、`"en"` 等。

---

## 7. 故障排查

### 7.1 任务没运行

1. 检查 `enabled` 是否为 `true`
2. 检查 `nextRunAtMs` 是否在未来时间
3. 检查 cron 表达式是否正确：`"分 时 * * *"`（UTC）
4. 查看日志文件是否存在

### 7.2 任务运行但没投递

1. 检查 `delivery.channel` 和 `accountId` 是否正确
2. 检查 `delivery.to` 格式是否正确（`user:` 或 `chat:` 前缀）
3. 查看 `deliveryStatus` 和 `error` 字段

### 7.3 400 错误

通常是以下原因：
- `accountId` 缺失或错误
- 内容格式不被飞书接受（如超长内容）
- 权限问题（机器人没有发消息到该用户/群的权限）

### 7.4 日志位置

```
/root/.openclaw/cron/runs/{job_id}.jsonl
```

每条日志是 JSONL 格式，包含：
- `action`: `finished`
- `status`: `ok` / `error` / `skipped`
- `summary`: 任务输出内容
- `deliveryStatus`: 投递状态
- `error`: 错误信息（如果有）

---

## 8. 最佳实践

### 8.1 任务命名

- 测试任务：`temp-test-{timestamp}` 或 `temp-{功能名}-{timestamp}`
- 正式任务：简短描述性名称，如 `每日-采购提醒`

### 8.2 测试流程

1. 先用 temp job 测试
2. 确认成功后，再更新正式任务
3. 每次测试后清理旧测试任务

### 8.3 清理测试任务

```python
for j in d['jobs']:
    if j['id'].startswith('temp-') or 'test' in j['id'].lower():
        j['enabled'] = False  # 软删除
```

### 8.4 编写任务描述

好的描述：
```
【每周采购规划｜周一采购日】
今天是周一，结合库存现状，帮我规划一下这周的采购清单。
```

差的描述：
```
库存提醒任务
```

### 8.5 任务内容模板

```markdown
【任务标题｜场景说明】

背景：（可选）为什么要做这个任务

请读取飞书多维表格（app_token=xxx, table_id=xxx）

---

模块一：标题
内容要求...

模块二：标题
内容要求...

---

格式要求：
- 简洁，不啰嗦
- 直接输出内容
- 不要加解释性文字
```

---

## 9. 文件位置

| 文件 | 路径 |
|------|------|
| Cron 任务配置 | `/root/.openclaw/cron/jobs.json` |
| Cron 运行日志 | `/root/.openclaw/cron/runs/{job_id}.jsonl` |
| OpenClaw 配置 | `/root/.openclaw/config.json` |
| Workspace | `/root/.openclaw/workspace-lionclaw/` |

---

## 附录：常用飞书 ID

| 目标 | ID 格式 | 示例 |
|------|---------|------|
| 用户 | `user:ou_xxx` | `user:ou_2a1d6ab74d78f529af95ea08e4f60d19` |
| 群 | `chat:oc_xxx` | `chat:oc_76b918a1da88e33c679d6543d1ebfbe7` |

---

**更新记录**

| 日期 | 变更 |
|------|------|
| 2026-04-15 | agents-radar 日报：添加 `--sections` 参数解决输出截断问题，新增硬约束禁止 `#` 编号 |
| 2026-04-13 | 新增「投递配置」和「故障排查」章节 |
| 2026-04-08 | 初始版本 |
| 2026-04-13 | 初始版本，包含创建、测试、配置、故障排查完整指南 |
