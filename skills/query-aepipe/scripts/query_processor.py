#!/usr/bin/env python3
"""
Advanced query result processor for aepipe data.

Reads JSON/CSV query results and applies filtering, grouping, aggregation,
time bucketing, sorting, and exports to table/CSV/JSON/SQLite.
"""

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone


def load_data(path):
    """Load data from JSON or CSV file."""
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r") as f:
        if ext == ".csv":
            reader = csv.DictReader(f)
            return list(reader)
        else:
            data = json.load(f)
            # Handle CF Analytics Engine response format
            if isinstance(data, dict):
                if "data" in data:
                    return data["data"]
                if "rows" in data:
                    return data["rows"]
            return data


def parse_filter(expr):
    """
    Parse a simple filter expression like 'field == "value"' or 'field > 10'.
    Returns a function that takes a row dict and returns bool.
    """
    # Match: field op value
    m = re.match(r'(\w+)\s*(==|!=|>=|<=|>|<|contains|startswith|endswith)\s*(.+)', expr.strip())
    if not m:
        print(f"Invalid filter expression: {expr}", file=sys.stderr)
        sys.exit(1)

    field, op, val_str = m.group(1), m.group(2), m.group(3).strip()

    # Strip quotes for string values
    if (val_str.startswith('"') and val_str.endswith('"')) or \
       (val_str.startswith("'") and val_str.endswith("'")):
        val = val_str[1:-1]
        is_str = True
    else:
        try:
            val = float(val_str)
            is_str = False
        except ValueError:
            val = val_str
            is_str = True

    def _filter(row):
        rv = row.get(field, "")
        if not is_str:
            try:
                rv = float(rv)
            except (ValueError, TypeError):
                return False

        if op == "==":
            return rv == val
        elif op == "!=":
            return rv != val
        elif op == ">":
            return rv > val
        elif op == ">=":
            return rv >= val
        elif op == "<":
            return rv < val
        elif op == "<=":
            return rv <= val
        elif op == "contains":
            return str(val) in str(rv)
        elif op == "startswith":
            return str(rv).startswith(str(val))
        elif op == "endswith":
            return str(rv).endswith(str(val))
        return False

    return _filter


def parse_agg_spec(spec):
    """
    Parse aggregation spec like 'count:cnt,sum:field:alias,avg:field:alias'.
    Returns list of (func, field, alias) tuples.
    """
    aggs = []
    for part in spec.split(","):
        tokens = part.strip().split(":")
        func = tokens[0]
        if func == "count":
            alias = tokens[1] if len(tokens) > 1 else "count"
            aggs.append(("count", None, alias))
        elif func in ("sum", "avg", "min", "max"):
            if len(tokens) < 2:
                print(f"Aggregation '{func}' requires a field name.", file=sys.stderr)
                sys.exit(1)
            field = tokens[1]
            alias = tokens[2] if len(tokens) > 2 else f"{func}_{field}"
            aggs.append((func, field, alias))
        else:
            print(f"Unknown aggregation function: {func}", file=sys.stderr)
            sys.exit(1)
    return aggs


def aggregate(rows, group_fields, agg_specs):
    """Group rows and compute aggregations."""
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row.get(f, "") for f in group_fields)
        groups[key].append(row)

    results = []
    for key, group_rows in groups.items():
        result = {}
        for f, v in zip(group_fields, key):
            result[f] = v

        for func, field, alias in agg_specs:
            if func == "count":
                result[alias] = len(group_rows)
            else:
                vals = []
                for r in group_rows:
                    try:
                        vals.append(float(r.get(field, 0)))
                    except (ValueError, TypeError):
                        pass
                if not vals:
                    result[alias] = 0
                elif func == "sum":
                    result[alias] = sum(vals)
                elif func == "avg":
                    result[alias] = round(sum(vals) / len(vals), 4)
                elif func == "min":
                    result[alias] = min(vals)
                elif func == "max":
                    result[alias] = max(vals)

        results.append(result)
    return results


