# glance_brief Agent Installation Contract

This document is the contract for installing `glance_brief` into an Agent
runtime (Hermes today; OpenClaw is a future adapter). It is written for an
installing agent with terminal/file/job-control access, not for end users
typing commands by hand. End users can hand this repository to their agent.

Installation must be **idempotent**: running it again updates project-owned
files without duplicating jobs, resetting schedules, or overwriting user
config. Uninstalling removes only what this project owns.

## Scope

Two installable reports:

- `agents-report` — AI / Agents ecosystem daily report
- `noon-news` — midday news briefing

Supported runtime: `hermes`. Files are placed under the runtime home
(`$HERMES_HOME`, default `~/.hermes`):

```text
<hermes-home>/scripts/glance-brief/        entry points + lib/ (project-owned)
<hermes-home>/data/glance-brief/           config, state, cache, output, manifest
```

## Discovery (before touching anything)

1. Read `install/install-manifest.json`.
2. Detect the runtime home: `$HERMES_HOME` or `~/.hermes`.
3. Inspect existing installed files at
   `<hermes-home>/data/glance-brief/install-manifest.json` and the Cron jobs
   that reference `scripts/glance-brief/`.
4. Check Python dependencies (`feedparser`) and external skills
   (`news-aggregator-skill`, `news-summary`) — `install.py` reports them.
5. Do not ask the user for facts discoverable locally.

## User decisions (ask only these)

- Which components to install (`agents-report`, `noon-news`, or both).
- Schedule and timezone for each report job (defaults are in the manifest).
- Delivery target (platform and chat id).
- Whether missing external skills may be installed, and from where.
- Model/provider for the jobs, when not using the runtime default.

Do not create or alter scheduled jobs or external delivery targets before the
user approves the job preview.

## Install

```bash
python3 install/install.py install --runtime hermes \
  [--components agents-report,noon-news] [--prefix <hermes-home>] [--dry-run]
```

This copies the library modules and adapter entry points under
`scripts/glance-brief/`, creates the data directories, seeds default config
from `skills/*/config/*.example.json` (only when the target does not exist),
and writes the installed manifest with file hashes.

`--dry-run` prints the exact plan without writing anything. JSON output is
machine-readable for the agent; it includes:

- `missing_python_deps`, `missing_external_skills` — warnings to resolve
- `jobs_to_create` — suggested jobs: `script` (relative to
  `<hermes-home>/scripts/`), `prompt`, `default_schedule`

Create the jobs with the runtime's job interface (Hermes: `cronjob`), using
the suggested values plus the user-approved schedule/delivery/model. Keep the
job `script` as the relative path printed (`glance-brief/<entrypoint>.py`).

## Verify

```bash
python3 install/install.py verify --runtime hermes [--prefix <hermes-home>]
```

Exit code 0 means: installed manifest present, all entry points exist, every
library file matches its recorded hash, default config files exist, and at
least one Cron job is wired to a `glance-brief/` entry point. Report the
failing checks to the user; a job whose prefetch output is stale is not a
verify failure — the report is produced by the scheduled job itself.

## Uninstall

```bash
python3 install/install.py uninstall --runtime hermes \
  [--prefix <hermes-home>] [--dry-run]
```

Removes only files listed in the installed manifest and reports
`jobs_to_detach`. It preserves `<hermes-home>/data/glance-brief/` user
config/state/output by default. After the dry-run is approved, remove the
reported jobs with the runtime job interface, then run uninstall again to
delete the files.

## Invariants (do not break)

- Never modify the committed prompt files (`skills/*/prompts/*-v2.md`) or the
  report layout contract (`docs/output-contracts.md`) during installation.
- Never change existing schedules, models, providers, delivery targets, or
  credentials of unrelated jobs.
- Never embed runtime paths, chat ids, job ids, or credentials into committed
  files. Runtime paths belong in the adapter entry points written by
  `install.py`.
- Keep `schema_version: 1` in prefetch payloads and source failures as
  `ok:false + error + items:[]`.
- No third-party Python dependencies for the installer itself (stdlib only).
