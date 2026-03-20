# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**aepipe** is a Cloudflare Worker that serves as a **multi-tenant** HTTP ingestion and query endpoint for structured events, writing them to Cloudflare's Workers Analytics Engine. The isolation hierarchy is:

```
aepipe instance
  └── Project (top-level tenant)
        └── LogStore (log category within a project)
```

No external database — projects and logstores are implicit, encoded into Analytics Engine data points.

## Commands

```bash
npm run dev      # Local dev server (wrangler dev)
npm run deploy   # Deploy to Cloudflare Workers
npm run tail     # Stream live logs from deployed worker
```

No test suite or linter is configured.

## Architecture

Three source files, no framework:

- **`src/index.ts`** — Router, shared types (`Env`, `DataPoint`), auth, CORS, name validation
- **`src/ingest.ts`** — Ingest handler + `mapDataPoint(project, logstore, point)`, structured log handler (`handleLog`)
- **`src/query.ts`** — Query proxy (SQL rewrite + CF API call), raw log query (CF Telemetry API), project/logstore listing

### Routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/{project}/{logstore}/ingest` | Write structured event points to Analytics Engine |
| `POST` | `/v1/{project}/{logstore}/query` | Query structured logs (SQL proxy to Analytics Engine) |
| `POST` | `/v1/{project}/{logstore}/log` | Write raw logs via Workers Observability (console methods) |
| `POST` | `/v1/{project}/{logstore}/rawlog` | Query raw Worker logs via CF Telemetry REST API |
| `GET` | `/v1/projects` | List all projects |
| `GET` | `/v1/{project}/logstores` | List logstores in a project |
| `OPTIONS` | `*` | CORS preflight |

Project and logstore names: validated against `^[a-zA-Z0-9_-]{1,64}$`.

## Environment Bindings (wrangler.toml)

- `LOGS` — AnalyticsEngineDataset binding (dataset: "aepipe")

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
| `blob5`–`blob20` | user `blobs[0..15]` | Max 16 extra blobs |
| `double1`–`double20` | user `doubles[0..19]` | Unchanged |

## Query Tenant Isolation

The query handler auto-injects `blob1 = '{project}' AND blob2 = '{logstore}'` into SQL WHERE clauses, preventing cross-tenant reads.
