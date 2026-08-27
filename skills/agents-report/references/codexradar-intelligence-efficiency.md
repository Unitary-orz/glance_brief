# CodexRadar 智力效率读取参考

## 用途

为 agents-radar 增加可选的“智力效率”板块时，读取 CodexRadar 的公开 JSON，不抓 HTML、不依赖浏览器登录。

页面来源：<https://codexradar.com/>

## 推荐读取路径

页面实际使用以下同域接口：

- 当前原始评测表：`GET https://codexradar.com/api/intelligence-efficiency`
- 当前 24 小时运行指标：`GET https://codexradar.com/api/intelligence-efficiency-metrics`
- 已聚合的发布快照/兜底：`GET https://codexradar.com/data/intelligence-efficiency.json`

页面还在快照的 `source` / `metrics_source` 中暴露了对应的 API origin：

- `https://api.codexradar.com/api/v1/table`
- `https://api.codexradar.com/api/v1/model-metrics`

实现时优先使用 codexradar.com 的同域路径，因为这是页面自身的读取方式；服务器端任务不需要 CORS 或登录。

## 三种数据形态

### 1. 原始表 `api/intelligence-efficiency`

当前 schema 为 1，包含：

- `combos`：`model + effort` 配置列表
- `tasks`：评测任务列表
- `cells`：键为 `<task_id>|<model>|<effort>` 的结果单元
- `cells[key].ran_by[]`：按时间保存的实际运行记录

页面当前每次聚合约 112 个任务、21 个配置。这个接口体积较大，适合需要复现页面计算时使用。

### 2. 运行指标 `api/intelligence-efficiency-metrics`

当前 schema 为 1，`mode` 通常是 `latest_valid_per_task`。按 `model + effort` 返回：

- `average_agent_steps`
- `average_total_tokens`
- `cache_hit_rate`
- `runs_24h`
- `runs_48h`
- `runs_total`

把它和其他结果按 `(model, effort)` 合并，不要按数组位置合并。

### 3. 聚合快照 `data/intelligence-efficiency.json`

当前 schema 为 2，`points[]` 已经包含：

- `iq`
- `passed`
- `valid_tasks`
- `average_price_usd`
- `average_minutes`
- `combined_cost_index`
- 以及运行次数、Agent steps、tokens、cache 命中率等字段

日报优先使用这个快照可以减少计算和网络负担；读取 `source_updated_at`，如实标注数据更新时间。live 接口失败时可以把它作为兜底。

## 页面计算契约

页面源码的 IQ 计算为：

```text
IQ = passed / valid_tasks × 150
```

这不是通用智力或标准 benchmark 分数，只是 CodexRadar 任务集上的通过率缩放值。`valid_tasks` 是有有效判定结果的任务数。

对于每个 `model + effort`：

1. 遍历每个任务的 `cells[task|model|effort].ran_by`。
2. 取页面使用的最新有效结果（当前 live table 中页面取 `ran_by[0]`；若自行实现，先确认源端数组顺序，不要凭猜测）。
3. 统计 `passed`、`valid_tasks`、平均耗时和平均费用。
4. `average_minutes = duration_sec` 的有效样本平均值除以 60。
5. `average_price_usd` 使用 `actual_cost_usd`；`ultra` 档仅纳入 `cost_complete=true` 的费用样本。

综合成本权重与公式：

```text
weight = log(2.5) / log(1.35)
raw_combined_cost = average_price_usd × (average_minutes / 10)^weight × 100
combined_cost_index = raw_combined_cost / 当前图表最高 raw_combined_cost × 100
```

页面解释为“2.5 倍价格可换 1.35 倍速度”，因此综合成本指数越低越好，IQ 越高越好；“越靠左上越高效”。归一化最高值为 100，不能把它当作跨日期的绝对成本。

## 关注配置

外置关注配置的项目模板位于：`skills/agents-report/config/codexradar_watch.example.json`；运行时应复制为私有配置并通过 `CODEXRADAR_CONFIG` 指定。

当前默认读取指标为：`iq`、`average_minutes`、`average_price_usd`。

当前显式关注规则为：

- `gpt-5.6-luna`：`xhigh`、`max`
- `gpt-5.6-sol`：`medium` 及以上
- `deepseek-v4-flash`：全部可用 effort
- `gpt-5.5`：全部可用 effort

配置中保留 `selection.iq_filter.include_iq_at_least: 90` 作为未来筛选阈值，但 `selection.iq_filter.enabled` 当前为 `false`，因此暂时不会因为 IQ 达标而额外纳入模型。显式规则匹配后按 `(model, effort)` 去重。

配置还保留 `ranking`：智力排行取 Top 2；均衡排行取 Top 2，计算范围为全部显式关注配置，不先排除已进入其他榜单的配置，使用 IQ、平均耗时、平均价格的百分位分数几何平均，平分时优先综合成本更低者；性价比 Top 3 只在非 Sol 显式关注配置中计算，先应用独立的 `IQ ≥ 70` 质量门槛，再按 `IQ × price_factor` 降序；`price_factor` 由 `ranking.value_price_bands` 提供，当前为 `≤$0.30 → 1.00`、`>$0.30–$0.50 → 0.98`、`>$0.50–$1 → 0.95`、`>$1–$3 → 0.85`、`>$3–$5 → 0.75`、`>$5 → 0.65`；时间和综合成本只作次级平分判断。非 Sol 候选为空时直接输出空榜，不回退引入 Sol；价格为 0 的配置作为免费项优先排序，并用 `value_is_free: true` 与 `value_score: null` 保持标准 JSON。这个门槛属于性价比排序，不等同于全局 IQ 筛选开关。榜单计算不互相排除；展示排版时，未进入任一 Top 榜的关注配置归入“其他”。综合成本沿用 CodexRadar 的价格/耗时权重；IQ 筛选阈值与这些排序分开，当前仍未启用。

“其他”不做 IQ 或性价比排名，按模型顺序 `Sol → Luna → gpt-5.5 → DeepSeek V4`，同一模型内按 effort 顺序排列，只用分号分隔。

## 稳定性与降级

- live 接口观察到 `cache-control: max-age=30, stale-while-revalidate=60`。
- 发布快照观察到 `max-age=600, stale-while-revalidate=60`。
- 每日任务不要高频轮询；一次抓取即可。
- 推荐顺序：快照作为轻量主路径或兜底；需要页面级实时值时再读原始表和 metrics。
- 校验 HTTP 状态、JSON schema、`points` 非空、`source_updated_at` 存在。
- CodexRadar 板块失败只影响该板块，不得用其他来源或常识补写。
- 不要把 IQ 概括成“模型智商”；输出时说明它是 CodexRadar 评测任务通过率缩放指标。
