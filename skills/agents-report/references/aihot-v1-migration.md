# AI HOT v1 integration checklist

Use this when an agents-radar cron job or collector consumes AI HOT data. Updating the AI HOT Skill does not automatically migrate scripts that call the API directly.

## Contract mapping

| Legacy compatibility layer | Stable v1 |
|---|---|
| `/api/public/items` | `/api/v1/items` |
| `since=<ISO timestamp>` | `window=24h` or `window=7d` (default timeline semantics) |
| `take=N` | `limit=N` |
| `permalink` | `links.aihot` |
| `url` | `links.original` |
| `source` string | `source.name` |
| `nextCursor` / `hasNext` | `page.nextCursor` / `page.hasMore` |
| `since=<ISO timestamp>` | `window=24h` or `window=7d` |
| `take=N` | `limit=N` |

Use a recognizable non-browser User-Agent such as `aihot-skill/1.3.0 (+https://aihot.virxact.com/aihot-skill/)`; API v1 does not require a custom UA, but it is useful for diagnostics.

## Safe migration sequence

1. Read the actual cron job prompt and its `script` field; do not assume updating the Skill changes the consumer.
2. Update the collector endpoint, time-window parameters, response-field mapping, and prompt references as one targeted change.
3. Preserve the existing output format and unrelated sources.
4. Run the collector against a small real query, e.g. `mode=selected&window=24h&by=timeline&limit=3`.
5. Verify `schemaVersion=1`, `page.count`, `page.hasMore`, `items[*].links.aihot`, and `items[*].links.original` before declaring the migration complete.
6. If the collector partially fails, keep independent report sections usable and mark only the AI HOT-backed section as unavailable; never fill it from another source without saying so.

Do not parse, manufacture, or reuse cursors across endpoints or query parameters. For errors and retry rules, use the current AI HOT Skill's `references/errors.md` and `references/api.md`.
