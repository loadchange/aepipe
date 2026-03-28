# aepipe

[中文文档](README.zh-CN.md)

**The Edge-Native Log Pipeline for Everyone.**

A high-performance log gateway built on Cloudflare Workers + Analytics Engine — your **free, self-hosted alternative** to Datadog, AWS CloudWatch, and Alibaba Cloud SLS. Kill your overpriced log bills with $0 edge-native ingestion.

## Why aepipe?

In 2026, log services shouldn't be the silent assassin in your monthly cloud bill. aepipe redefines the cost-performance ratio of log ingestion and analysis.

### Comparison with cloud giants

| | Alibaba Cloud SLS | AWS CloudWatch | GCP Cloud Logging | **aepipe** |
|---|---|---|---|---|
| **Pricing** | Index + traffic + storage fees | $0.50/GB ingest + query fees | $0.50/GB ingest | **$0** (Cloudflare free tier) |
| **Query language** | SQL (requires indexing) | Proprietary Insights syntax | Proprietary LQL syntax | **Native SQL** (Analytics Engine) |
| **Deployment** | Install & configure Logtail | Configure CloudWatch Agent | Configure log routers | **Serverless, one-click deploy** |
| **Global reach** | Limited to physical regions | Limited to physical regions | Limited to physical regions | **300+ edge nodes worldwide** |
| **Data ownership** | Vendor-controlled | Vendor-controlled | Vendor-controlled | **100% yours** (your CF account) |
| **Multi-tenancy** | Per-project billing | Per-log-group billing | Per-project billing | **Unlimited projects, $0** |

### Core advantages

**1. Truly free SLS alternative** — Leverages Cloudflare Analytics Engine to bypass the traditional cloud vendor playbook of charging per "scan volume" or "index size". High-concurrency log ingestion and real-time analytics within Cloudflare's free tier.

**2. Dead-simple log funnel** — No complex regex or field mapping configs. Dynamic schema mapping: throw JSON into the pipe, get SQL-queryable structured data out.

**3. Cross-cloud log bridge** — Whether your app runs on AWS EC2, Alibaba Cloud Function Compute, or a Raspberry Pi at home — one HTTP POST sends logs to the nearest global edge node, instantly queryable.

**4. Zero bill anxiety** — Fully open-source, deployed under your own Cloudflare account. No hidden fees, no closed-source black boxes, full data sovereignty.

## How it works

```
Your App ──POST JSON──▶ aepipe (CF Worker) ──writeDataPoint()──▶ Analytics Engine (92 days)
                              │                    │                      │
                              │                    └──payload──▶ D1 (configurable TTL)
                              └──console.log──▶ Workers Logs (7-30 days) │
                                                                   SQL API ◀── You
```

Events are scoped by **Project** and **LogStore** — one deployment serves many teams/apps:

```
aepipe instance
  └── Project (top-level tenant)
        └── LogStore (log category within a project)
```

No external database required. Projects and logstores are implicit, created on first write, discovered via SQL queries. Optional **Cloudflare D1** integration extends storage capacity beyond AE's 16 KB blob limit.

### Dual log storage

aepipe writes every data point to **two** independent storage layers:

| | Analytics Engine (query) | Workers Logs (rawlog) |
|---|---|---|
| **Data format** | Structured (blobs + doubles) | Raw JSON snapshot |
| **Retention** | **92 days** | Free: **7 days** / Paid: **30 days** |
| **Daily limit** | No hard cap on free tier | Free: 200K logs/day (then 1% sampled) |
| **Query method** | SQL via `/query` endpoint | Telemetry API via `/rawlog` endpoint |
| **Best for** | Metrics, aggregations, dashboards | Debugging, audit trail, raw payloads |

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Configure

Edit `wrangler.toml` to customize the dataset name:

```toml
name = "aepipe"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[observability]
enabled = true

[observability.logs]
enabled = true

[[analytics_engine_datasets]]
binding = "LOGS"
dataset = "aepipe"
```

### 3. (Optional) Enable D1 payload storage

D1 extends your log capacity beyond AE's 16 KB blob limit. Large payloads (stack traces, request dumps) are stored in D1 and linked to AE via a UUID.

```bash
# Create the D1 database
npx wrangler d1 create aepipe-payloads
```

