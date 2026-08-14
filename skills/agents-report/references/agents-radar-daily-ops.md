# agents-radar operation guide

## Purpose

This guide describes the current content-marker based agents-radar pipeline. It intentionally does not contain a live Cron ID, chat ID, model, credential, or absolute runtime path.

## Pipeline

```text
agents_radar_prefetch.py
  ├── agents-radar-daily.py --source ai-trending
  ├── AI HOT v1: selected global pool, window=24h, by=timeline
  └── codexradar_efficiency.py
```

The collector output is selected by content markers such as `今日速览`, `各维度热门项目`, `趋势信号分析`, and `社区关注热点`. Do not restore fixed BLOCK numbers as the primary selector.

## Manual checks

```bash
python3 skills/agents-report/scripts/agents_radar_prefetch.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Failure handling

- HTTP / RSS failure is retained in the JSON payload.
- A failed AI HOT category does not get filled from another source.
- CodexRadar snapshot failure falls back to its raw table; if both fail, only that block reports limited information.
- Do not send a report based on a failed or empty source by guessing.

## Source rules

- AI HOT links use `items[*].links.aihot`.
- AI HOT source labels use `items[*].source.name`.
- The agents-radar collector preserves the original feed link and block text.
- CodexRadar uses the public snapshot first and raw table as fallback.
