#!/usr/bin/env python3
"""Unified CLI client for all aepipe API operations."""

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
import urllib.error

CONFIG_FILE = os.path.expanduser("~/.config/query-aepipe/config.json")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Config not found at {CONFIG_FILE}", file=sys.stderr)
        print("Run setup_config.py first.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def api_request(config, method, path, body=None):
    """Make an authenticated HTTP request to the aepipe API."""
    url = f"{config['base_url'].rstrip('/')}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {config['admin_token']}",
        "Content-Type": "application/json",
        "User-Agent": "aepipe-client/1.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            err = json.loads(err_body)
        except Exception:
            err = {"error": err_body}
        print(f"HTTP {e.code}: {json.dumps(err, indent=2)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def format_table(rows):
    """Format rows as an aligned ASCII table."""
    if not rows:
        return "(empty)"
    cols = list(rows[0].keys())
    widths = {c: len(c) for c in cols}
    str_rows = []
    for row in rows:
        str_row = {}
        for c in cols:
            val = row.get(c, "")
            s = str(val) if val is not None else ""
            if len(s) > 80:
                s = s[:77] + "..."
            str_row[c] = s
            widths[c] = max(widths[c], len(s))
        str_rows.append(str_row)
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    lines = [header, sep]
    for sr in str_rows:
        lines.append(" | ".join(sr[c].ljust(widths[c]) for c in cols))
    return "\n".join(lines)


def format_output(rows, fmt, output_file=None, label="row"):
    """Format and write rows in the specified format. Shared by all commands."""
    if not rows:
        print(f"No {label}s found.")
        return

    if fmt == "json":
        text = json.dumps(rows, indent=2, ensure_ascii=False)
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    elif fmt == "csv":
        buf = io.StringIO()
        cols = list(rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: json.dumps(r[c], ensure_ascii=False)
                             if isinstance(r[c], (dict, list)) else r.get(c, "")
                             for c in cols})
        text = buf.getvalue()
    else:  # table
        text = format_table(rows)

    if output_file:
        with open(output_file, "w") as f:
            f.write(text)
        print(f"Wrote {len(rows)} {label}(s) to {output_file}")
    else:
        print(text)
        print(f"\n--- {len(rows)} {label}(s) ---")


def cmd_projects(args, config):
    result = api_request(config, "GET", "/v1/projects")
    projects = result.get("projects", [])
    if args.json_output:
        print(json.dumps(projects, indent=2))
    else:
        if not projects:
            print("No projects found.")
        else:
            print(f"Projects ({len(projects)}):")
            for p in sorted(projects):
                print(f"  - {p}")


def cmd_logstores(args, config):
    result = api_request(config, "GET", f"/v1/{args.project}/logstores")
    logstores = result.get("logstores", [])
    if args.json_output:
        print(json.dumps(logstores, indent=2))
    else:
        if not logstores:
            print(f"No logstores found in project '{args.project}'.")
        else:
            print(f"Logstores in '{args.project}' ({len(logstores)}):")
            for ls in sorted(logstores):
                print(f"  - {ls}")


def cmd_ingest(args, config):
    if args.file:
        with open(args.file, "r") as f:
            points = json.load(f)
        if isinstance(points, dict) and "points" in points:
            points = points["points"]
        if not isinstance(points, list):
            print("File must contain a JSON array of data points.", file=sys.stderr)
            sys.exit(1)
    else:
        point = {"event": args.event}
        if args.level:
            point["level"] = args.level
        if args.blobs:
            point["blobs"] = json.loads(args.blobs)
        if args.doubles:
            point["doubles"] = json.loads(args.doubles)
        if args.payload:
            point["payload"] = json.loads(args.payload)
        if args.ttl:
            point["ttl"] = args.ttl
        points = [point]

    total_written = 0
    for i in range(0, len(points), 250):
        batch = points[i:i + 250]
        result = api_request(config, "POST",
                             f"/v1/{args.project}/{args.logstore}/ingest",
                             {"points": batch})
        total_written += result.get("written", 0)

    print(f"Ingested {total_written} point(s) into {args.project}/{args.logstore}")


def cmd_query(args, config):
    result = api_request(config, "POST",
                         f"/v1/{args.project}/{args.logstore}/query",
                         {"sql": args.sql})
    rows = result.get("data", [])
    format_output(rows, args.format, args.output, label="row")


def cmd_log(args, config):
    if args.file:
        with open(args.file, "r") as f:
            logs = json.load(f)
        if isinstance(logs, dict) and "logs" in logs:
            logs = logs["logs"]
        if not isinstance(logs, list):
            print("File must contain a JSON array of log entries.", file=sys.stderr)
            sys.exit(1)
    else:
        entry = {"message": args.message}
        if args.level:
            entry["level"] = args.level
        if args.extra:
            entry.update(json.loads(args.extra))
        logs = [entry]

    total_written = 0
    for i in range(0, len(logs), 250):
        batch = logs[i:i + 250]
        result = api_request(config, "POST",
                             f"/v1/{args.project}/{args.logstore}/log",
                             {"logs": batch})
        total_written += result.get("written", 0)

    print(f"Logged {total_written} entry(ies) to {args.project}/{args.logstore}")


def cmd_detail(args, config):
    result = api_request(config, "POST",
                         f"/v1/{args.project}/{args.logstore}/detail",
                         {"ref_ids": args.ref_ids})

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    results = result.get("results", [])
    format_output(results, args.format, args.output, label="payload")


def cmd_rawlog(args, config):
    body = {}
    if args.limit:
        body["limit"] = args.limit
    if args.start:
        body["start"] = args.start
    if args.end:
        body["end"] = args.end

    result = api_request(config, "POST",
                         f"/v1/{args.project}/{args.logstore}/rawlog",
                         body)

    logs = result.get("logs", [])
    # Normalize data field for display
    for log in logs:
        data = log.get("data", "")
        if isinstance(data, (dict, list)):
            log["data"] = json.dumps(data, ensure_ascii=False)

    format_output(logs, args.format, args.output, label="log")


def main():
    parser = argparse.ArgumentParser(description="aepipe API client")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # projects
    sub.add_parser("projects", help="List all projects")

    # logstores
    p_ls = sub.add_parser("logstores", help="List logstores in a project")
    p_ls.add_argument("project", help="Project name")

    # ingest
    p_in = sub.add_parser("ingest", help="Ingest events")
    p_in.add_argument("project", help="Project name")
    p_in.add_argument("logstore", help="Logstore name")
    p_in.add_argument("--event", help="Event name (single point)")
    p_in.add_argument("--level", help="Log level (default: info)")
    p_in.add_argument("--blobs", help="JSON array of extra blob strings")
    p_in.add_argument("--doubles", help="JSON array of numeric values")
    p_in.add_argument("--payload", help="JSON object for D1 extended storage (avoids AE 16KB truncation)")
    p_in.add_argument("--ttl", type=int, help="Payload TTL in seconds (default: 90 days)")
    p_in.add_argument("--file", help="JSON file with array of data points")

    # query
    p_q = sub.add_parser("query", help="Query logs with SQL")
    p_q.add_argument("project", help="Project name")
    p_q.add_argument("logstore", help="Logstore name")
    p_q.add_argument("--sql", required=True, help="SQL query")
    p_q.add_argument("--format", choices=["table", "json", "csv", "jsonl"],
                     default="table", help="Output format (default: table)")
    p_q.add_argument("--output", "-o", help="Write output to file")

    # log
    p_log = sub.add_parser("log", help="Write structured logs")
    p_log.add_argument("project", help="Project name")
    p_log.add_argument("logstore", help="Logstore name")
    p_log.add_argument("--message", "-m", help="Log message (single entry)")
    p_log.add_argument("--level", help="Log level (default: info)")
    p_log.add_argument("--extra", help="JSON object with extra fields")
    p_log.add_argument("--file", help="JSON file with array of log entries")

    # detail
    p_dt = sub.add_parser("detail", help="Fetch extended payloads from D1 by ref_ids")
    p_dt.add_argument("project", help="Project name")
    p_dt.add_argument("logstore", help="Logstore name")
    p_dt.add_argument("ref_ids", nargs="+", help="One or more ref_id UUIDs (from blob5)")
    p_dt.add_argument("--format", choices=["table", "json", "csv", "jsonl"],
                     default="json", help="Output format (default: json)")
    p_dt.add_argument("--output", "-o", help="Write output to file")

    # rawlog
    p_rl = sub.add_parser("rawlog", help="Query raw Worker logs")
    p_rl.add_argument("project", help="Project name")
    p_rl.add_argument("logstore", help="Logstore name")
    p_rl.add_argument("--limit", type=int, help="Max invocations (default: 50, max: 200)")
    p_rl.add_argument("--start", help="Start time (ISO format)")
    p_rl.add_argument("--end", help="End time (ISO format)")
    p_rl.add_argument("--format", choices=["table", "json", "csv", "jsonl"],
                     default="table", help="Output format (default: table)")
    p_rl.add_argument("--output", "-o", help="Write output to file")

    args = parser.parse_args()
    config = load_config()

    cmds = {
        "projects": lambda: cmd_projects(args, config),
        "logstores": lambda: cmd_logstores(args, config),
        "ingest": lambda: cmd_ingest(args, config),
        "query": lambda: cmd_query(args, config),
        "log": lambda: cmd_log(args, config),
        "detail": lambda: cmd_detail(args, config),
        "rawlog": lambda: cmd_rawlog(args, config),
    }

    # Pre-flight validation
    if args.command == "ingest" and not args.file and not args.event:
        print("Either --event or --file is required.", file=sys.stderr)
        sys.exit(1)
    if args.command == "log" and not args.file and not args.message:
        print("Either --message or --file is required.", file=sys.stderr)
        sys.exit(1)

    cmds[args.command]()


if __name__ == "__main__":
    main()
