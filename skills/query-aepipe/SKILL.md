---
name: query-aepipe
description: "Interact with aepipe Analytics Engine API -- query structured logs, ingest events, fetch D1 extended payloads, list projects/logstores, and process results. Use this skill whenever the user mentions aepipe, analytics engine logs, log querying, event ingestion, logstore management, D1 payloads, data truncation prevention, or wants to analyze/export/visualize data from their aepipe instance. Also triggers for aepipe config setup, connectivity checks, or working with structured event data in Cloudflare Analytics Engine or D1."
---

# query-aepipe

A CLI toolkit for the aepipe HTTP API -- a multi-tenant log ingestion and query service backed by Cloudflare Analytics Engine, with optional D1 extended payload storage.

Python 3.8+ required. No pip dependencies (uses stdlib only).

## Before You Start

Check if `~/.config/query-aepipe/config.json` exists. If not, run setup:

```bash
python3 <skill-path>/scripts/setup_config.py --base-url https://your-worker.example.com --token YOUR_TOKEN
```

This validates connectivity and saves the config. All subsequent commands read from this file.

## Which Command to Use

| Goal | Command | Key Flags |
|------|---------|----------|
| See all projects | `projects` | |
| See logstores in a project | `logstores <project>` | |
| Write events to AE | `ingest <proj> <log>` | `--event`, `--file`, `--payload`, `--ttl` |
| Query events with SQL | `query <proj> <log>` | `--sql`, `--format`, `-o` |
| Write structured logs | `log <proj> <log>` | `--message`, `--level`, `--extra`, `--file` |
| Query raw Worker logs | `rawlog <proj> <log>` | `--start`, `--end`, `--limit` |
| Fetch D1 payloads by ref_id | `detail <proj> <log> <ids...>` | `--format`, `-o` |

All commands: `python3 <skill-path>/scripts/aepipe_client.py <command> [args]`

All query/rawlog/detail commands support `--format table|json|csv|jsonl` and `--output FILE`.

## Query SQL Field Mapping

The query endpoint talks to Cloudflare Analytics Engine SQL. Use these column names:

| Column | Meaning | Notes |
|--------|---------|-------|
| `blob1` | project | Auto-filtered, don't include in WHERE |
| `blob2` | logstore | Auto-filtered, don't include in WHERE |
| `blob3` | event | User-provided event name |
| `blob4` | level | "info", "warn", "error", "debug" |
| `blob5` | ref_id | D1 payload UUID (empty string if none) |
| `blob6`-`blob20` | user blobs[0..14] | Up to 15 extra strings |
| `double1`-`double20` | user doubles[0..19] | Numeric fields |
| `timestamp` | event time | |
| `_sample_interval` | sampling factor | For accurate counts: `SUM(_sample_interval)` |

The query endpoint automatically injects `blob1 = '{project}' AND blob2 = '{logstore}'`. Don't add these yourself.

Example:
```sql
SELECT blob3 AS event, blob4 AS level, count() AS cnt
FROM aepipe
GROUP BY event, level ORDER BY cnt DESC LIMIT 20
```

## D1 Extended Payload Storage

Analytics Engine has a **16 KB total blob size limit** per data point. Exceeding it causes **silent truncation** with no error. For larger data, use the `payload` field:

### Writing payloads

Include `payload` (JSON object) in your data point. The server stores it in D1 and puts a UUID reference in AE `blob5`:

```bash
# Single event with payload
python3 <skill-path>/scripts/aepipe_client.py ingest myproject mylog \
  --event "api_trace" --payload '{"request":{"body":"large..."},"response":{"body":"large..."}}'

# With custom TTL (7 days instead of default 90 days)
python3 <skill-path>/scripts/aepipe_client.py ingest myproject mylog \
  --event "temp_debug" --payload '{"stack":"..."}' --ttl 604800
```

Batch ingest with payloads via `--file` works too -- include `payload` and optional `ttl` per point in the JSON array.

### Reading payloads

Two-step process: query AE to find ref_ids, then fetch from D1:

```bash
# Step 1: Find events with payloads (blob5 is non-empty)
python3 <skill-path>/scripts/aepipe_client.py query myproject mylog \
  --sql "SELECT blob3, blob5 AS ref_id, timestamp FROM aepipe WHERE blob5 != '' ORDER BY timestamp DESC LIMIT 20" \
  --format json

# Step 2: Fetch full payloads from D1 using ref_ids from step 1
python3 <skill-path>/scripts/aepipe_client.py detail myproject mylog \
  <ref_id_1> <ref_id_2> --format json
```

The detail endpoint returns `{results: [{ref_id, payload, created_at, expires_at}]}`. Max 100 ref_ids per request.

## Common Workflows

### Explore the system

```bash
python3 <skill-path>/scripts/aepipe_client.py projects
python3 <skill-path>/scripts/aepipe_client.py logstores myproject
python3 <skill-path>/scripts/aepipe_client.py query myproject mylog \
  --sql "SELECT blob3 AS event, blob4 AS level, timestamp FROM aepipe ORDER BY timestamp DESC LIMIT 20"
```

### Error analysis

```bash
# Export raw data, then analyze with query_processor
python3 <skill-path>/scripts/aepipe_client.py query myproject mylog \
  --sql "SELECT blob3, blob4, double1, timestamp FROM aepipe LIMIT 5000" \
  --format json --output raw.json

python3 <skill-path>/scripts/query_processor.py raw.json \
  --filter 'blob4 == "error"' \
  --group-by blob3 --agg 'count:cnt' --sort-by cnt --desc --format table
```

### Structured logging (Workers Observability)

```bash
python3 <skill-path>/scripts/aepipe_client.py log myproject mylog \
  --message "deploy completed" --level info --extra '{"version":"1.2.3"}'
```

The `log` endpoint writes to Workers Observability (not AE). Query these with `rawlog`.

## Advanced Processing

For post-query filtering, grouping, aggregation, time bucketing, and export to SQLite/CSV, use `query_processor.py`. Read `<skill-path>/references/processing.md` for the full reference.

Quick example:
```bash
python3 <skill-path>/scripts/query_processor.py raw.json \
  --time-bucket hour --time-field timestamp --agg 'count:cnt' --format table
```
