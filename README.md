# aepipe

A lightweight Cloudflare Worker that ingests structured events over HTTP and writes them to [Workers Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/).

Send JSON from any backend, query with SQL — no log aggregation stack required.

## How it works

```
Your App ──POST JSON──▶ aepipe (CF Worker) ──writeDataPoint()──▶ Analytics Engine
                                                                        │
                                                                   SQL API ◀── You
```

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
dataset = "your-dataset-name"  # change this
```

### 3. Set the ingest token

```bash
npx wrangler secret put INGEST_TOKEN
```

This shared secret protects the endpoint from unauthorized writes.

### 4. Deploy

```bash
npm run deploy
```

## Usage

### Write data points

```bash
curl -X POST https://aepipe.<your-subdomain>.workers.dev \
  -H "Authorization: Bearer <INGEST_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "event": "order_placed",
        "level": "info",
        "index": "session-abc",
        "blobs": ["user-42", "us-east"],
        "doubles": [99.95, 3]
      }
    ]
  }'
```

**Response:**

```json
{ "ok": true, "written": 1 }
```

### Query with SQL

Create an [API token](https://dash.cloudflare.com/profile/api-tokens) with **Account Analytics Read** permission, then:

```bash
curl "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql" \
  -H "Authorization: Bearer <CF_API_TOKEN>" \
  -d "SELECT timestamp, blob1 AS event, blob2 AS level, double1
      FROM your-dataset-name
      WHERE blob2 = 'error'
      AND timestamp >= NOW() - INTERVAL '1' HOUR
      ORDER BY timestamp DESC
      LIMIT 50"
```

## Data point schema

| Field | Type | Required | Maps to |
|-------|------|----------|---------|
| `event` | string | **yes** | `blob1` |
| `level` | string | no (default `"info"`) | `blob2` |
| `index` | string | no | `index1` (sampling key) |
| `blobs` | string[] | no | `blob3`, `blob4`, ... |
| `doubles` | number[] | no | `double1`, `double2`, ... |

**Analytics Engine limits:** up to 20 blobs (each ≤ 16 KB), 20 doubles, 1 index (≤ 96 bytes).

## API reference

### `POST /`

Writes data points to Analytics Engine.

**Headers:**
- `Authorization: Bearer <INGEST_TOKEN>` (required)
- `Content-Type: application/json`

**Body:**

```json
{
  "points": [
    {
      "event": "string (required)",
      "level": "string",
      "index": "string",
      "blobs": ["string"],
      "doubles": [0.0]
    }
  ]
}
```

**Constraints:**
- `points` must be a non-empty array
- Max 250 points per request
- Points with missing or empty `event` are silently skipped

**Responses:**

| Status | Body |
|--------|------|
| 200 | `{ "ok": true, "written": N }` |
| 400 | `{ "error": "invalid json" }` or `{ "error": "points must be a non-empty array" }` or `{ "error": "max 250 points per request" }` |
| 401 | `{ "error": "unauthorized" }` |
| 405 | `{ "error": "method not allowed" }` |

## Development

```bash
npm run dev      # local dev server (wrangler dev)
npm run deploy   # deploy to Cloudflare
npm run tail     # stream live logs
```

## License

MIT
