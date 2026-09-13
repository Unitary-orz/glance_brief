# V2 production runtime source boundary

This directory is the repository-owned, rebuildable source for the current V2
production runtime. The directory name `preview` is retained as a historical
compatibility name for the installer and existing deployment paths; it does not
mean that the active V2 writer is still a shadow deployment. It is intentionally
separate from the schema 2 legacy `glance_brief/` package so the two runtime
lines cannot silently overwrite each other's config, artifacts, or jobs.

```text
entrypoints/
  noon_preview.py       Hermes-facing orchestration wrapper
  agents_preview.py     Hermes-facing orchestration wrapper
lib/glance_brief/
  adapters.py           source catalog, normalization, assembly
  source_inputs.py      json_file / command_json / snapshot_json drivers
  contracts.py          canonical data and validation contracts
  profiles.py           schema-v3 Report Plan compiler
  resolve.py            semantic resolver and fact restoration
  render_report.py      deterministic renderer
  local_radar_publication.py
                        local-radar producer adapter / legacy publication bridge
  prompts/              semantic model contracts
 tests/                 offline adapter and boundary regression tests
```

## Rebuild boundary

- `config/brief.preview.example.json` and
  `tests/fixtures/pipeline/preview-snapshot.json` are the deterministic
  offline input pair.
- A report loads its immutable `input` once. Sources with `driver:
  snapshot_json` receive a view of that same payload through the registered
  input adapter; they do not read a private report artifact in the assembler.
- `report_json` is accepted only as a compatibility alias for
  `snapshot_json`. New configurations use `snapshot_json`.
- The wrappers validate only a generic producer envelope and delegate source
  semantics to the core/source adapter. Required sources and candidate
  minimums are defined in the Report Plan.
- The repository does not contain live Cron metadata, generated reports,
  delivery IDs, credentials, or external source state.

## Hermes deployment mapping

The repository source is installed only through the explicit Preview mode:

```bash
python3 install/install.py install --runtime hermes-preview \
  --components agents-report,noon-news \
  --prefix <hermes-home>
```

The installer maps the tree deliberately rather than copying it blindly:

| Repository source | Installed path |
|---|---|
| `runtime/preview/entrypoints/agents_preview.py` | `scripts/glance-brief-v2/entrypoints/agents_preview.py` |
| `runtime/preview/entrypoints/noon_preview.py` | `scripts/glance-brief-v2/entrypoints/noon_preview.py` |
| `runtime/preview/lib/glance_brief/` | `scripts/glance-brief-v2/lib/glance_brief/` |
| `runtime/preview/cron/*.md` | `scripts/glance-brief-v2/cron-prompts/` |
| generated flat adapters | `scripts/glance-brief-v2/agents-v2.py`, `noon-v2.py` |
| `config/brief.preview.example.json` | `data/glance-brief-v2/config/brief.preview.example.json` |

The installed manifest records the repository `source_revision`, whether the
worktree was dirty at install time, and an SHA-256 entry for every owned runtime
file. `install.py verify --runtime hermes-preview` checks that full closure,
the schema 3 live config, and Cron script wiring. It does not create or edit
Cron jobs.

The runtime accepts deployment-specific values through its environment:
`GLANCE_BRIEF_PREVIEW_CONFIG`, `GLANCE_BRIEF_PREVIEW_PREFETCH`,
`GLANCE_BRIEF_PREVIEW_MODEL`, `GLANCE_BRIEF_PREVIEW_PROVIDER`, and
`GLANCE_BRIEF_PREVIEW_REASONING`. Production jobs should set these explicitly;
only the Agents runtime requires `GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR`, and the
wrapper fails closed when that path is absent instead of guessing a `local-radar`
directory. The default reasoning metadata is `medium`, matching the currently
verified Cron setting, and may be overridden only by an explicit deployment
environment value.

The active Hermes copy under `~/.hermes/scripts/glance-brief-v2` is a separate
installed runtime. Installing or updating this repository mapping does not itself
perform a production cutover: before changing jobs, inspect all enabled writers
for the same report and destination, preserve the old runtime/job records, and
choose one writer per report. Rollback restores the saved runtime tree and
scheduler records together.

## Verification

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  runtime.preview.tests.test_preview_productization

cd /tmp
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/absolute/path/to/repository/runtime/preview/lib \
python3 -B -m glance_brief check \
  --config /absolute/path/to/repository/config/brief.preview.example.json
```
