# glance_brief v0.3.0

`glance_brief` 把值得看的 AI 动态和新闻整理成两份可追溯日报：模型负责筛选、压缩和翻译，程序负责事实、来源、链接、日期、指标与 Markdown。

## 两份日报

### `agents-report`：AI / Agents 生态日报

聚合 AI 生态动态、CodexRadar 效率快照和开源热点，按固定结构呈现趋势、新热门项目与分类项目。项目身份、GitHub URL、描述、指标、分类和 fresh 状态均由 producer 提供，模型不能生成或修改。

![agents-report 排版示例](docs/images/report-style-1.png)

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

详见：

- [架构](docs/architecture.md)
- [数据契约](docs/data-contracts.md)
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

`install/install.py` 安装两份报告的 producer、共享 `glance_brief` core、统一 CLI 与脱敏配置示例。当前已验证的调度适配器是 Hermes：报告 Job 使用 `no_agent: true` 关闭外层 Agent，安装入口内部完成一次模型调用，再由 core 校验和渲染；这不代表无模型调用或零 token。OpenClaw 在 v0.3.0 仅提供 adapter contract，不发布未验证的可运行 Job 模板。定时任务和投递目标仍须在用户确认后由 runtime 原生接口创建或更新。

### 本地验证

```bash
python3 -m glance_brief check --config config/brief.example.json
python3 -B -m unittest tests.test_contracts tests.test_pipeline -v
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

正式业务包位于 `glance_brief/`；两份报告共享同一套 adapters、contracts、resolver、renderer、Prompt 加载和 artifact/replay 边界。

## 后续工作

- [ ] 在 production rollout 前单独演练 Cron 切换与回滚
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
