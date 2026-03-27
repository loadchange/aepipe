from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataPoint:
    """A structured event point to write to Analytics Engine."""

    event: str
    level: str = "info"
    blobs: list[str] = field(default_factory=list)
    doubles: list[float] = field(default_factory=list)


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
class ListResult:
    items: list[str]