def time_bucket(rows, time_field, bucket):
    """Add a _bucket field based on time truncation."""
    fmt_map = {
        "minute": "%Y-%m-%d %H:%M",
        "hour": "%Y-%m-%d %H:00",
        "day": "%Y-%m-%d",
        "week": None,  # handled separately
        "month": "%Y-%m",
    }

    for row in rows:
        ts_str = row.get(time_field, "")
        if not ts_str:
            row["_bucket"] = "unknown"
            continue

        # Try parsing various timestamp formats
        dt = None
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(ts_str.strip(), fmt)
                break
            except ValueError:
                continue

        # Try unix timestamp
        if dt is None:
            try:
                dt = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                row["_bucket"] = "unknown"
                continue

        if bucket == "week":
            # ISO week
            iso = dt.isocalendar()
            row["_bucket"] = f"{iso[0]}-W{iso[1]:02d}"
        else:
            row["_bucket"] = dt.strftime(fmt_map[bucket])

    return rows


def to_sqlite(rows, db_path, table_name):
    """Export rows to a SQLite database."""
    if not rows:
        print("No data to export.")
        return

    cols = list(rows[0].keys())
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create table
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
    cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    cur.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    # Insert rows
    placeholders = ", ".join("?" for _ in cols)
    for row in rows:
        vals = [str(row.get(c, "")) if row.get(c) is not None else None for c in cols]
        cur.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders})', vals)

    conn.commit()
    conn.close()
    print(f"Exported {len(rows)} rows to {db_path} (table: {table_name})")


