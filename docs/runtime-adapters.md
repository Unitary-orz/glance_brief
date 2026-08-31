# glance_brief v0.3.0 Runtime Adapters

## Boundary

The shared `glance_brief/` package is runtime-independent. It owns:

- bounded `json_file` and argv-based `command_json` source loading;
- immutable candidates and provenance;
- lean model prompts;
- model-response validation and hard gates;
- resolution, deterministic Markdown, artifacts, manifests, and replay.

A runtime adapter owns only:

- runtime paths and external source entry points;
- one model invocation and usage metadata;
- model/provider/reasoning/timeout configuration;
- schedule, timezone, and delivery;
- process-level failure reporting.

Real job IDs, chat IDs, credentials, user paths, and private model configuration
must never be committed.

## Hermes: verified in v0.3.0

`install/install.py` installs the shared core and thin Hermes report entry points.
Each report entry point runs the complete batch pipeline:

```text
sources
→ candidate registry
→ lean prompt
→ one Hermes model call
→ strict JSON parser
→ resolver + hard gates
→ deterministic renderer
→ verified report.md on stdout
```

The report Cron jobs use `no_agent: true`. This means the scheduler does not
start a second outer Agent; it does **not** mean the task performs no model call
or has no token cost. Adding an outer Cron prompt would break the post-model
validation boundary.

The core never imports Hermes. `hermes chat` and optional model/provider overrides
exist only in the installed Hermes adapter. See `adapters/hermes/INSTALL.md`.

Before scheduler wiring, the installing Agent must create a real schema 2
`data/glance-brief/config/brief.json`. The installed example points at repository
fixtures and is not a live configuration.

## OpenClaw: contract only in v0.3.0

No verified OpenClaw model adapter is shipped. `adapters/openclaw/jobs.example.json`
therefore contains no runnable jobs. A future adapter must inject one model runner
into the shared core and preserve the same fail-closed artifact and renderer
boundary before it can advertise scheduler templates.

The old pattern of running a producer and asking an outer task prompt to format
the final report is not equivalent and is not supported as the v0.3.0 strict
pipeline.

## Repository policy

May be committed:

- example JSON/environment files without private values;
- runtime-independent adapter code;
- placeholder scheduler templates;
- deterministic fixtures and verification scripts.

Must not be committed:

- real job/chat/delivery identifiers;
- API keys, tokens, passwords, cookies, or connection strings;
- generated source snapshots, artifacts, or reports;
- user model/provider configuration;
- machine-specific absolute runtime paths.
