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

`agents_radar_prefetch.py`、`agents-radar-daily.py`、`codexradar_efficiency.py` 等是 producer/utility，不是最终报告入口，也不发送报告。

## 数据来源

- AI HOT：AI 生态动态；
- CodexRadar：producer-owned 模型效率 Markdown；
- agents-radar / 本地开源雷达：hot、fresh、分类与项目事实。

真实路径与用户配置由 runtime adapter 提供，不写入 Skill。

## 所有权边界

模型只选择 AI 动态候选、写单候选摘要和恰好两条总体趋势。模型不得返回 URL、来源、日期、项目名、模型名、指标、fresh、分类、Codex 内容或 Markdown。

程序负责：

- 从 candidate registry 回填 AI 动态来源；
- 验证并逐字插入 `codexradar.markdown`；
- 从 `hot_today`、`fresh_hot`、`local_report_categories` 恢复项目事实；
- 验证 GitHub URL、quality、fresh 子集和分类唯一完整覆盖；
- deterministic render、manifest 和 replay。

完整语义契约见 `glance_brief/prompts/agents-report.md`，可见格式见 `docs/output-contracts.md`。

## 固定结构

1. `🤖 AI 生态动态`；
2. producer-owned CodexRadar block；
3. `🔥 开源热点趋势`；
4. 非空时唯一的 `✨新热门开源`；
5. producer 分类板块。

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
