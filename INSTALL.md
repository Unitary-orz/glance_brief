# glance_brief v0.3.0 Agent Installation Contract

This is the installation contract for an Agent with terminal, file, and scheduler
access. `glance_brief v0.3.0` installs two reports on one shared strict pipeline:

- `agents-report` — AI / Agents ecosystem report;
- `noon-news` — midday news briefing.

The installer is idempotent and stdlib-only. It copies project-owned files,
preserves user config/state/output, records hashes, and reports scheduler changes.
It never creates, edits, or removes jobs directly.

## Supported runtime modes

Hermes is verified in two intentionally separate modes:

- `hermes` — retained schema 2 legacy batch runtime;
- `hermes-preview` — current V2 production agent-handoff runtime. `preview` is a
  historical installer/runtime name kept for compatibility; it does not mean the
  installed V2 writer is still a shadow deployment.

OpenClaw currently has an adapter contract only and intentionally advertises no
runnable jobs.

Hermes layout:

```text
<hermes-home>/scripts/glance-brief/   shared core, report adapters, producer libraries
<hermes-home>/data/glance-brief/      config, state, cache, output, install manifest
```

## Architecture boundary

The schema 2 `glance_brief` package is runtime-independent. It owns source
assembly, model payload construction, response validation, resolution,
deterministic rendering, artifacts, and replay. It never imports Hermes or
selects a provider.

The V2 production source tree is separately owned under `runtime/preview/` and
contains its own schema 3 core, Report Plan and agent-handoff entry points. The
repository keeps the schema 2 legacy line for compatibility and rollback; it is
not the implementation used by the current V2 production writer.

The installed schema 2 Hermes report entry point owns one model invocation and
returns raw JSON to its core. Its scheduler job therefore uses `no_agent: true`:
this disables the outer scheduler Agent, not the model call inside the batch
process. The V2 production jobs use the separate agent-handoff path described
below and must not be conflated with this legacy mode. Neither mode is a
zero-token mode.

## Discovery before changes

1. Read `install/install-manifest.json` and this document.
2. Detect `$HERMES_HOME` or use `~/.hermes`.
3. Inspect any installed manifest and jobs that reference
   `glance-brief/*.py`; do not guess paths or job IDs.
4. Check reported Python dependencies and external news skills.
5. Ask the user only for decisions that cannot be discovered locally.

Required user decisions before job creation:

- components to install;
- schedule and timezone;
- delivery platform and target;
- whether optional missing dependencies/skills may be installed;
- model/provider override only when the Hermes runtime default is unsuitable.

Do not create or alter a job or delivery target before those values are approved.

## 1. Dry-run and install

```bash
python3 install/install.py install --runtime hermes \
  [--components agents-report,noon-news] \
  [--prefix <hermes-home>] \
  [--dry-run]
```

The command installs:

- `lib/glance_brief/` shared core and stable Prompt contracts;
- selected component producer libraries;
- `glance-brief.py` plus selected report/utility entry points;
- `config/brief.example.json` and selected component config templates;
- an installed manifest with project version and owned-file SHA-256 hashes.

Reinstallation updates owned code but does not overwrite existing config files.
The JSON result includes warnings, `required_setup`, and `jobs_to_create`.

## 2. Create the live schema 2 config

The installer deliberately does not create live `brief.json`: the repository
example points at offline fixtures and is not a production source configuration.
Create and validate:

```text
<hermes-home>/data/glance-brief/config/brief.json
```

Use `brief.example.json` as a structural template, then replace fixture paths with
real bounded `json_file` or argv-based `command_json` sources. The config must
contain every installed report.

Validate before creating jobs:

```bash
<hermes-home>/scripts/glance-brief/glance-brief.py check \
  --config <hermes-home>/data/glance-brief/config/brief.json
```

Do not place credentials, shell strings, chat IDs, or delivery data in this file.
`command_json` must remain an argv array with its explicit environment allowlist.

## 3. Create approved schema 2 legacy Hermes jobs

Use Hermes' native scheduler interface and the `jobs_to_create` suggestions.
Report scripts are relative to `$HERMES_HOME/scripts/`:

```text
glance-brief/agents-report.py
glance-brief/noon-news.py
```

Each report job must use:

```json
{"no_agent": true}
```

Do not attach `prompt`, `prompt_file`, `model`, `provider`, or `skills` to the
script-only job. The installed Hermes adapter uses the runtime default model and
provider. Optional overrides belong in the scheduler process environment:

