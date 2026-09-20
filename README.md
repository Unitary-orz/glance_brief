# AI Briefs, at a glance

### 一眼看懂今天值得关注的变化

把 AI 生态、Agents 动态、开源项目和世界新闻，整理成两份**短、准、可追溯**的结构化日报。

<div align="center">

`glance_brief` · `v0.3.0`

[![Release](https://img.shields.io/badge/release-v0.3.0-6d5dfc?style=flat-square)](https://github.com/Unitary-orz/glance_brief/releases/tag/v0.3.0)
[![License](https://img.shields.io/badge/license-MIT-2ea44f?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/badge/CI-Python%203.10%E2%80%933.12-3776ab?style=flat-square)](.github/workflows/test.yml)

</div>

> **先看结论，再看细节，最后回到原文。**
>
> 每份日报都有固定结构、明确来源和稳定版式；它们不是信息堆积，而是每天可以快速读完的阅读入口。

## 你会收到什么

| 报告 | 适合什么时候看 | 主要内容 |
|---|---|---|
| **Agents Report** | 关注 AI 行业、模型和开源生态时 | AI / Agents 动态、模型效率快照、开源项目热点与趋势 |
| **Noon News** | 午间快速了解外部世界时 | 国际要闻、宏观与商业、AI 主线，以及每条新闻的原始来源 |

两份报告共享同一套“采集 → 筛选 → 结构化 → 渲染”方法，但各自保持独立的阅读节奏和版式。

## 两份日报

### 01 · Agents Report

面向 AI 生态和 Agents 领域的结构化日报：先给当天值得注意的变化，再展开模型效率、开源项目和趋势信号。

- **AI 生态**：模型、产品、Agent 工具和行业动态
- **效率快照**：CodexRadar 等效率信号
- **开源热点**：新项目、热门项目和分类后的趋势观察
- **可追溯**：保留来源链接，方便继续深挖

<p align="center">
  <img src="docs/images/report-style-1.png" alt="Agents Report 排版示例" width="760">
</p>

### 02 · Noon News

午间新闻简报，按固定三段组织信息，减少从几十条新闻里重新筛选的成本：

1. **国际要闻**
2. **宏观与商业**
3. **AI 主线**

每条新闻保留原题、短事实和来源。英文标题可附简洁中文对照，但不牺牲主体、动作、结果和关键限定条件。

<p align="center">
  <img src="docs/images/report-style-2.png" alt="Noon News 排版示例" width="760">
</p>

## 阅读方式

日报的阅读路径很简单：先看结论，再按主题展开；需要细节时，直接打开原始来源。Agents Report 和 Noon News 共享可追溯的来源体系，但分别服务不同的阅读场景。

## 数据来源 / 模块

| 数据来源 | 服务模块 | 覆盖内容 |
|---|---|---|
| AI HOT | `noon-news` | AI 动态与午间 AI 主线 |
| CodexRadar | `agents-report` | 模型效率快照 |
| agents-radar / 本地开源雷达 | `agents-report` | AI 生态与开源项目热点 |
| news-aggregator-skill | `noon-news` | 宏观、商业与综合新闻 |
| news-summary | `noon-news` | 国际新闻 RSS |

报告保留原始来源链接。需要细节时，直接打开来源，而不是把日报当成唯一事实来源。

## 一个独立的开源雷达

`local-open-source-radar` 是独立的项目采集器，**不是第三份日报**。它为 `agents-report` 提供结构化项目热点，也可以单独生成项目快照。

源码和使用契约见 [`producers/local-open-source-radar/`](producers/local-open-source-radar/)。

## 开始使用

这是一个面向 Agent 的可安装项目。推荐让具备终端、文件和任务调度能力的 Agent 执行根目录的 [`INSTALL.md`](INSTALL.md)：

```text
请安装 AI Briefs：
https://github.com/Unitary-orz/glance_brief

克隆后读取根目录 INSTALL.md；创建定时任务或设置投递目标前先展示预览并确认。
```

安装流程会先说明：

- 要安装哪些报告；
- 运行文件和数据放在哪里；
- 哪些配置需要用户确认；
- 如何用离线样例完成验证。

安装器会保留用户配置、状态和历史产物；创建定时任务和设置投递目标仍需单独确认。

## 当前版本 · v0.3.0

这一版的重点是把日报从“脚本集合”收口为可安装、可验证的报告工具集：

- 两份日报继续按固定结构提供 AI 生态和午间新闻内容；
- 独立开源雷达为 Agents 日报补充项目热点，也支持单独使用；
- 来源适配器和板块映射可以通过配置扩展，不必改报告核心；
- 安装、更新和卸载会保留用户配置与历史产物；
- 仓库提供离线 fixture、完整测试和安装器 dry-run 验证。

更具体的说明：

- [安装说明](INSTALL.md)
- [架构](docs/architecture.md)
- [数据契约](docs/data-contracts.md)
- [新增来源指南](docs/adding-sources.md)
- [Producer contract](docs/producer-contract.md)
- [输出契约](docs/output-contracts.md)

## 本地验证

项目支持 Python 3.10–3.12。修改后可以运行完整的离线测试套件：

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B -m unittest discover -s producers/local-open-source-radar/tests -p 'test_*.py'
python3 -B -m unittest discover -s runtime/reports/tests -p 'test_*.py'
```

CI 还会执行 release gate、正式示例配置校验、两条 runtime 的安装器 dry-run、wheel 安装 smoke test 和空白检查。

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
