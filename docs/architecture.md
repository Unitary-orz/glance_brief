# Architecture

## 目标

让同一套简报逻辑可以在不同 Agent runtime 中运行，同时降低同步、排错和格式回归的成本。

## 分层

```text
外部来源
  │
  ▼
预取层（Python，输出 JSON）
  │
  ├── agents-radar collector
  ├── AI HOT client
  ├── CodexRadar reader/ranker
  └── news-aggregator / RSS collectors
  │
  ▼
数据契约（schema_version: 1）
  │
  ▼
Prompt / Skill 层
  │
  ├── 事实边界
  ├── 来源字段映射
  ├── Markdown 输出结构
  └── Self-check 规则
  │
  ▼
Runtime adapter
  │
  ├── Hermes Cron
  └── OpenClaw Cron
  │
  ▼
消息渠道
```

## 组件职责

### 预取脚本

预取脚本只负责：

- 调用来源
- 重试和超时
- 保留来源 URL 和原始字段
- 返回成功 / 失败状态
- 输出 JSON

预取脚本不负责：

- 生成最终新闻摘要
- 改写来源 URL
- 决定 Feishu / Telegram 等投递方式
- 输出最终报告 Markdown

### Prompt / Skill

Prompt 只负责：

- 如何使用已经预取的数据
- 如何去重和压缩
- 如何保持固定排版
- 如何在证据不足时降级

Prompt 不应再次调用网络工具或脚本。

### Runtime adapter

Adapter 负责：

- Cron 时间和时区
- 脚本路径
- 外部 Skill 路径
- 本地配置路径
- 模型和投递目标

真实 Job ID、聊天 ID、模型和凭据不能进入通用 Skill。

## 重要设计取舍

当前不把项目改造成 `src/glance_brief` Python package。脚本需要被 Cron 直接执行，保持 standalone scripts 可以降低安装成本和运行时耦合。

只有在公共模块重复明显、并且已经有测试覆盖后，才抽取 shared library；不要为了形式上的“标准化”提前增加抽象层。

## 数据流约束

- 每次任务只预取一次。
- Prompt 直接读取预取 JSON。
- 来源失败只影响对应板块。
- 不跨来源补写没有证据的内容。
- 所有输出格式变化必须先更新输出契约和快照测试。
