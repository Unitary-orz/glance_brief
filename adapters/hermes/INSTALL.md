# Hermes adapter

This directory describes how `glance_brief` connects to Hermes Cron. The
example is a template, not a direct import file. The supported installation
path is the agent contract in the repository root `INSTALL.md`, which runs
`install/install.py` and creates the jobs with Hermes' job interface.

## Runtime layout after install

```text
$HERMES_HOME/scripts/glance-brief/
├── agents-report.py           # entry point for the agents-report job
├── noon-news.py               # entry point for the noon-news job
├── agents-quality-check.py    # quality check utility
├── codexradar.py              # CodexRadar standalone renderer
└── lib/
    ├── agents-report/         # business modules (copied verbatim from repo)
    └── noon-news/

$HERMES_HOME/data/glance-brief/
├── config/                    # user config (codexradar_watch.json, agents_radar_quality.json)
├── state/ cache/ output/      # runtime data
└── install-manifest.json      # installed file hashes + job mapping
```

Entry points are thin adapters: they resolve `$HERMES_HOME` (default
`~/.hermes`), set the config/output environment variables, and execute the
matching module under `lib/` with `runpy`. Business modules are never edited
in place; a sync replaces them from the repository and verifies hashes.

## Environment

The entry points set these variables with `os.environ.setdefault` when
running; a user or scheduler may override them:

```text
AGENTS_RADAR_COLLECTOR            -> lib/agents-report/agents-radar-daily.py
AGENTS_RADAR_OUTPUT_DIR           -> $HERMES_HOME/data/glance-brief/output/agents-radar
AGENTS_RADAR_QUALITY_CONFIG       -> $HERMES_HOME/data/glance-brief/config/agents_radar_quality.json
AGENTS_RADAR_QUALITY_MODULE_DIR   -> lib/agents-report
CODEXRADAR_CONFIG                 -> $HERMES_HOME/data/glance-brief/config/codexradar_watch.json
NEWS_AGGREGATOR_SCRIPT            -> $HERMES_HOME/skills/news-aggregator-skill/scripts/fetch_news.py
NEWS_SUMMARY_SCRIPT               -> $HERMES_HOME/skills/news-summary/scripts/fetch_rss.py
```

External news skills must be installed separately; `install.py` reports them
as `missing_external_skills` if absent.

## Job script paths

Hermes job `script` is relative to `$HERMES_HOME/scripts/`. After install use:

```text
glance-brief/agents-report.py
glance-brief/noon-news.py
```

Do not point jobs at repository paths (`skills/...`) — the scheduler resolves
scripts under `$HERMES_HOME/scripts/`.

## Schedule

The reference schedules are:

- agents-report: `0 2 * * *` UTC, equivalent to 10:00 Asia/Shanghai
- noon-news: `30 4 * * *` UTC, equivalent to 12:30 Asia/Shanghai

Set the actual model and delivery target in the local Hermes job
configuration. Do not commit them here. Hermes schedules are interpreted using
the scheduler's configured/default timezone; the examples are deliberately
expressed in UTC. If you use local-time cron expressions, set the scheduler
timezone explicitly instead of relying on the host timezone.

## Verification

```bash
python3 install/install.py verify --runtime hermes
```

All checks must pass (exit 0) after install and after every sync.
