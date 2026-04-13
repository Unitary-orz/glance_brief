# glance_brief

每日简报工具集，为 OpenClaw agent 提供结构化、可复用的报告生成能力。



## 前提条件

本项目依赖 **OpenClaw** 运行环境。需要先完成 OpenClaw 安装和基础配置。

详细参考：[OpenClaw 官方文档](https://docs.openclaw.ai)

## 简报风格特点

- **事实驱动**：只写已发生的事实，不写推断或趋势判断
- **克制精确**：标题即核心信息，正文不超过两句话
- **来源可查**：每条消息附带来源标签（NS/NA/DA/HN），可追溯
- **结构固定**：国际/宏观/科技，板块清晰，扫描成本低

## Skills

### agents-report

每日 OpenClaw 生态报告。

- **定时：** 每日 10:00 Asia/Shanghai
- **数据：** agents-radar RSS（OpenClaw 生态 + GitHub Trending）
- **安装：** `skills/agents-report/INSTALL.md`

### noon-news

每日午间热点简报。

- **定时：** 每日 12:30 Asia/Shanghai
- **数据：** 多源新闻聚合（news-aggregator + news-summary RSS + daily-ai-news）
- **安装：** `skills/noon-news/INSTALL.md`

## 快速安装

```bash
# 克隆仓库（稀疏克隆，只取目标 skill）
git clone --filter=blob:none --sparse https://github.com/Unitary-orz/glance_brief.git
cd glance_brief

# 单独安装 agents-report
git sparse-checkout set skills/agents-report

# 或单独安装 noon-news
git sparse-checkout set skills/noon-news
```

详细安装说明见各 skill 目录下的 `INSTALL.md`。

## 许可证

MIT License