```text
GLANCE_BRIEF_MODEL
GLANCE_BRIEF_PROVIDER
GLANCE_BRIEF_REASONING
GLANCE_BRIEF_TIMEOUT
```

Set schedule and delivery only from the user-approved values. Never commit real
job IDs, chat IDs, credentials, or user model configuration.

## 2A. Current V2 agent-handoff runtime (historical installer name)

The V2 source-owned runtime is installed only by an explicit opt-in; the default
`--runtime hermes` path above remains the schema 2 legacy batch runtime. The
explicit `hermes-preview` name is retained so existing deployment automation can
be inspected and migrated without silently changing paths.

```bash
python3 install/install.py install --runtime hermes-preview \
  --components agents-report,noon-news \
  --prefix <hermes-home>
```

This maps the committed `runtime/preview/` tree to:

```text
<hermes-home>/scripts/glance-brief-v2/
  agents-v2.py, noon-v2.py       flat Cron entry points
  entrypoints/                    source entrypoint copies
  lib/glance_brief/               complete V2 core + prompts
  cron-prompts/                   self-contained handoff prompts
<hermes-home>/data/glance-brief-v2/
  config/brief.preview.example.json
  config/brief-live.json          user-authored schema 3 config
  install-manifest.json           source revision + owned-file hashes
```

The installer also prints `jobs_to_create` with `no_agent: false`, the handoff
prompt, and the required deployment environment variables. It never edits
`jobs.json`, creates a delivery target, or enables a job. Set these values in the
scheduler process rather than committing them:

```text
GLANCE_BRIEF_PREVIEW_CONFIG
GLANCE_BRIEF_PREVIEW_PREFETCH
GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR   # required for Agents; use the actual dated local-radar publication root
GLANCE_BRIEF_PREVIEW_MODEL
GLANCE_BRIEF_PREVIEW_PROVIDER
GLANCE_BRIEF_PREVIEW_REASONING         # default medium
```

Copy and customize the installed V2 example to `brief-live.json`, replace
fixture paths with production source paths, then validate it with:

```bash
<hermes-home>/scripts/glance-brief-v2/agents-v2.py --help
<hermes-home>/scripts/glance-brief-v2/noon-v2.py --help
python3 install/install.py verify --runtime hermes-preview --prefix <hermes-home>
```

Before creating V2 jobs, inspect the scheduler for the corresponding schema 2
legacy writers and choose exactly one writer per report and destination. Do not
enable both lines merely because each passes its own health checks. Keep the old
runtime tree and exact job records until the current V2 schedule is accepted;
rollback means restoring both from that backup. The sample mapping is also
available at `adapters/hermes/jobs.preview.example.json`.

## 4. Verify

After writing `brief.json` and creating approved jobs:

```bash
python3 install/install.py verify --runtime hermes [--prefix <hermes-home>]
```

Exit code 0 requires:

- installed manifest present;
- only the selected components' entry points present;
- all owned library hashes matching;
- installed templates present;
- live `brief.json` parseable as schema 2 and containing every selected report;
- at least one installed report entry point wired to Hermes Cron.

A missing live config is a hard failure because the installed report entry points
cannot run without it.

## 5. Doctor

```bash
python3 install/install.py doctor --runtime hermes [--prefix <hermes-home>]
```

`doctor` is read-only. It checks component completeness and reports optional
runtime/dependency hints. It never fetches sources or sends messages:

- `ok` — complete;
- `warn` — optional dependency, unwired job, stale/error hint, or missing delivery;
- `error` — broken owned file, unparseable required config, or missing entry point.

## 6. Uninstall

```bash
python3 install/install.py uninstall --runtime hermes \
  [--prefix <hermes-home>] [--dry-run]
```

The installer removes only files listed as project-owned and reports
`jobs_to_detach`. Detach approved jobs through Hermes' native scheduler interface.
User config, state, cache, and output are preserved by default.

## Invariants

- Never bypass resolver/validator/rendering by asking an outer Agent to write the
  final report.
- Never overwrite user config on reinstall.
- Never modify unrelated jobs, schedules, delivery targets, or credentials.
- Never commit runtime paths, real delivery IDs, generated reports, or secrets.
- Invalid model output must leave failure artifacts and no `report.md`.
- Installer operations must remain stdlib-only and scheduler writes must remain
  outside `install.py`.
