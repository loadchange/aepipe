from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataPoint:
    """A structured event point to write to Analytics Engine.

    Field mapping & limits (Cloudflare Analytics Engine):

    - ``event``  -> blob3 (required, non-empty string)
    - ``level``  -> blob4 (defaults to "info")
    - ``blobs``  -> blob6–blob20, max **15** items.
      Used for grouping / filtering only (NOT aggregatable).
      (blob5 is reserved for ref_id linking to D1 payloads)
    - ``doubles`` -> double1–double20, max **20** items.
      64-bit IEEE 754 floats. Can be aggregated with SUM / AVG / QUANTILE / MIN / MAX.

    **Storage limits per data point:**

    - All blobs (including system blobs: project, logstore, event, level) share a
      **16 KB total size limit**. Exceeding this causes **silent truncation** by
      Cloudflare — data is lost without any error.
    - Keep individual blob values short to stay within the 16 KB budget.
    - Data is retained for **3 months**.

    See: https://developers.cloudflare.com/analytics/analytics-engine/limits/
    """

    event: str
    level: str = "info"
    blobs: list[str] = field(default_factory=list)
    doubles: list[float] = field(default_factory=list)
    payload: dict[str, Any] | None = None
    """Extended JSON data stored in D1. Requires D1 binding on the server.
    If D1 is not configured, silently ignored."""
    ttl: int | None = None
    """Payload TTL in seconds. Default: 90 days (matches AE retention).
    Only meaningful when ``payload`` is set."""


@dataclass
class LogEntry:
    """A raw log entry to write via Workers Logs."""

    message: str
    level: str = "info"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    ok: bool
    written: int


@dataclass
class LogResult:
    ok: bool
    written: int


@dataclass
class RawLogEntry:
    timestamp: str
    level: str
    data: Any


@dataclass
class RawLogResult:
    logs: list[RawLogEntry]
    count: int


@dataclass
class QueryResult:
    data: Any


@dataclass
class DetailEntry:
    ref_id: str
    payload: dict[str, Any]
    created_at: int
    expires_at: int


@dataclass
class DetailResult:
    results: list[DetailEntry]


@dataclass
class ListResult:
    items: list[str]