Then uncomment the `[[d1_databases]]` block in `wrangler.toml` and paste your `database_id`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "aepipe-payloads"
database_id = "your-database-id-here"
```

The table and indexes are auto-created on first use. No manual migration needed.

### 4. Set secrets

```bash
npx wrangler secret put ADMIN_TOKEN       # shared auth token for all API operations
npx wrangler secret put CF_ACCOUNT_ID     # your Cloudflare account ID
npx wrangler secret put CF_API_TOKEN      # CF API token (Account Analytics Read + Workers Scripts Read)
```

### 5. Deploy

```bash
npm run deploy
```

## API

All endpoints require `Authorization: Bearer <ADMIN_TOKEN>`.

Project and logstore names must match `^[a-zA-Z0-9_-]{1,64}$`.

### Ingest — `POST /v1/{project}/{logstore}/ingest`

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/ingest \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "event": "GET /api/users",
        "level": "info",
        "blobs": ["200", "us-east"],
        "doubles": [42.5]
      },
      {
        "event": "unhandled_exception",
        "level": "error",
        "payload": { "stack": "Error: ...\n  at ...", "request": { "url": "/api/users" } },
        "ttl": 604800
      }
    ]
  }'
```

**Response:** `{ "ok": true, "written": 2 }`

**Request body — `points[]` fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `event` | string | **required** | Event name (non-empty) |
| `level` | string | `"info"` | Log level |
| `blobs` | string[] | `[]` | String metadata for grouping/filtering (max **15**) |
| `doubles` | number[] | `[]` | Numeric metrics for aggregation (max **20**) |
| `payload` | object | | Extended data stored in D1 (requires D1 binding). No 16 KB limit. |
| `ttl` | number | 7776000 | Payload TTL in seconds (default: 90 days) |

**Constraints:**
- `points` must be a non-empty array, max 250 per request
- Points with missing or empty `event` are silently skipped
- When `payload` is set and D1 is configured, the payload is stored in D1 with a UUID reference in AE `blob5`
- When `payload` is set but D1 is **not** configured, the payload is silently ignored

### Write raw log — `POST /v1/{project}/{logstore}/log`

Write free-form log entries to Workers Logs (up to **7 days** on Free / **30 days** on Paid plan).

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/log \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      { "message": "user login failed", "level": "error", "userId": "u-42", "ip": "1.2.3.4" }
    ]
  }'
```

**Response:** `{ "ok": true, "written": 1 }`

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `logs[].message` | string | **yes** | Log message (entries without it are skipped) |
| `logs[].level` | string | no | `debug` / `info` (default) / `warn` / `error` |
| `logs[].*` | any | no | Any extra fields are preserved in the raw JSON |

**Constraints:**
- `logs` must be a non-empty array, max 250 per request
- Level maps to `console.log` / `console.warn` / `console.error` / `console.debug` for filtering in Workers Logs

### Query (structured) — `POST /v1/{project}/{logstore}/query`

Query structured log data from Analytics Engine (up to **92 days**).

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/query \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT blob3 AS event, blob4 AS level FROM aepipe WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR ORDER BY timestamp DESC LIMIT 100"
  }'
```

The worker auto-injects `blob1 = '{project}' AND blob2 = '{logstore}'` into the WHERE clause — users cannot read across tenant boundaries.

### Raw log — `POST /v1/{project}/{logstore}/rawlog`

Query raw JSON snapshots from Workers Logs via the CF Telemetry REST API (up to **7 days** on Free / **30 days** on Paid plan).

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/rawlog \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 50,
    "start": "2026-03-20T00:00:00Z",
    "end": "2026-03-20T12:00:00Z"
  }'
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | number | 50 | Max results (capped at 200) |
| `start` | ISO string | 6 hours ago | Start of time range |
| `end` | ISO string | now | End of time range |

**Response:** `{ "logs": [{ "timestamp": "...", "level": "log", "data": { ... } }], "count": 1 }`

### Fetch D1 payloads — `POST /v1/{project}/{logstore}/detail`

Retrieve extended payloads from D1 by ref_id. Requires D1 binding on the server.

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/detail \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_ids": ["550e8400-e29b-41d4-a716-446655440000"]
  }'
```

**Request body:**

| Field | Type | Description |
|-------|------|-------------|
| `ref_ids` | string[] | UUID references from AE blob5 (max 100 per request) |

**Response:**

```json
{
  "results": [
    {
      "ref_id": "550e8400-e29b-41d4-a716-446655440000",
      "payload": { "stack": "Error: ...", "request": { "url": "/api/users" } },
      "created_at": 1711584000000,
      "expires_at": 1719360000000
    }
  ]
}
```

Returns `501` if D1 is not configured.

### List projects — `GET /v1/projects`

```bash
curl https://aepipe.<subdomain>.workers.dev/v1/projects \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

**Response:** `{ "projects": ["my-app", "backend-svc"] }`

### List logstores — `GET /v1/{project}/logstores`

