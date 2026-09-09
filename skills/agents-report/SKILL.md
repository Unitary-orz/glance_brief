---
name: agents-report
description: >-
  每日 AI / Agents 生态报告 Skill。整合 AI HOT、CodexRadar、agents-radar
  和本地开源雷达，按 glance_brief v0.3.0 契约生成可追溯报告。
triggers:
  - agents-report
  - agents-radar
  - AI 开源雷达
  - AI 生态日报
---

# agents-report — glance_brief v0.3.0

## 正式入口

两份报告共享项目级 `glance_brief` core。仓库 CLI 用于配置检查、离线运行和 replay：

```bash
python3 -m glance_brief check --config config/brief.example.json
python3 -m glance_brief probe --config config/brief.example.json --report agents-report
```

Hermes 安装后使用 `glance-brief/agents-report.py`。该入口完成来源读取、一次模型调用、严格解析、resolver、确定性渲染和 artifacts；Cron 使用 `no_agent: true`，不再附加外层 Prompt。`no_agent` 只关闭外层 Agent，不表示无模型调用。

独立 Preview 也可以使用 `prepare → Cron Agent 写 semantic JSON → render-prepared` handoff；它只验证外层 Agent 模式，不授权修改正式任务。两种模式都必须保持一次来源快照、单轮语义模型、严格 resolver 和确定性 renderer。

`agents_radar_prefetch.py`、`agents-radar-daily.py`、`codexradar_efficiency.py` 等是 producer/utility，不是最终报告入口，也不发送报告。

## 数据来源

- AI HOT：AI 生态动态；
- CodexRadar：producer-owned 模型效率 Markdown；
- agents-radar / 本地开源雷达：hot、fresh、分类与项目事实。

真实路径与用户配置由 runtime adapter 提供，不写入 Skill。

## 所有权边界

模型只负责把 AI HOT 候选先按事件、进展或明确互补主题聚类，再从中选择最多三条代表生态变化的动态；每条动态写 `candidate_ids` 数组、短导语和高密度摘要，并为程序提供的展示项目翻译简介和恰好两条总体趋势。候选池达到 5 条时默认争取覆盖至少 5 个候选 ID，但不得为覆盖而强行合并不相关事件。AI 动态摘要可以保留对应候选证据中的产品名、组织名、模型名和关键数字，但不得补充候选外事实，也不得输出 URL、来源、RSS/feed/抓取等采集实现细节。模型不得返回日期、指标、fresh、分类、Codex 内容或 Markdown；项目简介翻译必须逐个覆盖 `open_source_display_ids`，且只能根据对应候选文本。

程序负责：

- 从 candidate registry 回填并合并多候选 AI 动态的来源；AIHOT 条目页只保留在内部 provenance，不在 AI 动态可见来源行展示；可见来源取原文或直接来源，同一发布方去重，社交平台短帖在有完整原文时降级，每条最多展示两个来源并隐藏 `RSS`、`网页` 等传输标签，但不改变 URL；没有可见原文时明确显示“暂无可见原文”，不得回退展示 AIHOT 条目页；
- 验证并逐字插入 `codexradar.markdown`；
- 从 `hot_today`、`fresh_hot`、`local_report_categories` 恢复项目事实；
- 将模型的 `open_source_descriptions[].description_zh` 绑定回实际展示项目；
- 验证 GitHub URL、quality、fresh 子集和分类唯一完整覆盖；
- deterministic render、manifest 和 replay。

完整语义契约见 `glance_brief/prompts/agents-report.md`，可见格式见 `docs/output-contracts.md`。

## 固定结构

1. `🤖 AI 生态动态`；
2. producer-owned CodexRadar block；
3. `🔥 开源热点趋势`；
4. 非空时唯一的 `✨新热门开源`；
5. `📦**最热门开源**`；
6. producer 分类板块。

AI 动态行使用 `- ① **topic**：summary（来源：[来源A](URL) · [来源B](URL)）`；topic 为 4–8 字纯文本短导语，由 renderer 统一加粗，来源之间使用 ` · `。开源项目板块在 fresh 项目之后先放独立的 `📦**最热门开源**` 标题，再进入分类标题；每类保留原始顺序前 1–3 个项目，并把同类项目压缩到同一条列表行，用 ` · ` 连接；分类项目行直接从 Markdown 链接开始，不添加 `热门项目：`、`最热：` 或 `其他：` 前缀。

独立本地雷达的 `new_projects` 不在主报告重复展示。

## 失败处理

- 必选来源失败、候选不足、雷达 quality 非 `ok`、Codex block 缺失、fresh/category/project 契约失败：模型调用前或 renderer 前 hard fail；
- 非 required 来源失败：记录 `source_errors`，其余来源可继续；
- malformed 模型响应：保留 raw response、`failure.json` 和 failed manifest，不生成 `report.md`；
- 不用常识、旧缓存或搜索结果补写 producer 未提供的项目事实。

## 配置与发布边界

- `config/brief.example.json` 只用于离线结构示例；安装后必须创建真实 schema 2 `brief.json`；
- 模型/provider/timeout、schedule 和 delivery 属于 runtime adapter；
- OpenClaw 在 v0.3.0 仅有 adapter contract，没有可运行 Job；
- 真实配置不得提交；Runtime/Cron 变更必须先 dry-run，并获得明确授权。
