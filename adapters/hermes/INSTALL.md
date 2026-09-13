# Hermes runtime adapter

`glance_brief v0.3.0` currently ships one verified scheduler adapter: Hermes.
The repository installer owns files only; an installing Agent creates or updates
Cron jobs separately through Hermes' native job interface after the user approves
schedule and delivery.

## Installed layout

```text
$HERMES_HOME/scripts/glance-brief/
├── glance-brief.py              # shared core CLI
├── agents-report.py             # complete Agents report batch entry point
├── noon-news.py                 # complete Noon report batch entry point
├── agents-quality-check.py      # Agents quality utility
├── codexradar.py                # CodexRadar utility
└── lib/
    ├── glance_brief/            # shared contracts, resolver, renderer, prompts
    ├── agents-report/           # source producer modules
    └── noon-news/               # source producer modules

$HERMES_HOME/data/glance-brief/
├── config/
│   ├── brief.example.json       # installed example; never used as live config
│   ├── brief.json               # user-authored live schema 2 config
│   └── ...                      # component configs
├── state/
├── cache/
├── output/
└── install-manifest.json
```

The installer never creates `brief.json` automatically because the example uses
repository fixtures. The installing Agent must create a runtime-specific config
with real `json_file` or bounded `command_json` sources before creating jobs.

## Execution boundary

Each report entry point is a complete batch application:

1. load and validate `brief.json`;
2. run bounded source adapters and build the immutable candidate registry;
3. construct the lean model prompt without source URLs;
4. invoke one `hermes chat` process through the Hermes adapter;
5. pass raw JSON back to the shared core;
6. resolve facts and provenance, apply hard gates, and render deterministic Markdown;
7. print only the verified `report.md` to stdout.

The shared `glance_brief` package does not import Hermes or select a provider.
Hermes-specific model invocation exists only in the installed runtime entry point.

The current V2 production agent-handoff mode maps the source-owned tree through
`python3 install/install.py install --runtime hermes-preview` to:

```text
$HERMES_HOME/scripts/glance-brief-v2/
├── agents-v2.py                 # flat scheduler wrapper
├── noon-v2.py                   # flat scheduler wrapper
├── entrypoints/                 # source entrypoints retained for auditability
├── lib/glance_brief/            # complete V2 core and Prompt closure
└── cron-prompts/                # sanitized outer-Agent handoff prompts

$HERMES_HOME/data/glance-brief-v2/config/
├── brief.preview.example.json   # installed example; fixture-backed
└── brief-live.json              # user-authored schema 3 config
```

The flat wrappers set `HERMES_HOME` and `GLANCE_BRIEF_PREVIEW_ROOT` from their
installed location, so the mapping is relocatable under a different Hermes
home. The installer records the repository `source_revision`, dirty-state
marker, and hashes for every owned file. It does not create, disable, or update
Cron jobs.

V2 jobs are outer-Agent handoff jobs (`no_agent: false`) and must use the
prompt printed by the installer or `adapters/hermes/jobs.preview.example.json`.
The Agents job must set `GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR` explicitly to the
already-published local-radar directory; the wrapper fails closed when it is
missing instead of silently using a guessed directory. The `hermes-preview` name
is historical; do not enable the V2 writer and the corresponding schema 2 legacy
writer for the same destination together.

## `no_agent` jobs

Use the installed relative script paths:

```text
glance-brief/agents-report.py
glance-brief/noon-news.py
```

Both jobs must set:

```json
{"no_agent": true}
```

Here `no_agent` means **no outer scheduler Agent**. It does not mean no LLM call,
zero tokens, or zero cost: the runtime adapter performs one model call inside the
batch process. Do not add a Cron `prompt`, `prompt_file`, `model`, `provider`, or
`skills` field; those would either be ignored in script-only mode or encourage a
second model layer that bypasses deterministic post-processing.

Reference schedules in `jobs.example.json` are UTC. Delivery identifiers are
placeholders and must never be committed with real values.

## Runtime settings

The entry points use the Hermes runtime default model/provider unless explicitly
overridden in the scheduler process environment:

```text
GLANCE_BRIEF_CONFIG          default: $HERMES_HOME/data/glance-brief/config/brief.json
GLANCE_BRIEF_OUTPUT_DIR      optional explicit artifact directory
GLANCE_BRIEF_HERMES          default: hermes
GLANCE_BRIEF_MODEL           optional model override
GLANCE_BRIEF_PROVIDER        optional provider override
GLANCE_BRIEF_REASONING       optional reasoning override
GLANCE_BRIEF_TIMEOUT         default: 600 seconds
GLANCE_BRIEF_DATE            optional trusted YYYY-MM-DD date
```

`GLANCE_BRIEF_MODEL_RESPONSE` is reserved for deterministic offline verification;
it bypasses the model adapter and must not be configured on production jobs.

Producer and utility settings remain runtime-owned, including:

```text
LOCAL_OPEN_SOURCE_RADAR_READER   # schema 2 legacy path only
AGENTS_RADAR_COLLECTOR
AGENTS_RADAR_OUTPUT_DIR
AGENTS_RADAR_QUALITY_CONFIG
AGENTS_RADAR_QUALITY_MODULE_DIR
CODEXRADAR_CONFIG
NEWS_AGGREGATOR_SCRIPT
NEWS_SUMMARY_SCRIPT
```

The V2 Agents path consumes the explicitly configured publication directory
instead of guessing a reader path. External news skills are installed
separately. The installer reports missing ones as warnings and does not fetch
them automatically.

## Verification

After installing files, writing `brief.json`, and creating approved jobs:

```bash
python3 install/install.py verify --runtime hermes [--prefix <hermes-home>]
python3 install/install.py doctor --runtime hermes [--prefix <hermes-home>]
```

`verify` fails when owned files drift, the live runtime config is missing/invalid,
or no installed report entry point is wired to Cron. `doctor` is read-only and
adds dependency/runtime hints; it never fetches sources or sends a message.
