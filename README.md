# glance_brief v0.3.0

`glance_brief` 把值得看的 AI 动态和新闻整理成两份日报：先筛选和压缩信息，再按固定结构呈现。内容覆盖 Agents 生态、开源项目、国际新闻和商业动态，方便每天快速了解重点。

## 两份日报

### `agents-report`：AI / Agents 生态日报

聚合 AI 生态变化、CodexRadar 效率快照和开源项目热点，按固定结构呈现趋势、新热门项目与分类项目。

![agents-report 排版示例](docs/images/report-style-1.png)

### `noon-news`：午间热点简报

先看今日要点，再按三个固定板块展开：

1. 国际要闻
2. 宏观与商业
3. AI 主线

每条新闻保留原题、简短事实和来源。英文标题可以附简洁中文对照。

![noon-news 排版示例](docs/images/report-style-2.png)

## 内容来源

| 信息源 | 覆盖内容 |
|---|---|
| AI HOT | AI 动态与午间 AI 主线 |
| CodexRadar | 模型效率快照 |
| agents-radar / 本地开源雷达 | AI 生态与开源热点 |
| news-aggregator-skill | 宏观、商业与综合新闻 |
| news-summary | 国际新闻 RSS |

报告保留原始来源链接，方便需要时打开原文。

## 一个独立的开源雷达

`local-open-source-radar` 是独立的开源项目采集器，不是第三份日报。它为 `agents-report` 提供项目热点，也可以单独生成项目快照。

源码和使用契约见 [`producers/local-open-source-radar/`](producers/local-open-source-radar/)。

## 开始使用

推荐让具有终端和任务调度能力的 Agent 执行根目录的 [`INSTALL.md`](INSTALL.md)：

```text
请安装 glance_brief：
https://github.com/Unitary-orz/glance_brief

克隆后读取根目录 INSTALL.md；创建定时任务或设置投递目标前先展示预览并确认。
```

安装流程会先说明要安装的报告、运行位置和待确认的投递设置；仓库里的示例数据用于离线验证，正式运行时换成实际来源即可。

## v0.3.0

- 两份日报继续按固定结构提供 AI 生态和午间新闻内容。
- 独立开源雷达为 Agents 日报补充项目热点，也支持单独使用。
- 安装、更新和卸载会保留用户配置与历史产物。

更具体的说明：

- [安装说明](INSTALL.md)
- [架构](docs/architecture.md)
- [数据契约](docs/data-contracts.md)
- [新增来源指南](docs/adding-sources.md)
- [Producer contract](docs/producer-contract.md)
- [输出契约](docs/output-contracts.md)

## 本地验证

开发或修改后，可以运行完整的三套测试：

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B -m unittest discover -s producers/local-open-source-radar/tests -p 'test_*.py'
python3 -B -m unittest discover -s runtime/reports/tests -p 'test_*.py'
```

贡献代码前请先阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 下一步计划

- [x] 可插拔来源适配器：将现有来源接入统一的「来源 → 标准化数据 → 板块编排 → 输出契约」接口，新增来源不改报告逻辑
- [x] 板块映射配置化：通过配置文件声明「来源 → 板块」的对应关系，无需改代码即可接入新来源
- [ ] 扩大优质来源：优先补充 arXiv 论文、X / 微博话题、YouTube 摘要等高质量内容源
- [ ] 补充其他 runtime 适配：复用同一安装契约，支持 OpenClaw 等运行时

## 致谢

信息源相关开源项目：

- [news-aggregator-skill](https://github.com/cclank/news-aggregator-skill)
- [AI HOT / khazix-skills](https://github.com/KKKKhazix/khazix-skills)
- [agents-radar](https://github.com/duanyytop/agents-radar)
- [CodexRadar](https://codexradar.com/)

## 许可证

MIT License
