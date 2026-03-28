# aepipe-sdk-js

JavaScript/TypeScript SDK for [aepipe](https://github.com/loadchange/aepipe), a multi-tenant log ingestion and query service built on Cloudflare Workers Analytics Engine.

Zero external dependencies. Works in **Node.js 18+** and the **browser**.

## Installation

```bash
npm install aepipe-sdk
```

## Quick Start

```ts
import { Aepipe } from "aepipe-sdk";

const client = new Aepipe({
  baseUrl: "https://aepipe.yourdomain.com",
  token: "your-admin-token",
});
```

## API Reference

### `ingest(project, logstore, points): Promise<IngestResult>`

Write structured event points to Analytics Engine.

| Parameter  | Type          | Description                                     |
|------------|---------------|-------------------------------------------------|
| `project`  | `string`      | Project name (`^[a-zA-Z0-9_-]{1,64}$`)          |
| `logstore` | `string`      | Logstore name (`^[a-zA-Z0-9_-]{1,64}$`)         |
| `points`   | `DataPoint[]` | Event points (max 250 per call)                  |

```ts
const result = await client.ingest("myapp", "backend", [
  { event: "user_login" },
  { event: "api_error", level: "error", blobs: ["GET /api"], doubles: [1.23] },
  // With D1 payload — large data stored separately, linked via UUID
  {
    event: "unhandled_exception",
    level: "error",
    payload: { stack: "Error: ...\n  at ...", request: { url: "/api/users", method: "POST" } },
    ttl: 604800, // 7 days
  },
]);
console.log(result.ok);       // true
console.log(result.written);  // 3
```

### `log(project, logstore, logs): Promise<LogResult>`

Write raw log entries via Workers Observability. Extra properties are spread into each entry automatically.

| Parameter  | Type          | Description                                     |
|------------|---------------|-------------------------------------------------|
| `project`  | `string`      | Project name                                     |
| `logstore` | `string`      | Logstore name                                    |
| `logs`     | `LogEntry[]`  | Log entries (max 250 per call)                   |

```ts
const result = await client.log("myapp", "backend", [
  { message: "server started" },
  { message: "connection timeout", level: "error", ip: "1.2.3.4" },
]);
console.log(result.written);  // 2
```

### `query(project, logstore, sql): Promise<QueryResult>`

Run a SQL query against Analytics Engine. Tenant filters are injected automatically.

| Parameter  | Type     | Description                              |
|------------|----------|------------------------------------------|
| `project`  | `string` | Project name                              |
| `logstore` | `string` | Logstore name                             |
| `sql`      | `string` | SQL query (Analytics Engine dialect)      |

```ts
const result = await client.query("myapp", "backend", "SELECT count() as cnt FROM aepipe");
console.log(result);
```

### `rawlog(project, logstore, opts?): Promise<RawLogResult>`

Query raw Worker logs via Cloudflare Telemetry API.

| Parameter  | Type     | Default | Description                     |
|------------|----------|---------|---------------------------------|
| `project`  | `string` |         | Project name                     |
| `logstore` | `string` |         | Logstore name                    |
| `opts.limit`  | `number` | `50` | Max results (server caps at 200) |
| `opts.start`  | `string` |       | Start timestamp (ISO 8601)       |
| `opts.end`    | `string` |       | End timestamp (ISO 8601)         |

```ts
const result = await client.rawlog("myapp", "backend", {
  limit: 100,
  start: "2025-01-01T00:00:00Z",
});
for (const entry of result.logs) {
  console.log(`[${entry.level}] ${entry.timestamp} ${entry.data}`);
}
console.log(`total: ${result.count}`);
```

### `detail(project, logstore, refIds): Promise<DetailResult>`

Fetch extended payloads from D1 by ref_id. Requires D1 binding on the server.

| Parameter  | Type       | Description                             |
|------------|------------|-----------------------------------------|
| `project`  | `string`   | Project name                             |
| `logstore` | `string`   | Logstore name                            |
| `refIds`   | `string[]` | UUID references from AE blob5 (max 100)  |

```ts
// 1. Query AE to get ref_ids
const aeResult = await client.query("myapp", "backend",
  "SELECT blob5 as ref_id, blob3 as event FROM aepipe WHERE blob5 != '' LIMIT 10"
);

// 2. Fetch full payloads from D1
const refIds = aeResult.data.map((r: any) => r.ref_id);
const details = await client.detail("myapp", "backend", refIds);
for (const entry of details.results) {
  console.log(entry.ref_id, entry.payload);  // { stack: "...", request: { ... } }
}
```

### `listProjects(): Promise<ListResult>`

List all projects that have written data.

```ts
const result = await client.listProjects();
console.log(result.items);  // ["myapp", "analytics", ...]
```

### `listLogstores(project): Promise<ListResult>`

List all logstores within a project.

```ts
const result = await client.listLogstores("myapp");
console.log(result.items);  // ["backend", "frontend", ...]
```

## Data Types

### `DataPoint`

| Field     | Type                      | Default  | AE Mapping     | Description                     |
|-----------|---------------------------|----------|-----------------|---------------------------------|
| `event`   | `string`                  | required | blob3           | Event name (non-empty)          |
| `level`   | `string`                  | `"info"` | blob4           | Log level                       |
| `blobs`   | `string[]`                | `[]`     | blob6 – blob20  | String metadata for grouping/filtering (max **15** items) |
| `doubles` | `number[]`                | `[]`     | double1 – double20 | Numeric metrics for aggregation (max **20** items) |
| `payload` | `Record<string, unknown>` |          | D1 (via blob5 ref_id) | Extended data stored in D1. Requires D1 binding on server |
| `ttl`     | `number`                  | 7776000  |                 | Payload TTL in seconds (default: 90 days) |

> **blobs vs doubles — how to choose?**
>
> - **blobs** (string): Used for **grouping** (`GROUP BY`) and **filtering** (`WHERE`). Not aggregatable. Examples: URL path, user ID, region, error message.
> - **doubles** (number): 64-bit IEEE 754 floats. Can be **aggregated** with `SUM`, `AVG`, `QUANTILE`, `MIN`, `MAX`. Examples: response time, request size, error count.

## Cloudflare Analytics Engine Limits

These are hard limits enforced by Cloudflare. Exceeding blob size limits causes **silent data truncation** — the write succeeds but data is lost, making it impossible to observe anomalies. The SDK validates these limits client-side and throws `ValidationError` before sending.

| Limit | Value | Notes |
|-------|-------|-------|
| Blobs per data point | 20 total | 5 used by system (project, logstore, event, level, ref_id), **15 available to user** |
| Doubles per data point | 20 | All available to user |
| **Total blob size per data point** | **16 KB** | Sum of all blob byte lengths (UTF-8), including system blobs. **Exceeding = silent truncation** |
| Index size | 96 bytes | Index = `{project}/{logstore}`, auto-managed |
| Data points per request | 250 | Per `ingest()` / `log()` call |
| Data retention | **3 months** | Data auto-expires after 3 months |

> **Tip:** If your data is large (e.g., full stack traces, request dumps), use the `payload` field instead of blobs. Payloads are stored in Cloudflare D1 with no 16 KB limit, linked to AE via a UUID in blob5.

See: [Cloudflare Analytics Engine Limits](https://developers.cloudflare.com/analytics/analytics-engine/limits/)

### `LogEntry`

| Field     | Type       | Default  | Description                     |
|-----------|------------|----------|---------------------------------|
| `message` | `string`   | required | Log message (non-empty)         |
| `level`   | `string`   | `"info"` | Log level                       |

Additional properties are spread into the log entry.

### Result Types

| Type            | Fields                              |
|-----------------|-------------------------------------|
| `IngestResult`  | `ok: boolean`, `written: number`    |
| `LogResult`     | `ok: boolean`, `written: number`    |
| `QueryResult`   | Raw response from Analytics Engine  |
| `DetailResult`  | `results: DetailEntry[]`            |
| `DetailEntry`   | `ref_id: string`, `payload: Record<string, unknown>`, `created_at: number`, `expires_at: number` |
| `RawLogResult`  | `logs: RawLogEntry[]`, `count: number` |
| `RawLogEntry`   | `timestamp: string`, `level: string`, `data: unknown` |
| `ListResult`    | `items: string[]`                   |

## Validation

All methods validate inputs before making network requests:

- **Name format**: project and logstore names must match `^[a-zA-Z0-9_-]{1,64}$`.
- **Batch size**: `ingest()` and `log()` accept at most 250 items per call.

Invalid inputs throw `ValidationError`.

## Error Handling

```ts
import { AepipeError, ValidationError } from "aepipe-sdk";

try {
  await client.ingest("myapp", "backend", points);
} catch (e) {
  if (e instanceof ValidationError) {
    // Client-side validation failed
    console.error("invalid input:", e.message);
  } else if (e instanceof AepipeError) {
    // Server returned an error
    console.error(`API error ${e.status}: ${e.message}`);
  }
}
```

| Error Class      | Parent   | Fields               | When                       |
|------------------|----------|----------------------|----------------------------|
| `AepipeError`    | `Error`  | `status`, `message`  | Server returns non-2xx     |
| `ValidationError`| `Error`  | `message`            | Invalid client input       |

## Node.js < 18

Provide a `fetch` polyfill:

```ts
import fetch from "node-fetch";

const client = new Aepipe({
  baseUrl: "https://aepipe.yourdomain.com",
  token: "your-admin-token",
  fetch,
});
```

## Requirements

- Node.js 18+ (or any environment with a global `fetch`)
- TypeScript 5+ (optional, for type checking)

## License

MIT
