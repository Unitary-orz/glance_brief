# OpenClaw adapter

This directory describes the runtime boundary for OpenClaw. The business scripts do not contain OpenClaw absolute paths.

## Required environment

```bash
export CODEXRADAR_CONFIG="$OPENCLAW_WORKSPACE/data/brief/config/codexradar_watch.json"
export AGENTS_RADAR_OUTPUT_DIR="$OPENCLAW_WORKSPACE/data/brief/output/agents-radar"
export AGENTS_RADAR_COLLECTOR="$OPENCLAW_WORKSPACE/skills/agents-report/scripts/agents-radar-daily.py"
export NEWS_AGGREGATOR_SCRIPT="$OPENCLAW_WORKSPACE/skills/news-aggregator-skill/scripts/fetch_news.py"
export NEWS_SUMMARY_SCRIPT="$OPENCLAW_WORKSPACE/skills/news-summary/scripts/fetch_rss.py"
```

Install the required external news skills separately. The project does not vendor them.

Use the prompt files in:

```text
skills/agents-report/prompts/agents-report-v2.md
skills/noon-news/prompts/news-brief-v2.md
```

Set schedule, model, and delivery target in the OpenClaw task configuration, not in the reusable Skill.
