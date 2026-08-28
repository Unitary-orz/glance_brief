# Local Open-Source Radar Producer

This component independently collects GitHub open-source signals and writes a
current-day structured snapshot. `agents-report` consumes that snapshot through
a runtime-supplied reader; it does not run this producer itself.

## Responsibilities

The producer owns:

- GitHub Trending and Search collection;
- relevance filtering, source-aware ranking, and history-based freshness;
- technical evidence collection for selected new projects;
- the current-day JSON snapshot and its quality status.

The root installer does **not** install or schedule this producer by default.
Keep its collection schedule and report prompt in the runtime that owns the
independent radar. This source package must not contain runtime Job IDs,
message destinations, state files, or generated reports.

## Runtime layout

A deployment may use the following layout:

```text
<runtime-root>/scripts/local-open-source-radar/
  collector.py
  prefetch.py
  read-current.py

<runtime-root>/data/local-open-source-radar/
  config/config.json
  state/state.json
  cache/
  output/
```

Copy `config.example.json` to the runtime data directory and adjust only the
source and output policy settings. Relative paths such as `cache` are resolved
under the local radar data directory. Existing state, cache, and output data
must be preserved when updating code.

The default runtime root is derived from the deployed producer location. A
runtime may override it explicitly with:

```text
LOCAL_OPEN_SOURCE_RADAR_RUNTIME_ROOT
LOCAL_OPEN_SOURCE_RADAR_DATA_DIR
LOCAL_OPEN_SOURCE_RADAR_CONFIG
LOCAL_OPEN_SOURCE_RADAR_STATE
LOCAL_OPEN_SOURCE_RADAR_OUTPUT_DIR
```

`read-current.py` reads the producer snapshot directly. Its structured
`categories` mapping is the source for the report category/project mapping; no
rendered Markdown report directory is required.

## GitHub access

Set `GITHUB_TOKEN` when authenticated GitHub API access is available. If it is
not set, the collector may use the local `gh auth token` credential. Never put
tokens in this repository or in `config.json`.

## Run and verify

Run the producer from its deployment directory or pass explicit paths:

```bash
python3 collector.py \
  --config <runtime-root>/data/local-open-source-radar/config/config.json \
  --state <runtime-root>/data/local-open-source-radar/state/state.json \
  --output-dir <runtime-root>/data/local-open-source-radar/output
```

The cron wrapper is:

```bash
python3 prefetch.py
```

Read today's snapshot without collecting again:

```bash
python3 read-current.py
```

Run the offline test suite from the repository root:

```bash
python3 -m unittest discover -s producers/local-open-source-radar/tests
```
