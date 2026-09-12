# glance_brief v0.3.0 Architecture

## 目标

把来源事实、模型语义和最终格式分开，使两份日报可追溯、可回放、可在不同 Agent runtime 中运行，并在任一契约失败时 fail closed。

## 数据流

```text
外部来源
  ↓
producer / prefetch（来源调用、重试、原始 JSON）
  ↓
bounded input adapters（json_file / command_json / snapshot_json）
  ↓
source view + normalization（每个来源只看到自己的 snapshot 路径）
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
- 将来源映射为有稳定 `candidate_id` 的 registry；Noon lean payload 再从规范化后的标题/正文确定性派生 `title_only`；
- 拒绝标题或证据文本中夹带 URL 等不安全候选，并记录 `candidate_rejections`；对已明确配置 `strip_urls_from_text` 的来源，只删除正文/description 中的 URL，独立 provenance URL 不受影响；
- 执行来源级 `required`、原始记录 `exclude` 和报告级 `minimum_candidates`；exclude 在候选构造及 `take` 之前执行。

不负责摘要、翻译或最终 Markdown。

### 模型

只负责：

- 将 payload 内的 AI 候选先按事件、进展或明确互补主题聚类，再选择最多三个生态变化切片；每条用 `candidate_ids` 绑定 1–3 个候选，候选池达到 5 条时默认争取覆盖至少 5 个候选，全文不得复用 ID；
- 为每条 AI 动态写短 `topic` 和高密度事实摘要；同簇事实可用分号并列，但摘要只能使用绑定候选证据的并集，不得补出跨候选因果；
- 为英文原题提供可选中文对照；Noon 纯标题候选省略摘要且只展示标题与来源，有独立正文的候选仍须提供标题之外的摘要；
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

## V2 Preview 的 source-owned 边界

当前已验证的 V2 Preview 暂不覆盖正式 `glance_brief/` v0.3.0 包，而是
完整保存在 `runtime/preview/`。这是 live V2 的可重建源码边界，包含
入口、共享 core、Prompt、schema-v3 配置样例、离线 snapshot、Cron handoff
prompt 和边界测试。默认正式 installer 不会触碰它；显式使用
`install/install.py install --runtime hermes-preview` 时，installer 按
manifest 将完整依赖闭包映射到 `scripts/glance-brief-v2/`，记录 source
revision/owned-file hashes，并仍然不自动修改 Cron 或投递。

V2 的来源输入分为三类：`json_file` 和 `command_json` 负责得到一个独立
payload，`snapshot_json` 只返回报告已加载的不可变 snapshot。所有来源都
经同一个注册表进入 `load_source`，再由映射层规范化；assembler 不再针对
`report_json` 写来源分支。`report_json` 仅保留为兼容别名，新的配置使用
`snapshot_json`。

Wrapper 只负责运行 producer、锁、路径和 handoff；required source、最小候选
数和质量门禁由 Report Plan/core 统一执行。来源专用的 local-radar 发布物
解析位于 `local_radar_publication.py`，不再散落在入口 wrapper。

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
