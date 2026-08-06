# Hermes adapter

This directory describes how to connect the project to Hermes Cron. The example is a template, not a direct import file.

## Required environment

```bash
export CODEXRADAR_CONFIG="$HOME/.hermes/data/brief/config/codexradar_watch.json"
export AGENTS_RADAR_OUTPUT_DIR="$HOME/.hermes/data/brief/output/agents-radar"
export AGENTS_RADAR_COLLECTOR="$HOME/.hermes/skills/agents-radar/scripts/agents-radar-daily.py"
export NEWS_AGGREGATOR_SCRIPT="$HOME/.hermes/skills/news-aggregator-skill/scripts/fetch_news.py"
export NEWS_SUMMARY_SCRIPT="$HOME/.hermes/skills/news-summary/scripts/fetch_rss.py"
```

## Script paths

From a full checkout, use:

```text
skills/agents-report/scripts/agents_radar_prefetch.py
skills/noon-news/scripts/noon_news_prefetch.py
```

If a runtime installs the Skills into its own directory, set the job's script path to that installed copy instead of assuming a `brief/` compatibility directory.

## Schedule

The reference local tasks are:

- agents-report: `0 2 * * *` UTC, equivalent to 10:00 Asia/Shanghai
- noon-news: `30 4 * * *` UTC, equivalent to 12:30 Asia/Shanghai

Set the actual model and delivery target in the local Hermes job configuration. Do not commit them here.
