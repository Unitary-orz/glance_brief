# reports runtime

`runtime/reports/` is the repository-owned source for the current semantic
handoff runtime. It serves the two production report lines together:

- `agents-report`: AI / Agents ecosystem report;
- `noon-news`: midday news briefing.

Both lines use the same canonical pipeline and renderer. They have separate
source prefetch commands and deployment environment names so one source chain
cannot silently replace the other.

```text
entrypoints/
  agents.py       Hermes-facing Agents orchestration wrapper
  news.py         Hermes-facing News orchestration wrapper
lib/glance_brief/
  adapters.py                 source catalog, normalization, assembly
  input_adapters/             bounded json_file / command_json / snapshot_json drivers
  source_adapters/            registered source-specific payload/publication adapters
    local_open_source_radar.py  local-radar publication adapter
  source_inputs.py            compatibility facade for input_adapters
  contracts.py                canonical data and validation contracts
  profiles.py                 schema-3 Report Plan compiler
  resolve.py                  semantic resolver and fact restoration
  render_report.py            deterministic renderer
  prompts/                    semantic model contracts
tests/                          offline and boundary regression tests
```

## Boundaries

- A source prefetch command owns network/API access, raw snapshots, source
  compatibility, source metadata, and source-specific exceptions.
- `input_adapters/` only loads a bounded payload; `source_inputs.py` is a
  compatibility facade for that package.
- `source_adapters/` is the registry for sources with special payload or
  publication semantics. Generic News sources remain configuration-driven
  through `items_path` and `map` in the Report Plan.
- The core consumes the canonical source contract and owns candidate assembly,
  health gates, ranking, semantic validation, and deterministic rendering.
- The publication layer only mounts producer-owned output into the canonical
  report input. It does not fetch sources or choose a model.
- The Hermes wrappers own orchestration and model metadata. They do not define
  source registries or source health policy.

`report_json` remains a compatibility alias for `snapshot_json`; new configs
should use `snapshot_json`.

## Repository-to-Hermes mapping

Install explicitly with:

```bash
python3 install/install.py install --runtime hermes-reports \
  --components agents-report,noon-news \
  --prefix <hermes-home>
```

The installer maps:

| Repository source | Installed path |
|---|---|
| `runtime/reports/entrypoints/agents.py` | `scripts/glance-brief-reports/entrypoints/agents.py` |
| `runtime/reports/entrypoints/news.py` | `scripts/glance-brief-reports/entrypoints/news.py` |
| `runtime/reports/lib/glance_brief/` | `scripts/glance-brief-reports/lib/glance_brief/` |
| `runtime/reports/cron/*.md` | `scripts/glance-brief-reports/cron-prompts/` |
| generated flat adapters | `scripts/glance-brief-reports/agents.py`, `news.py` |
| `config/brief.reports.example.json` | `data/glance-brief-reports/config/brief.reports.example.json` |

The installed manifest records the source revision, dirty state, and hash of
every owned runtime file. `install.py verify --runtime hermes-reports` checks
that closure, the schema-3 live config, Cron wiring, and required source
bindings. It does not create or edit jobs.

## Required deployment bindings

There is no implicit source-command fallback. The scheduler environment must
provide these paths:

```text
GLANCE_BRIEF_AGENTS_PREFETCH          # required file
GLANCE_BRIEF_AGENTS_PUBLICATION_DIR   # required existing directory
GLANCE_BRIEF_NEWS_PREFETCH            # required file
```

Optional values are report-specific:

```text
GLANCE_BRIEF_AGENTS_DATA
GLANCE_BRIEF_AGENTS_CONFIG
GLANCE_BRIEF_AGENTS_MODEL
GLANCE_BRIEF_AGENTS_PROVIDER
GLANCE_BRIEF_AGENTS_REASONING

GLANCE_BRIEF_NEWS_DATA
GLANCE_BRIEF_NEWS_CONFIG
GLANCE_BRIEF_NEWS_MODEL
GLANCE_BRIEF_NEWS_PROVIDER
GLANCE_BRIEF_NEWS_REASONING
```

The two prefetch commands must print a schema-1 JSON envelope. Agents then
mounts the dated local-radar publication from the explicitly configured
publication directory. A missing binding is a hard error in both `verify` and
`doctor`, before any report Cron run is considered healthy.

## Cron jobs

Use the installer output or `adapters/hermes/jobs.reports.example.json` to
create two outer-Agent jobs:

```text
glance-brief-reports/agents.py
glance-brief-reports/news.py
```

Both jobs use `no_agent: false`, the matching handoff prompt, and the matching
report-specific environment bindings. Keep exactly one enabled writer per
report and destination. The installer never changes scheduler records or
external delivery targets.

## Verification

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s runtime/reports/tests -p 'test_*.py'
python3 install/install.py verify --runtime hermes-reports \
  --prefix <hermes-home>
python3 install/install.py doctor --runtime hermes-reports \
  --prefix <hermes-home>
```

For an offline core check:

```bash
cd /tmp
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/absolute/path/to/repository/runtime/reports/lib \
python3 -B -m glance_brief check \
  --config /absolute/path/to/repository/config/brief.reports.example.json
```
