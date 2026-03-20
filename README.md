# aepipe

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
Your App ──POST JSON──▶ aepipe (CF Worker) ──writeDataPoint()──▶ Analytics Engine
                                                                        │
                                                                   SQL API ◀── You
```

Events are scoped by **Project** and **LogStore** — one deployment serves many teams/apps:

```
aepipe instance
  └── Project (top-level tenant)
        └── LogStore (log category within a project)
```

No external database. Projects and logstores are implicit, created on first write, discovered via SQL queries.

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

[[analytics_engine_datasets]]
binding = "LOGS"
dataset = "aepipe"
```

### 3. Set secrets

```bash
npx wrangler secret put ADMIN_TOKEN       # shared auth token for all API operations
npx wrangler secret put CF_ACCOUNT_ID     # Cloudflare account ID (for query API)
npx wrangler secret put CF_API_TOKEN      # CF API token with Analytics Engine read permission
```

### 4. Deploy

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
      }
    ]
  }'
```

**Response:** `{ "ok": true, "written": 1 }`

**Constraints:**
- `points` must be a non-empty array, max 250 per request
- Points with missing or empty `event` are silently skipped

### Query — `POST /v1/{project}/{logstore}/query`

```bash
curl -X POST https://aepipe.<subdomain>.workers.dev/v1/my-app/access-log/query \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT blob3 AS event, blob4 AS level FROM aepipe WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR ORDER BY timestamp DESC LIMIT 100"
  }'
```

The worker auto-injects `blob1 = '{project}' AND blob2 = '{logstore}'` into the WHERE clause — users cannot read across tenant boundaries.

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
| `index1` | `{project}/{logstore}` | Sampling key |
| `blob1` | project name | Tenant filter |
| `blob2` | logstore name | Sub-tenant filter |
| `blob3` | event (required) | User's event string |
| `blob4` | level | Defaults to "info" |
| `blob5`-`blob20` | user `blobs[0..15]` | Max 16 extra blobs, <=16KB each |
| `double1`-`double20` | user `doubles[0..19]` | Up to 20 doubles |

## Error responses

| Status | Body |
|--------|------|
| 400 | `{ "error": "..." }` — invalid JSON, bad name, empty points, etc. |
| 401 | `{ "error": "unauthorized" }` |
| 404 | `{ "error": "not found" }` |
| 502 | `{ "error": "CF API ..." }` — upstream query failure |

## Development

```bash
npm run dev      # local dev server (wrangler dev)
npm run deploy   # deploy to Cloudflare
npm run tail     # stream live logs
```

## License

MIT
