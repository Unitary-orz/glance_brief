# V2 Preview runtime source boundary

This directory is the repository-owned, rebuildable source for the currently
verified V2 Preview runtime. It is intentionally separate from the formal
`glance_brief/` v0.3.0 package until the two output contracts are deliberately
merged.

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

## Hermes deployment inputs

A deployment may point the wrapper at a runtime-specific configuration,
data root, producer command, and publication directory using:

- `HERMES_HOME`
- `GLANCE_BRIEF_PREVIEW_ROOT`
- `GLANCE_BRIEF_PREVIEW_DATA`
- `GLANCE_BRIEF_PREVIEW_CONFIG`
- `GLANCE_BRIEF_PREVIEW_PREFETCH`
- `GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR`

These are deployment settings, not committed source. The active Hermes copy
under `~/.hermes/scripts/glance-brief-v2` remains unchanged by this source-tree
refactor; syncing it is a separate, explicitly scoped release step.

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
