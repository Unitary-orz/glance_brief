# Noon news task guide

## Purpose

The noon-news task prefetches source data and leaves formatting to the runtime Prompt. It does not send messages itself.

## Pipeline

```text
noon_news_prefetch.py
  ├── news-aggregator
  ├── news-summary RSS
  └── AI HOT v1 全局精选（`/api/v1/items`，`mode=selected&window=24h&by=timeline`）
```

All child script paths are supplied by environment variables. The project does not assume an OpenClaw or Hermes directory.

## Manual checks

```bash
NEWS_AGGREGATOR_SCRIPT=/path/to/fetch_news.py \
NEWS_SUMMARY_SCRIPT=/path/to/fetch_rss.py \
python3 skills/noon-news/scripts/noon_news_prefetch.py
```

## Output rules

- The runtime reads only the emitted JSON.
- Sources are deduplicated by the runtime Prompt.
- The final report keeps the existing `今日要点` and `分类详情` order.
- Each detail's source remains a separate final line.
- Links use the original `link` or `url` field and are never manufactured.

## Failure handling

- Preserve each source's `ok`, `returncode`, `stderr`, and parsed items.
- If one source fails, use the remaining sources according to the Prompt.
- If all sources fail, use the fixed failure message.
