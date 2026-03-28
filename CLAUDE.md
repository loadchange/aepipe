# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**aepipe** is a Cloudflare Worker that serves as a **multi-tenant** HTTP ingestion and query endpoint for structured events, writing them to Cloudflare's Workers Analytics Engine. The isolation hierarchy is:

```
aepipe instance
  └── Project (top-level tenant)
        └── LogStore (log category within a project)
```

Projects and logstores are implicit, encoded into Analytics Engine data points. An **optional Cloudflare D1** database provides extended payload storage for data exceeding AE's 16 KB blob limit.

## Commands

```bash
npm run dev      # Local dev server (wrangler dev)
npm run deploy   # Deploy to Cloudflare Workers
npm run tail     # Stream live logs from deployed worker
```

No test suite or linter is configured.

## Architecture

Four source files, no framework:

- **`src/index.ts`** — Router, shared types (`Env`, `DataPoint`), auth, CORS, name validation
- **`src/ingest.ts`** — Ingest handler + `mapDataPoint(project, logstore, point, refId?)`, structured log handler (`handleLog`)
- **`src/query.ts`** — Query proxy (SQL rewrite + CF API call), raw log query (CF Telemetry API), detail query (D1), project/logstore listing
- **`src/store.ts`** — D1 payload storage layer (table init, expiration cleanup, batch write/read)

### Routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/{project}/{logstore}/ingest` | Write structured event points to Analytics Engine |
| `POST` | `/v1/{project}/{logstore}/query` | Query structured logs (SQL proxy to Analytics Engine) |
| `POST` | `/v1/{project}/{logstore}/log` | Write raw logs via Workers Observability (console methods) |
| `POST` | `/v1/{project}/{logstore}/rawlog` | Query raw Worker logs via CF Telemetry REST API |
| `POST` | `/v1/{project}/{logstore}/detail` | Fetch extended payloads from D1 by ref_ids |
| `GET` | `/v1/projects` | List all projects |
| `GET` | `/v1/{project}/logstores` | List logstores in a project |
| `OPTIONS` | `*` | CORS preflight |

Project and logstore names: validated against `^[a-zA-Z0-9_-]{1,64}$`.

## Environment Bindings (wrangler.toml)

- `LOGS` — AnalyticsEngineDataset binding (dataset: "aepipe")
- `DB` — (Optional) D1Database binding for extended payload storage. Enable by uncommenting the `[[d1_databases]]` block in `wrangler.toml`.

### Secrets (set via `npx wrangler secret put`)

- `ADMIN_TOKEN` — Bearer token for all API operations
- `CF_ACCOUNT_ID` — Cloudflare account ID (for query/rawlog API calls)
- `CF_API_TOKEN` — Cloudflare API token (requires **Account Analytics Read** + **Workers Scripts Read** permissions)

## Data Point Mapping

| AE Field | Content | Notes |
|----------|---------|-------|
| `index1` | `{project}/{logstore}` | Sampling key for efficient scoping |
| `blob1` | project name | Top-level tenant filter |
| `blob2` | logstore name | Sub-tenant filter |
| `blob3` | event (required) | User's event string |
| `blob4` | level | Defaults to "info" |
| `blob5` | ref_id (UUID) | D1 payload reference, empty string if no payload |
| `blob6`–`blob20` | user `blobs[0..14]` | Max 15 extra blobs |
| `double1`–`double20` | user `doubles[0..19]` | Unchanged |

## Query Tenant Isolation

The query handler auto-injects `blob1 = '{project}' AND blob2 = '{logstore}'` into SQL WHERE clauses, preventing cross-tenant reads.

## D1 Payload Storage (Optional)

When D1 is configured, data points with a `payload` field get their payload stored in D1 with a UUID reference in AE `blob5`. This overcomes AE's 16 KB blob size limit.

### D1 Table: `payloads`

| Column | Type | Description |
|--------|------|-------------|
| `ref_id` | TEXT PRIMARY KEY | UUID linking to AE blob5 |
| `payload` | TEXT NOT NULL | JSON string |
| `created_at` | INTEGER NOT NULL | Unix timestamp (ms) |
| `expires_at` | INTEGER NOT NULL | Unix timestamp (ms) |

### Expiration

- Default TTL: 90 days (matches AE retention)
- User can specify `ttl` (seconds) per data point
- Every D1 read/write first cleans up expired rows (`DELETE ... WHERE expires_at <= now LIMIT 1000`)
- Table and index are auto-created on first D1 access (lazy init)
