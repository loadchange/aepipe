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
]);
console.log(result.ok);       // true
console.log(result.written);  // 2
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

| Field     | Type       | Default  | Description                     |
|-----------|------------|----------|---------------------------------|
| `event`   | `string`   | required | Event name (non-empty)          |
| `level`   | `string`   | `"info"` | Log level                       |
| `blobs`   | `string[]` |          | String metadata (max 16 extra)  |
| `doubles` | `number[]` |          | Numeric metrics (max 20)        |

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
