# openclaw-news-skills

OpenClaw News 相关 Skills 集合。

## Skills

### agents-report

每日 OpenClaw 生态报告（agents-radar 生态日报）。

- **定时：** 每日 10:00 Asia/Shanghai
- **数据：** agents-radar RSS（OpenClaw 生态 + GitHub Trending）
- **安装：** 见 `skills/agents-report/SKILL.md`

### noon-news

每日午间热点简报。

- **定时：** 每日 12:30 Asia/Shanghai
- **数据：** news-aggregator + news-summary RSS + daily-ai-news
- **安装：** 见 `skills/noon-news/SKILL.md`

## 安装方式

### 方式一：Git Sparse Checkout（推荐，只装一个）

```bash
# 只装 agents-report
git clone --filter=blob:none --sparse https://github.com/<you>/openclaw-news-skills.git
cd openclaw-news-skills
git sparse-checkout set skills/agents-report

# 或只装 noon-news
git sparse-checkout set skills/noon-news
```

### 方式二：全量克隆

```bash
git clone https://github.com/<you>/openclaw-news-skills.git
# 所有 skills 都在 skills/ 目录下
```

## 依赖

- `news-aggregator-skill`（noon-news 需要）
- `news-summary`（noon-news 需要）
- `daily-ai-news-skill`（noon-news 需要）
- `agent-reach`（搜索补齐用）

以上均通过 clawhub 安装或参考对应 SKILL.md。
