# OpenClaw adapter contract

`glance_brief v0.3.0` provides a runtime-independent shared core, but it does
**not** yet ship a complete, verified OpenClaw model adapter. Therefore
`jobs.example.json` intentionally contains no runnable jobs. The repository must
not advertise the old producer-plus-prompt pattern as equivalent to the strict
pipeline: it would let an outer model produce the final report without resolver,
provenance, or deterministic-renderer gates.

A future OpenClaw adapter must implement the same boundary as Hermes:

1. call `glance_brief.cli.run_pipeline` with a runtime-owned `model_runner`;
2. perform exactly one model call and return raw JSON plus usage metadata;
3. leave facts, URLs, source labels, dates, metrics, category/fresh state, and
   Markdown under program control;
4. preserve success/failure artifacts and fail closed on invalid model output;
5. deliver only the verified `report.md`.

The runtime must own workspace paths, model/provider settings, timeout, schedule,
and delivery. Real paths, credentials, task IDs, and delivery targets must not be
committed.

Existing producer/utility environment names remain part of the portability
contract and may be used by a future adapter:

```text
LOCAL_OPEN_SOURCE_RADAR_READER
CODEXRADAR_CONFIG
AGENTS_RADAR_OUTPUT_DIR
AGENTS_RADAR_COLLECTOR
AGENTS_RADAR_QUALITY_CONFIG
AGENTS_RADAR_QUALITY_MODULE_DIR
NEWS_AGGREGATOR_SCRIPT
NEWS_SUMMARY_SCRIPT
```

Until the adapter is implemented and covered by an installed-entrypoint test,
use the shared core only for offline validation with an explicit model response:

```bash
python3 -m glance_brief run \
  --config config/brief.example.json \
  --report noon-news \
  --output-dir /tmp/glance-brief-noon \
  --model-response <runtime-supplied-model-response.json>
```
