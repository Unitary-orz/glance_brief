# glance_brief v0.3.0 Runtime Adapters

## Boundary

The shared `glance_brief/` package is runtime-independent. It owns:

- bounded `json_file`, argv-based `command_json`, and shared-snapshot `snapshot_json` input drivers;
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

## Hermes: isolated agent-mode semantic handoff

The same core also supports an outer Cron Agent that owns the one semantic model
turn without generating final Markdown or nesting `hermes chat` in a script:

```text
glance_brief prepare
→ prepared.json + immutable assembled/payload/prompt hashes
→ Cron Agent writes run-scoped semantic JSON
→ glance_brief render-prepared
→ resolver + deterministic report.md
```

`prepare` reads each source once. `render-prepared` verifies the config and
prepared artifact hashes, then renders from the saved registry without reading
sources again. A runtime wrapper may add model/provider usage metadata, but the
shared CLI does not select a Hermes provider.

This mode is the current V2 production agent-handoff runtime in the workspace.
`Preview`/`hermes-preview` are historical source and installer names retained for
path compatibility, not a claim that the active V2 writer is still shadow-only.
Installing or updating the repository mapping remains an explicit file operation:
it does not itself modify Cron jobs, delivery settings, or the active live runtime.

## V2 production source tree and explicit install mapping

The current V2 production runtime is source-owned under `runtime/preview/`. Its
entrypoints, V2 core, Prompt files, schema-v3 example, immutable offline
fixture, Cron handoff prompts, and productization tests are versioned together.
The default schema 2 legacy installer does not touch this tree. An explicit
`install/install.py install --runtime hermes-preview` maps it to
`scripts/glance-brief-v2/`, generates flat `agents-v2.py`/`noon-v2.py` wrappers,
records source revision and hashes for the complete owned closure, and prints
Cron suggestions. It never writes `jobs.json` or delivery settings.

The entrypoints use `GLANCE_BRIEF_PREVIEW_*` environment variables for
deployment-specific paths; no Hermes home, live Cron ID, delivery target,
credential, or generated snapshot is committed. The Agents runtime requires an
explicit `GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR` and fails closed if it is absent, so a
portable default cannot silently point at the wrong local-radar publication.
The default V2 reasoning metadata is `medium`; scheduler/environment values remain
the deployment authority.

The `snapshot_json` input driver is the explicit bridge from one report input
to multiple source views. `report_json` remains a compatibility alias only.
Source health is evaluated by the configured Report Plan after each source has
been attempted, so a failed source is recorded and isolated before the required
component gate decides whether the report may render. The local-radar Markdown
bridge lives in the source adapter module rather than in the wrapper.

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
