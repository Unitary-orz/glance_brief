# glance_brief v0.3.0 Output Contracts

输出格式是公开接口。模型只返回语义 JSON；下列 Markdown 由程序确定性生成。

## agents-report

```markdown
📡 **agents-radar 生态报告 | YYYY-MM-DD**

**🤖 AI 生态动态**
- ① **短导语**：代表一个生态变化簇；可用分号并列同簇中的互补事实，保留主体、动作、结果和关键限定。（来源：[原文](精确 URL)•[独立分析](精确 URL，可选)）

[逐字插入 producer-owned `codexradar.markdown`；该 block 自带标题]

**🔥 开源热点趋势**
- ① 不含具体项目、模型或指标的总体趋势
- ② 不含具体项目、模型或指标的总体趋势

**✨新热门开源**
- [owner/repo](精确 GitHub URL)「模型根据 producer description 翻译的中文简介」(+X★/日)

① producer 分类标题
- 热门项目：✨ [owner/repo](精确 GitHub URL)「模型根据 producer description 翻译的中文简介」(+X★/日)
```

约束：

- AI 动态不是单篇新闻排行榜，而是对当天生态变化的最多三条编辑切片；先按事件、进展或明确互补主题聚类，再选择摘要。候选池达到 5 条时，默认目标是覆盖至少 5 个候选 ID；仅在候选确实无关、重复或证据不足时少选，不得为了三条上限直接输出三条单候选动态。每条使用 1–3 个 `candidate_ids`，候选 ID 在全文不得复用；来源从所有绑定候选的 provenance 合并回填。
- AI 动态每条都有 `topic` 短导语，renderer 以 `**topic**：summary` 输出；摘要目标 80–120 字、硬上限 140 字，并不得出现 RSS、feed、网页采集或抓取等来源管线细节。
- AI 动态的 AIHOT 条目页只作为内部 provenance，不在可见来源行展示；可见来源只取原文或直接来源。同一发布方去重，社交平台短帖在有完整原文时降级；每条最多展示两个来源，使用 `•` 连接，不追加 `+N`。若没有可见原文，明确显示“暂无可见原文”，不得回退展示 AIHOT 条目页。
- CodexRadar Markdown 只验证后原样插入，不解析、不重排、不重算。
- 开源总体趋势必须恰好两条，不得出现项目名、组织名、模型名、URL、Star 或其他数值。
- `fresh_hot` 必须是 `hot_today` 的唯一子集；非空时只生成一次 `**✨新热门开源**`。
- `local_report_categories` 必须唯一、完整覆盖 `hot_today`；分类标题逐字保留、顺序不变，每类只展示映射的第一项。
- 项目名、URL、`stars_today`、`is_fresh_hot` 和分类全部来自 producer，不猜测或拼接；简介由模型只根据 producer description 翻译，resolver 要求每个实际展示项目恰好有一条中文简介。
- `new_projects` 属于独立雷达，本报告不展示。
- 不生成 `其他项目`，不使用 Markdown 分隔线。

## noon-news

```markdown
📰 今日热点简报

### 今日要点
1. 主题词：一句候选支持的事实

### 分类详情

**① 国际要闻**
- **English original headline**（约 12–28 字中文对照）
  一句候选支持的事实。
  > 来源：[NS•Publisher](精确原文 URL)

**② 宏观与商业**
...

**③ AI 主线**
- **原始非英文标题**
  一句候选支持的事实。
  > 来源：[AIHOT](精确条目 URL)•[Publisher](精确原文 URL)
```

约束：

- 详情固定三段：`international`、`macro_business`、`ai`；每条详情固定三行。
- 每条详情只绑定一个候选；模型不得跨事件或跨候选合并。
- 原题由程序逐字回填。只有英文原题可附约 12–28 字中文对照；中文、日文等非英文标题不翻译。
- `top_points` 只引用已选详情，最多五条；重复或未绑定项属于 hard failure，不生成报告。
- AIHOT 条目页 URL 与原文 URL 是两个 provenance link，分别保留；renderer 使用 producer 提供的精确 URL。
- 来源标签中的层级冒号规范为空格；同渠道 URL 去重，渠道内及渠道间统一用 `•` 连接，每条最多两个渠道，更多显示 `+N`。
- 模型 payload 不含 URL、来源 metadata、日期、项目指标或 Markdown。
- 候选 title/text 含 URL 或 unsafe Markdown 时在 adapter 边界拒绝并记录 `candidate_rejections`；剩余候选仍须满足 `minimum_candidates`。
- 不使用 Markdown 分隔线。

## v0.3.0 运行策略

- 来源级 `required`：必选 producer 失败时在模型调用前终止，绝不生成部分报告。
- 报告级 `minimum_candidates`：固定板块候选低于下限时在模型调用前终止。
- Noon `selection_limits`：每个板块最终选择条数必须落在配置的 `min`/`max` 范围内；limits 会进入 lean payload，但由 resolver 最终 hard gate。
- `command_json` 默认不继承全部环境变量，只能获得基础变量与显式 `env_allowlist`。
- 每次运行写入 `manifest.json`：报告、状态、生成时间、全部输入/输出 artifact 与 config 的 SHA-256、模型参数。
- Agent-mode handoff 使用 `prepare` 固化 registry/payload/prompt 哈希，再由 `render-prepared` 从 run-scoped semantic JSON 渲染；render 不重新读取来源，任何 config/artifact 篡改都 hard fail。
- `replay` 只接受成功且输入哈希一致的快照，在不读取来源、不调用模型的情况下重新 resolve/render；输入输出目录必须不同。
- Agents 模型 `summary` 超过 140 字符属于 hard failure；Noon 模型 `summary` 仍使用 300 字符上限。

## Resolved schema 所有权

两个 resolved 对象均固定 `schema_version: 2`。Noon 使用受信任的 `report_date` 与 `generated_at`，Agents 使用受信任的 `date`；两者都包含固定 sections。模型字段只能进入摘要、项目简介翻译、主题和趋势位置；候选 ID 解析后，所有身份、链接、指标、fresh 和分类等不可变事实从 candidate registry / producer metadata 回填。

## 变更规则

任何可见格式变更都必须同时：

1. 更新 Prompt 所有权边界；
2. 更新本文档；
3. 更新 fixture/contract tests；
4. 生成本地 preview；
5. 获得明确授权后才同步 runtime 或 Cron。