def format_table(rows):
    """Format rows as an aligned ASCII table."""
    if not rows:
        return "(empty)"

    cols = list(rows[0].keys())
    widths = {c: len(c) for c in cols}
    str_rows = []
    for row in rows:
        sr = {}
        for c in cols:
            v = row.get(c, "")
            s = str(v) if v is not None else ""
            if len(s) > 60:
                s = s[:57] + "..."
            sr[c] = s
            widths[c] = max(widths[c], len(s))
        str_rows.append(sr)

    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    lines = [header, sep]
    for sr in str_rows:
        lines.append(" | ".join(sr[c].ljust(widths[c]) for c in cols))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Process aepipe query results with filtering, aggregation, and export."
    )
    parser.add_argument("input", help="Input file (JSON or CSV)")
    parser.add_argument("--filter", "-f", action="append",
                        help="Filter expression (e.g. 'blob4 == \"error\"'). Can be repeated.")
    parser.add_argument("--group-by", "-g",
                        help="Comma-separated fields to group by")
    parser.add_argument("--agg", "-a",
                        help="Aggregation spec: count:alias,sum:field:alias,avg:field:alias,...")
    parser.add_argument("--time-bucket", choices=["minute", "hour", "day", "week", "month"],
                        help="Time bucketing granularity (adds _bucket as grouping field)")
    parser.add_argument("--time-field", default="timestamp",
                        help="Field containing timestamps (default: timestamp)")
    parser.add_argument("--sort-by", "-s", help="Field to sort by")
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    parser.add_argument("--limit", "-n", type=int, help="Limit output rows")
    parser.add_argument("--format", choices=["table", "json", "csv", "jsonl"],
                        default="table", help="Output format (default: table)")
    parser.add_argument("--output", "-o", help="Write output to file")
    parser.add_argument("--to-sqlite", help="Export to SQLite database file")
    parser.add_argument("--table", default="data",
                        help="SQLite table name (default: data)")
    parser.add_argument("--select", help="Comma-separated fields to include in output")
    parser.add_argument("--rename", help="Rename columns: old1:new1,old2:new2")
    parser.add_argument("--stats", action="store_true",
                        help="Show summary statistics instead of data")

    args = parser.parse_args()

    # Load data
    rows = load_data(args.input)
    if not rows:
        print("No data in input file.")
        return

    print(f"Loaded {len(rows)} rows", file=sys.stderr)

    # Apply filters
    if args.filter:
        for expr in args.filter:
            fn = parse_filter(expr)
            rows = [r for r in rows if fn(r)]
        print(f"After filtering: {len(rows)} rows", file=sys.stderr)

    # Time bucketing
    if args.time_bucket:
        rows = time_bucket(rows, args.time_field, args.time_bucket)

    # Grouping & aggregation
    if args.group_by or args.agg:
        group_fields = []
        if args.time_bucket:
            group_fields.append("_bucket")
        if args.group_by:
            group_fields.extend(f.strip() for f in args.group_by.split(","))

        if not group_fields:
            group_fields = ["_all"]
            for r in rows:
                r["_all"] = "total"

        agg_specs = parse_agg_spec(args.agg) if args.agg else [("count", None, "count")]
        rows = aggregate(rows, group_fields, agg_specs)

        # Clean up _all placeholder
        if "_all" in group_fields:
            for r in rows:
                r.pop("_all", None)

        print(f"After aggregation: {len(rows)} groups", file=sys.stderr)

    # Rename columns
    if args.rename:
        mapping = {}
        for pair in args.rename.split(","):
            old, new = pair.strip().split(":")
            mapping[old.strip()] = new.strip()
        rows = [{mapping.get(k, k): v for k, v in r.items()} for r in rows]

    # Select columns
    if args.select:
        cols = [c.strip() for c in args.select.split(",")]
        rows = [{c: r.get(c, "") for c in cols} for r in rows]

    # Sort
    if args.sort_by:
        def sort_key(r):
            v = r.get(args.sort_by, "")
            try:
                return (0, float(v))
            except (ValueError, TypeError):
                return (1, str(v))
        rows.sort(key=sort_key, reverse=args.desc)

    # Limit
    if args.limit:
        rows = rows[:args.limit]

    # Stats mode
    if args.stats:
        print_stats(rows)
        return

    # SQLite export
    if args.to_sqlite:
        to_sqlite(rows, args.to_sqlite, args.table)
        return

    # Format output
    fmt = args.format
    if fmt == "json":
        text = json.dumps(rows, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        buf = io.StringIO()
        if rows:
            cols = list(rows[0].keys())
            writer = csv.DictWriter(buf, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
        text = buf.getvalue()
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    else:
        text = format_table(rows)

    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"Wrote {len(rows)} rows to {args.output}", file=sys.stderr)
    else:
        print(text)


def print_stats(rows):
    """Print summary statistics for numeric columns."""
    if not rows:
        print("No data.")
        return

    cols = list(rows[0].keys())
    print(f"Total rows: {len(rows)}\n")

    for col in cols:
        vals = []
        non_null = 0
        for r in rows:
            v = r.get(col)
            if v is not None and v != "":
                non_null += 1
                try:
                    vals.append(float(v))
                except (ValueError, TypeError):
                    pass

        if vals:
            vals.sort()
            total = sum(vals)
            mean = total / len(vals)
            median = vals[len(vals) // 2]
            print(f"[{col}] (numeric, {len(vals)}/{len(rows)} values)")
            print(f"  min={vals[0]}, max={vals[-1]}, sum={round(total, 4)}, "
                  f"avg={round(mean, 4)}, median={median}")
        else:
            # String column — show unique count and top values
            str_vals = [str(r.get(col, "")) for r in rows if r.get(col) is not None and r.get(col) != ""]
            unique = set(str_vals)
            print(f"[{col}] (text, {non_null}/{len(rows)} values, {len(unique)} unique)")
            if len(unique) <= 10:
                from collections import Counter
                top = Counter(str_vals).most_common(10)
                for v, c in top:
                    print(f"  {v}: {c}")
        print()


if __name__ == "__main__":
    main()
