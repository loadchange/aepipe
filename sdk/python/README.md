# aepipe-sdk-python

Python SDK for [aepipe](https://github.com/loadchange/aepipe), a multi-tenant log ingestion and query service built on Cloudflare Workers Analytics Engine.

Zero external dependencies. Python 3.10+.

## Installation

```bash
pip install aepipe-sdk
```

## Quick Start

```python
from aepipe import Aepipe

client = Aepipe(
    base_url="https://aepipe.yourdomain.com",
    token="your-admin-token",
)
```

## API Reference

### `ingest(project, logstore, points) -> IngestResult`

Write structured event points to Analytics Engine.

| Parameter  | Type               | Description                                     |
|------------|--------------------|-------------------------------------------------|
| `project`  | `str`              | Project name (`^[a-zA-Z0-9_-]{1,64}$`)          |
| `logstore` | `str`              | Logstore name (`^[a-zA-Z0-9_-]{1,64}$`)         |
| `points`   | `list[DataPoint]`  | Event points (max 250 per call)                  |

```python
from aepipe import DataPoint

result = client.ingest("myapp", "backend", [
    DataPoint(event="user_login"),
    DataPoint(event="api_error", level="error", blobs=["GET /api"], doubles=[1.23]),
    # With D1 payload — large data stored separately, linked via UUID
    DataPoint(
        event="unhandled_exception",
        level="error",
        payload={"stack": "Error: ...\n  at ...", "request": {"url": "/api/users"}},
        ttl=604800,  # 7 days
    ),
])
print(result.ok)       # True
print(result.written)  # 3
```

### `log(project, logstore, logs) -> LogResult`

Write raw log entries via Workers Observability.

| Parameter  | Type              | Description                                     |
|------------|-------------------|-------------------------------------------------|
| `project`  | `str`             | Project name                                     |
| `logstore` | `str`             | Logstore name                                    |
| `logs`     | `list[LogEntry]`  | Log entries (max 250 per call)                   |

```python
from aepipe import LogEntry

result = client.log("myapp", "backend", [
    LogEntry(message="server started"),
    LogEntry(message="connection timeout", level="error", extra={"ip": "1.2.3.4"}),
])
print(result.written)  # 2
```

### `query(project, logstore, sql) -> QueryResult`

Run a SQL query against Analytics Engine. Tenant filters are injected automatically.

| Parameter  | Type   | Description                              |
|------------|--------|------------------------------------------|
| `project`  | `str`  | Project name                              |
| `logstore` | `str`  | Logstore name                             |
| `sql`      | `str`  | SQL query (Analytics Engine dialect)      |

```python
result = client.query("myapp", "backend", "SELECT count() as cnt FROM aepipe")
print(result.data)
```

### `rawlog(project, logstore, *, limit=50, start=None, end=None) -> RawLogResult`

Query raw Worker logs via Cloudflare Telemetry API.

| Parameter  | Type           | Default | Description                    |
|------------|----------------|---------|--------------------------------|
| `project`  | `str`          |         | Project name                    |
| `logstore` | `str`          |         | Logstore name                   |
| `limit`    | `int`          | `50`    | Max results (server caps at 200)|
| `start`    | `str or None`  | `None`  | Start timestamp (ISO 8601)      |
| `end`      | `str or None`  | `None`  | End timestamp (ISO 8601)        |

```python
result = client.rawlog("myapp", "backend", limit=100, start="2025-01-01T00:00:00Z")
for entry in result.logs:
    print(f"[{entry.level}] {entry.timestamp} {entry.data}")
print(f"total: {result.count}")
```

### `detail(project, logstore, ref_ids) -> DetailResult`

Fetch extended payloads from D1 by ref_id. Requires D1 binding on the server.

| Parameter  | Type         | Description                             |
|------------|--------------|----------------------------------------|
| `project`  | `str`        | Project name                            |
| `logstore` | `str`        | Logstore name                           |
| `ref_ids`  | `list[str]`  | UUID references from AE blob5 (max 100) |

```python
# 1. Query AE to get ref_ids
ae_result = client.query("myapp", "backend",
    "SELECT blob5 as ref_id, blob3 as event FROM aepipe WHERE blob5 != '' LIMIT 10"
)

# 2. Fetch full payloads from D1
ref_ids = [r["ref_id"] for r in ae_result.data.get("data", [])]
details = client.detail("myapp", "backend", ref_ids)
for entry in details.results:
    print(entry.ref_id, entry.payload)  # {"stack": "...", "request": {...}}
```

### `list_projects() -> ListResult`

List all projects that have written data.

```python
result = client.list_projects()
print(result.items)  # ["myapp", "analytics", ...]
```

### `list_logstores(project) -> ListResult`

List all logstores within a project.

```python
result = client.list_logstores("myapp")
print(result.items)  # ["backend", "frontend", ...]
```

## Data Types

### `DataPoint`

| Field     | Type              | Default  | AE Mapping     | Description                     |
|-----------|-------------------|----------|-----------------|---------------------------------|
| `event`   | `str`             | required | blob3           | Event name (non-empty)          |
| `level`   | `str`             | `"info"` | blob4           | Log level                       |
| `blobs`   | `list[str]`       | `[]`     | blob6 – blob20  | String metadata for grouping/filtering (max **15** items) |
| `doubles` | `list[float]`     | `[]`     | double1 – double20 | Numeric metrics for aggregation (max **20** items) |
| `payload` | `dict[str, Any]`  | `None`   | D1 (via blob5 ref_id) | Extended data stored in D1. Requires D1 binding on server |
| `ttl`     | `int`             | 7776000  |                 | Payload TTL in seconds (default: 90 days) |

> **blobs vs doubles — how to choose?**
>
> - **blobs** (string): Used for **grouping** (`GROUP BY`) and **filtering** (`WHERE`). Not aggregatable. Examples: URL path, user ID, region, error message.
> - **doubles** (number): 64-bit IEEE 754 floats. Can be **aggregated** with `SUM`, `AVG`, `QUANTILE`, `MIN`, `MAX`. Examples: response time, request size, error count.

## Cloudflare Analytics Engine Limits

These are hard limits enforced by Cloudflare. Exceeding blob size limits causes **silent data truncation** — the write succeeds but data is lost, making it impossible to observe anomalies. The SDK validates these limits client-side and raises `ValidationError` before sending.

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

| Field     | Type              | Default  | Description                     |
|-----------|-------------------|----------|---------------------------------|
| `message` | `str`             | required | Log message (non-empty)         |
| `level`   | `str`             | `"info"` | Log level                       |
| `extra`   | `dict[str, Any]`  | `{}`     | Additional fields               |

### Result Types

| Type            | Fields                        |
|-----------------|-------------------------------|
| `IngestResult`  | `ok: bool`, `written: int`    |
| `LogResult`     | `ok: bool`, `written: int`    |
| `QueryResult`   | `data: Any`                   |
| `DetailResult`  | `results: list[DetailEntry]`  |
| `DetailEntry`   | `ref_id: str`, `payload: dict`, `created_at: int`, `expires_at: int` |
| `RawLogResult`  | `logs: list[RawLogEntry]`, `count: int` |
| `RawLogEntry`   | `timestamp: str`, `level: str`, `data: Any` |
| `ListResult`    | `items: list[str]`            |

## Validation

All methods validate inputs before making network requests:

- **Name format**: project and logstore names must match `^[a-zA-Z0-9_-]{1,64}$`.
- **Batch size**: `ingest()` and `log()` accept at most 250 items per call.

Invalid inputs raise `ValidationError` (subclass of `ValueError`).

## Error Handling

```python
from aepipe import AepipeError, ValidationError

try:
    client.ingest("myapp", "backend", points)
except ValidationError as e:
    # Client-side validation failed
    print(f"invalid input: {e}")
except AepipeError as e:
    # Server returned an error
    print(f"API error {e.status}: {e.message}")
```

| Error Class      | Parent     | Fields               | When                       |
|------------------|------------|----------------------|----------------------------|
| `AepipeError`    | `Exception`| `status`, `message`  | Server returns non-2xx     |
| `ValidationError`| `ValueError`| `message`           | Invalid client input       |

## License

MIT