```bash
curl https://aepipe.<subdomain>.workers.dev/v1/my-app/logstores \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

**Response:** `{ "logstores": ["access-log", "error-log"] }`

## Data point mapping

| AE Field | Content | Notes |
|----------|---------|-------|
| `index1` | `{project}/{logstore}` | Sampling key (max 96 bytes) |
| `blob1` | project name | Tenant filter |
| `blob2` | logstore name | Sub-tenant filter |
| `blob3` | event (required) | User's event string |
| `blob4` | level | Defaults to "info" |
| `blob5` | ref_id (UUID) | D1 payload reference, empty string if no payload |
| `blob6`–`blob20` | user `blobs[0..14]` | Max **15** extra blobs |
| `double1`–`double20` | user `doubles[0..19]` | Up to 20 doubles |

> **Important:** All blobs in a data point share a **16 KB total size limit** (sum of all blob byte lengths, UTF-8). Exceeding this causes **silent data truncation** by Cloudflare. Use `payload` for large data instead.

## D1 payload storage (optional)

Analytics Engine enforces a **16 KB total blob size limit** per data point. Exceeding it causes **silent data truncation** — the write succeeds but data is lost. For large payloads (stack traces, request/response dumps, full error contexts), use the `payload` field instead.

When D1 is configured, data points with a `payload` field get their payload stored in **Cloudflare D1** (SQLite-based serverless database), linked to AE via a UUID in `blob5`. This gives you unlimited payload size with a unified query experience:

1. **Ingest** with `payload` — aepipe generates a UUID, stores the payload in D1, writes the UUID to AE `blob5`
2. **Query** AE to find events — `SELECT blob5 as ref_id FROM aepipe WHERE blob5 != ''`
3. **Detail** fetch — pass `ref_ids` to `/detail` endpoint to retrieve full payloads from D1

**Expiration:** Payloads have a configurable TTL (default: 90 days, matching AE retention). Expired payloads are automatically cleaned up on every D1 read/write operation.

**Without D1:** If D1 is not configured, the `payload` field is silently ignored during ingest, and the `/detail` endpoint returns `501`.

## SDKs

Official SDKs with full type safety, client-side validation (blob size limits, index size, batch constraints), and support for all API features including D1 payload storage.

| SDK | Install | Docs |
|-----|---------|------|
| **JavaScript/TypeScript** | `npm install aepipe-sdk` | [README](sdk/javascript/README.md) |
| **Python** | `pip install aepipe-sdk` | [README](sdk/python/README.md) |

Both SDKs validate Cloudflare's hard limits **before** sending requests, preventing silent data truncation.

## Limits & pricing

aepipe runs on Cloudflare's infrastructure. Here are the platform limits to be aware of:

### Cloudflare Free plan

| Resource | Limit | Exceeded behavior |
|----------|-------|-------------------|
| Worker requests | 100K/day | **Requests fail** (429/5XX) until UTC midnight reset |
| Analytics Engine retention | 92 days | Auto-deleted after expiry |
| Workers Logs retention | 7 days | Auto-deleted after expiry |
| Workers Logs volume | 200K logs/day | Auto-sampled to 1% for remainder of day |

### Cloudflare Paid plan ($5/month)

| Resource | Limit | Exceeded behavior |
|----------|-------|-------------------|
| Worker requests | 10M included, then $0.50/M | Billed per usage |
| Analytics Engine retention | 92 days | Auto-deleted after expiry |
| Workers Logs retention | 30 days | Auto-deleted after expiry |
| Workers Logs volume | 5B logs/day | Auto-sampled to 1% for remainder of day |

All data (Analytics Engine and Workers Logs) is automatically cleaned up after the retention period — no manual action needed.

## Error responses

| Status | Body |
|--------|------|
| 400 | `{ "error": "..." }` — invalid JSON, bad name, empty points, etc. |
| 401 | `{ "error": "unauthorized" }` |
| 404 | `{ "error": "not found" }` |
| 502 | `{ "error": "CF API ..." }` — upstream query failure |

## Claude Code Skill

Install the [query-aepipe](skills/query-aepipe/SKILL.md) skill for Claude Code to interact with your aepipe instance directly:

```bash
npx skills add loadchange/aepipe
```

The skill provides a Python CLI client supporting all API operations (ingest, query, log, rawlog, list projects/logstores) and advanced data processing (filtering, aggregation, time bucketing, SQLite export).

## Development

```bash
npm run dev      # local dev server (wrangler dev)
npm run deploy   # deploy to Cloudflare
npm run tail     # stream live logs
```

## License

[MIT](LICENSE)
