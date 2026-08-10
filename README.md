# glance_brief

`glance_brief` 是一套可自行部署的 AI 日报工具。它的总体设计思路很简单：让信息有来源、内容有重点、版式有秩序，并且每天稳定呈现。

每天打开日报，你可以先快速掌握重点，再按主题查看详情；想继续了解时，直接回到原文核对。信息不足时会明确说明，不用看似完整的文字掩盖缺失内容。

## 两份日报

### `agents-report`：AI / Agents 生态日报

面向想持续关注 AI 行业的人，聚合 AI 与 Agents 生态动态、论文、开源热点和模型效率信息，按「AI 生态动态 → 模型效率 → 开源热点趋势」的顺序呈现，适合快速了解行业变化和值得继续追踪的方向。

[查看 agents-report 安装说明](skills/agents-report/INSTALL.md)

### `noon-news`：午间热点简报

面向想快速了解当天新闻的人，先给出 4–5 条今日要点，再按国际、商业、AI 等主题展开分类详情。每条新闻保留原始来源，方便直接点开继续阅读。

[查看 noon-news 安装说明](skills/noon-news/INSTALL.md)

## 最终样式

两份日报采用同一种阅读节奏：**先看结论，再按主题展开，最后核对来源。**

午间热点简报：

```text
📰 今日热点简报

### 今日要点
1. 主题词：一句话事实。
2. 主题词：一句话事实。

### 分类详情
**① 国际要闻**
- English Title
  （中文短题）
  一句话事实描述。
  来源：[NS](原文链接) · [BBC](原文链接)
```

AI / Agents 生态日报：

```text
📡 agents-radar 生态报告 | 日期

**🤖 AI 生态动态**
- ① 一句话动态（来源：[短标签](原文链接)）

---

**🧠 CodexRadar 智力效率**
- ① 智力Top2：模型与指标
- ② 均衡Top2：模型与指标
- ③ 性价比Top3：模型与指标

---

**🔥 开源热点趋势**
- ① 总体趋势
- ② 总体趋势

项目分类
- 热门项目：...
- 其他项目：...
```

示例中的文字和链接仅用于说明版式；实际日报使用当天内容和真实来源。

## 开始使用

`glance_brief` 是需要安装的工具集，不是在线新闻网站，也不是已经托管好的订阅服务。安装后选择需要的日报，按对应说明配置即可。

### 使用 Agent 安装（推荐）

把本仓库交给有终端与任务调度能力的 Agent，并让它执行根目录 [INSTALL.md](INSTALL.md) 的安装契约：

```text
请安装 glance_brief：
https://github.com/Unitary-orz/glance_brief

克隆仓库后读取根目录 INSTALL.md，按其中的 Agent Installation Contract 执行；
创建定时任务或设置投递目标前先向我展示预览并确认。
```

安装器会复制运行文件、生成默认配置、检查依赖，并输出待创建的定时任务建议；任务创建、投递目标由 Agent 在您确认后完成。

### 手工安装（备选）

```bash
git clone https://github.com/Unitary-orz/glance_brief.git
cd glance_brief
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

然后选择需要的日报，按对应说明配置：

- [agents-report 安装说明](skills/agents-report/INSTALL.md)
- [noon-news 安装说明](skills/noon-news/INSTALL.md)

如果只想在本地检查数据，也可以直接运行对应入口；它会输出结构化结果，不会自行发送消息。

## 给维护者和开发者

- [架构说明](docs/architecture.md)：项目如何组织和运行；
- [数据契约](docs/data-contracts.md)：数据字段和失败规则；
- [输出契约](docs/output-contracts.md)：日报版式和来源要求。

本地检查：

```bash
python3 -m py_compile \
  skills/agents-report/scripts/*.py \
  skills/noon-news/scripts/*.py

python3 -m unittest discover -s tests -p 'test_*.py'
```

当前项目版本是 **0.1.0**；Prompt 版本为 `agents-report-v2` 和 `news-brief-v2`；预取数据协议为 `schema_version: 1`。

## 许可证

MIT License
