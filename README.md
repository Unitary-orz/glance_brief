# glance_brief v0.3.0

`glance_brief` 把值得看的 AI 动态和新闻整理成两份可追溯日报：模型负责筛选、压缩和翻译，程序负责事实、来源、链接、日期、指标与 Markdown。

## 两份日报

### `agents-report`：AI / Agents 生态日报

聚合 AI 生态动态、CodexRadar 效率快照和开源热点，按固定结构呈现趋势、新热门项目与分类项目。项目身份、GitHub URL、描述、指标、分类和 fresh 状态均由 producer 提供，模型不能生成或修改。

![agents-report 排版示例](docs/images/report-style-1.png)

### `local-open-source-radar`：独立开源雷达 producer

独立采集 GitHub AI 开源项目，生成当天的热门项目、趋势和分类快照；source-owned renderer 负责独立 publication 的最终 Markdown，`agents-report` 消费这份经过校验的来源数据，不把 producer 的定时任务或运行状态塞进报告 core。它不属于根安装器默认安装的报告组件，源码和运行契约见 [`producers/local-open-source-radar/`](producers/local-open-source-radar/)。

### `noon-news`：午间热点简报

先列今日要点，再固定展开：

1. 国际要闻；
2. 宏观与商业；
3. AI 主线。

每条详情只绑定一个候选，保留原题、单句事实和精确来源。英文原题可附简短中文对照；数字必须在候选证据中逐字可核验。

![noon-news 排版示例](docs/images/report-style-2.png)

## v0.3.0 架构

```text
producer JSON
→ bounded adapters
→ immutable candidate registry
→ lean semantic model payload
→ model JSON
→ resolver + validator
→ deterministic Markdown renderer
→ report + manifest + replayable artifacts
```

**模型只拥有语义：**候选选择、忠实摘要、英文标题中文对照和总体趋势。

**程序拥有事实与格式：**日期、原题、URL、来源层级、发布时间、项目身份、指标、fresh、分类和 Markdown 骨架。模型 payload 不含 URL，也不能跨候选拼接事实。

配置只允许受控 `json_file` 和 argv 形式的 `command_json` 来源；必选来源、板块候选下限、最终选择上下限和数据质量均由程序 hard gate。失败时保留诊断和 manifest，不生成可投递报告。

### 当前 reports 生产 runtime 的源码边界

当前正式生产 writer 使用这份 reports source tree；`runtime/reports/` 是历史兼容目录名，
不表示当前只用于预览。可重建源码统一收在 [`runtime/reports/`](runtime/reports/)，
该目录包含两个入口、reports core、Prompt、schema-v3 配置样例、离线 snapshot
和解耦回归测试。`--runtime hermes` 保留为 schema 2 legacy 批处理 runtime；
当前 reports 的安装映射仍使用历史兼容名 `--runtime hermes-reports`，将源码映射到
`glance-brief-reports`。该模式只安装文件、记录 source revision/owned-file hashes
并输出 Cron 建议，不自动修改 Cron、投递或 live runtime。reports 通过注册式
`snapshot_json` input adapter 让多个来源查看同一份不可变输入。
详见：

- [架构](docs/architecture.md)
- [数据契约](docs/data-contracts.md)
- [新增来源指南](docs/adding-sources.md)
- [Producer contract](docs/producer-contract.md)
- [输出契约](docs/output-contracts.md)
- [`agents-report` Skill](skills/agents-report/SKILL.md)
- [`noon-news` Skill](skills/noon-news/SKILL.md)

## 数据来源

| 信息源 | 覆盖内容 |
|---|---|
| AI HOT | AI 动态与午间 AI 主线 |
| CodexRadar | 模型效率快照 |
| agents-radar / 本地开源雷达 | AI 生态与开源热点 |
| news-aggregator-skill | 宏观、商业与综合新闻 |
| news-summary | 国际新闻 RSS |

所有可见链接都来自 producer provenance；不得猜测、拼接或用搜索结果替换原始 URL。

## 开始使用

### Agent 安装

把仓库交给具有终端和任务调度能力的 Agent，并让它执行根目录 [INSTALL.md](INSTALL.md)：

```text
请安装 glance_brief：
https://github.com/Unitary-orz/glance_brief

克隆后读取根目录 INSTALL.md；创建定时任务或设置投递目标前先展示预览并确认。
```

`install/install.py` 同时提供 schema 2 legacy 批处理映射和当前 reports agent-handoff 映射；两条运行线有意并存，不再声称共用同一套实现。当前生产 writer 使用 `glance-brief-reports` 下的 reports core，`hermes-reports` 只是仓库安装器保留的历史兼容名。Hermes reports Job 使用外层 handoff，由 core 校验和渲染；schema 2 Job 才使用 `no_agent: true` 的批处理入口。OpenClaw 在 v0.3.0 仅提供 adapter contract，不发布未验证的可运行 Job 模板。定时任务和投递目标仍须在用户确认后由 runtime 原生接口创建或更新。

### 本地验证

```bash
python3 -m glance_brief check --config config/brief.example.json
python3 -B -m unittest tests.test_contracts tests.test_pipeline -v
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

reports 的可重建源码位于 `runtime/reports/`，reports 两份报告共享该目录内的 core；顶层 `glance_brief/` 则保留 schema 2 legacy 业务包。两条运行线通过各自的 manifest、配置与 runtime adapter 隔离。

## 后续工作

- [x] 已完成 reports Cron 切换、单 writer 校验和回滚演练；具体运行记录与备份位置属于本地 runtime，不入仓库
- [ ] 增加 artifact 原子发布、分层 deadline 和运行告警
- [ ] 补充 HTTP producer adapter 前先明确安全与缓存边界
- [ ] 支持更多 runtime adapter

## 致谢

信息源相关开源项目：

- [news-aggregator-skill](https://github.com/cclank/news-aggregator-skill)
- [AI HOT / khazix-skills](https://github.com/KKKKhazix/khazix-skills)
- [agents-radar](https://github.com/duanyytop/agents-radar)
- [CodexRadar](https://codexradar.com/)

## 许可证

MIT License
