# Query Result Processing Reference

`query_processor.py` reads JSON or CSV query results and applies filtering, grouping, aggregation, time bucketing, sorting, and export. Use it when you need post-query analysis beyond what SQL provides.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Filtering](#filtering)
3. [Grouping & Aggregation](#grouping--aggregation)
4. [Time Bucketing](#time-bucketing)
5. [Output & Export](#output--export)
6. [Full Flag Reference](#full-flag-reference)

## Basic Usage

First query data to a file, then process it:

```bash
# Step 1: Export raw query results
python3 <skill-path>/scripts/aepipe_client.py query <project> <logstore> \
  --sql "SELECT blob3, blob4, double1, timestamp FROM aepipe LIMIT 1000" \
  --format json --output raw.json

# Step 2: Process
python3 <skill-path>/scripts/query_processor.py raw.json --format table
```

## Filtering

Filter rows with `--filter` (repeatable for AND logic):

```bash
# Exact match
--filter 'blob4 == "error"'

# Numeric comparison
--filter 'double1 > 100'

# String operations
--filter 'blob3 contains "login"'
--filter 'blob3 startswith "user_"'
--filter 'blob3 endswith "_failed"'
```

Supported operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `startswith`, `endswith`

## Grouping & Aggregation

Group rows and compute aggregates:

```bash
# Count events by type
--group-by blob3 --agg 'count:cnt'

# Multiple aggregations
--group-by blob3 --agg 'count:cnt,sum:double1:total,avg:double1:average'

# Global aggregation (no grouping)
--agg 'count:cnt,max:double1:peak'
```

### Aggregation spec format

`func:field:alias` separated by commas:
- `count:alias` - count rows (no field needed)
- `sum:field:alias` - sum numeric field
- `avg:field:alias` - average numeric field
- `min:field:alias` - minimum value
- `max:field:alias` - maximum value

If alias is omitted, defaults to `func_field` (e.g., `sum_double1`).

## Time Bucketing

Truncate timestamps into buckets for time-series analysis:

```bash
# Hourly event counts
--time-bucket hour --time-field timestamp --agg 'count:cnt'

# Daily error trends
--filter 'blob4 == "error"' --time-bucket day --time-field timestamp --agg 'count:errors'
```

Bucket sizes: `minute`, `hour`, `day`, `week`, `month`

The `--time-field` defaults to `timestamp`. Supports ISO 8601 strings and Unix timestamps.

## Output & Export

```bash
# Formats: table (default), json, csv, jsonl
--format csv --output summary.csv

# Export to SQLite database
--to-sqlite analysis.db --table events

# Show summary statistics instead of data
--stats

# Select specific columns
--select blob3,blob4,double1

# Rename columns
--rename blob3:event,blob4:level

# Sort and limit
--sort-by cnt --desc --limit 20
```

## Full Flag Reference

| Flag | Short | Description |
|------|-------|-------------|
| `input` | (positional) | Input file (JSON or CSV) |
| `--filter` | `-f` | Filter expression (repeatable) |
| `--group-by` | `-g` | Comma-separated grouping fields |
| `--agg` | `-a` | Aggregation spec |
| `--time-bucket` | | Bucket: minute/hour/day/week/month |
| `--time-field` | | Timestamp field name (default: timestamp) |
| `--sort-by` | `-s` | Sort by field |
| `--desc` | | Sort descending |
| `--limit` | `-n` | Limit output rows |
| `--format` | | Output: table/json/csv/jsonl |
| `--output` | `-o` | Write to file |
| `--select` | | Comma-separated columns to include |
| `--rename` | | Rename: old1:new1,old2:new2 |
| `--stats` | | Show summary statistics |
| `--to-sqlite` | | Export to SQLite file |
| `--table` | | SQLite table name (default: data) |

## Example: Full Analysis Pipeline

```bash
# 1. Query raw data
python3 <skill-path>/scripts/aepipe_client.py query myproject mylog \
  --sql "SELECT blob3, blob4, double1, timestamp FROM aepipe LIMIT 5000" \
  --format json --output raw.json

# 2. Error breakdown by event type
python3 <skill-path>/scripts/query_processor.py raw.json \
  --filter 'blob4 == "error"' \
  --group-by blob3 --agg 'count:cnt' --sort-by cnt --desc \
  --format table

# 3. Hourly traffic pattern
python3 <skill-path>/scripts/query_processor.py raw.json \
  --time-bucket hour --time-field timestamp --agg 'count:cnt' \
  --format table

# 4. Export for external analysis
python3 <skill-path>/scripts/query_processor.py raw.json \
  --select blob3,blob4,double1,timestamp \
  --rename blob3:event,blob4:level,double1:duration \
  --to-sqlite analysis.db --table events
```
