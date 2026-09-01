# glance_brief v0.3.0 Architecture

## 目标

把来源事实、模型语义和最终格式分开，使两份日报可追溯、可回放、可在不同 Agent runtime 中运行，并在任一契约失败时 fail closed。

## 数据流

```text
外部来源
  ↓
producer / prefetch（来源调用、重试、原始 JSON）
  ↓
bounded adapters（json_file / command_json）
  ↓
immutable candidate registry（事实与 provenance）
  ↓
lean semantic payload（无 URL、日期、来源 metadata、指标或 Markdown）
  ↓
单轮模型 JSON（选择、摘要、翻译、趋势）
  ↓
resolver（candidate_id 回填不可变事实）
  ↓
strict validator
  ↓
deterministic renderer
  ↓
report.md + manifest.json + replay artifacts
  ↓
runtime adapter / delivery
```

## 所有权边界

### Producer 与 adapter

负责：

- 调用来源、重试、超时和受控环境；
- 保留原始 URL、标题、发布时间、项目身份、指标和分类；
- 将来源映射为有稳定 `candidate_id` 的 registry；
- 拒绝标题或证据文本中夹带 URL 等不安全候选，并记录 `candidate_rejections`；对已明确配置 `strip_urls_from_text` 的来源，只删除正文/description 中的 URL，独立 provenance URL 不受影响；
- 执行来源级 `required`、原始记录 `exclude` 和报告级 `minimum_candidates`；exclude 在候选构造及 `take` 之前执行。

不负责摘要、翻译或最终 Markdown。

### 模型

只负责：

- 将 payload 内的 AI 候选先按事件、进展或明确互补主题聚类，再选择最多三个生态变化切片；每条用 `candidate_ids` 绑定 1–3 个候选，候选池达到 5 条时默认争取覆盖至少 5 个候选，全文不得复用 ID；
- 为每条 AI 动态写短 `topic` 和高密度事实摘要；同簇事实可用分号并列，但摘要只能使用绑定候选证据的并集，不得补出跨候选因果；
- 为英文原题提供可选中文对照；
- 根据对应候选文本，为程序已确定展示的项目填写中文简介；
- 写不含项目身份和指标的总体趋势。

模型不得返回 URL、来源、日期、项目身份、指标、Markdown，不得添加候选外事实或自行换算数字；AI 动态不得泄露 RSS/feed/网页采集等来源管线细节；项目简介翻译必须逐个覆盖程序提供的展示项目 ID。

### Resolver、validator 与 renderer

负责：

- 只接受 registry 中的候选 ID，并验证多候选分组的数量、范围、去重和证据数字并集；
- 从 registry 回填原题、URL、来源、时间、项目身份、指标和分类；
- 验证数字 provenance、选择数量、安全文本、GitHub URL 和 producer quality；
- 生成固定 Markdown；
- 在失败时删除旧 `report.md`，保留 raw response、诊断和 failed manifest。

### Runtime adapter

只负责本地路径、配置、模型/provider、Cron 时间、投递目标、锁和超时。真实 Job ID、聊天 ID、凭据和用户配置不得进入仓库。

## 版本与协议

- 仓库版本：`v0.3.0`；
- producer 输入可继续使用 `schema_version: 1`，由 adapters 消化；
- canonical / resolved 报告使用 `schema_version: 2`；
- `glance_brief/` 是两份报告共用的正式业务包；
- 不支持旧模型响应、legacy fixture、converter 或多协议运行分支。

## 运行约束

- 每次任务只采集一次来源快照；
- `command_json` 必须使用 argv、受控 cwd、timeout 和环境 allowlist；
- 模型调用为单轮，不能调用 producer 工具；可由 batch adapter 直接调用，也可由外层 Cron Agent 只填写 run-scoped semantic JSON；
- agent-mode handoff 的 render 必须验证 config 与 prepared artifact SHA-256，并从已保存 registry 渲染，不重新读取来源；
- 每次运行使用独立 artifact 目录；
- replay 先验证 manifest SHA-256，不重新读取来源或调用模型；
- 正式 installer/Cron 切换必须作为单独变更并明确授权。
