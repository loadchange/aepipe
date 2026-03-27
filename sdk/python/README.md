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
])
print(result.ok)       # True
print(result.written)  # 2
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

| Field     | Type            | Default  | Description                     |
|-----------|-----------------|----------|---------------------------------|
| `event`   | `str`           | required | Event name (non-empty)          |
| `level`   | `str`           | `"info"` | Log level                       |
| `blobs`   | `list[str]`     | `[]`     | String metadata (max 16 extra)  |
| `doubles` | `list[float]`   | `[]`     | Numeric metrics (max 20)        |

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
