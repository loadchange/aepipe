from __future__ import annotations

import json
import re
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .types import (
    DataPoint,
    DetailEntry,
    DetailResult,
    IngestResult,
    ListResult,
    LogEntry,
    LogResult,
    QueryResult,
    RawLogEntry,
    RawLogResult,
)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_MAX_BATCH = 250
# Cloudflare Analytics Engine limit: total blob size per data point is 16 KB.
# See: https://developers.cloudflare.com/analytics/analytics-engine/limits/
_MAX_BLOB_BYTES = 16 * 1024
# Cloudflare Analytics Engine limit: index must not exceed 96 bytes.
# Index is formatted as "{project}/{logstore}".
_MAX_INDEX_BYTES = 96


class AepipeError(Exception):
    """Raised when the aepipe API returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"aepipe error {status}: {message}")


class ValidationError(ValueError):
    """Raised when client-side validation fails."""


def _validate_name(name: str, label: str) -> None:
    if not _NAME_RE.match(name):
        raise ValidationError(f"invalid {label}: {name!r}")


def _validate_index_size(project: str, logstore: str) -> None:
    """Index is ``{project}/{logstore}`` — Cloudflare caps it at 96 bytes."""
    index = f"{project}/{logstore}"
    size = len(index.encode("utf-8"))
    if size > _MAX_INDEX_BYTES:
        raise ValidationError(
            f'index "{index}" is {size} bytes, exceeds the 96-byte '
            f"Cloudflare Analytics Engine limit. Use shorter names."
        )


def _validate_blob_size(
    project: str, logstore: str, p: DataPoint, idx: int
) -> None:
    """All blobs in a data point (including system blobs) must total <= 16 KB."""
    ref_id_est = "00000000-0000-0000-0000-000000000000" if p.payload else ""
    all_blobs = [project, logstore, p.event, p.level, ref_id_est, *p.blobs]
    total = sum(len(b.encode("utf-8")) for b in all_blobs)
    if total > _MAX_BLOB_BYTES:
        raise ValidationError(
            f"points[{idx}]: total blob size {total} bytes exceeds the 16 KB "
            f"({_MAX_BLOB_BYTES} bytes) Cloudflare Analytics Engine limit. "
            f"Reduce blob content to prevent silent data truncation."
        )


def _serialize_point(p: DataPoint) -> dict[str, Any]:
    d: dict[str, Any] = {"event": p.event, "level": p.level}
    if p.blobs:
        d["blobs"] = p.blobs
    if p.doubles:
        d["doubles"] = p.doubles
    if p.payload is not None:
        d["payload"] = p.payload
    if p.ttl is not None:
        d["ttl"] = p.ttl
    return d


class Aepipe:
    """Python SDK for the aepipe analytics engine."""

    def __init__(self, base_url: str, token: str):
        """
        Args:
            base_url: The aepipe worker URL, e.g. ``https://aepipe.example.com``.
            token: The ``ADMIN_TOKEN`` secret.
        """
        self._base = base_url.rstrip("/")
        self._token = token

    # --- ingest ---

    def ingest(
        self,
        project: str,
        logstore: str,
        points: list[DataPoint],
    ) -> IngestResult:
        """Write structured event points (max 250 per call)."""
        _validate_name(project, "project")
        _validate_name(logstore, "logstore")
        _validate_index_size(project, logstore)
        if len(points) > _MAX_BATCH:
            raise ValidationError(f"max {_MAX_BATCH} points per request, got {len(points)}")
        for i, p in enumerate(points):
            if len(p.blobs) > 15:
                raise ValidationError(
                    f"points[{i}]: max 15 user blobs (blob6-blob20), got {len(p.blobs)}"
                )
            if len(p.doubles) > 20:
                raise ValidationError(
                    f"points[{i}]: max 20 doubles, got {len(p.doubles)}"
                )
            _validate_blob_size(project, logstore, p, i)
        body = {"points": [_serialize_point(p) for p in points]}
        resp = self._post(f"/v1/{project}/{logstore}/ingest", body)
        return IngestResult(ok=resp["ok"], written=resp["written"])

    # --- log ---

    def log(
        self,
        project: str,
        logstore: str,
        logs: list[LogEntry],
    ) -> LogResult:
        """Write raw log entries (max 250 per call)."""
        _validate_name(project, "project")
        _validate_name(logstore, "logstore")
        if len(logs) > _MAX_BATCH:
            raise ValidationError(f"max {_MAX_BATCH} logs per request, got {len(logs)}")
        body = {
            "logs": [
                {"message": e.message, "level": e.level, **e.extra}
                for e in logs
            ]
        }
        resp = self._post(f"/v1/{project}/{logstore}/log", body)
        return LogResult(ok=resp["ok"], written=resp["written"])

    # --- query ---

    def query(
        self,
        project: str,
        logstore: str,
        sql: str,
    ) -> QueryResult:
        """Run a SQL query against the Analytics Engine."""
        _validate_name(project, "project")
        _validate_name(logstore, "logstore")
        resp = self._post(f"/v1/{project}/{logstore}/query", {"sql": sql})
        return QueryResult(data=resp)

    # --- rawlog ---

    def rawlog(
        self,
        project: str,
        logstore: str,
        *,
        limit: int = 50,
        start: str | None = None,
        end: str | None = None,
    ) -> RawLogResult:
        """Query raw Worker logs."""
        _validate_name(project, "project")
        _validate_name(logstore, "logstore")
        body: dict[str, Any] = {"limit": limit}
        if start is not None:
            body["start"] = start
        if end is not None:
            body["end"] = end
        resp = self._post(f"/v1/{project}/{logstore}/rawlog", body)
        entries = [
            RawLogEntry(
                timestamp=e["timestamp"],
                level=e["level"],
                data=e["data"],
            )
            for e in resp.get("logs", [])
        ]
        return RawLogResult(logs=entries, count=resp.get("count", len(entries)))

    # --- detail ---

    def detail(
        self,
        project: str,
        logstore: str,
        ref_ids: list[str],
    ) -> DetailResult:
        """Fetch D1 payloads by ref_id (max 100 per call)."""
        _validate_name(project, "project")
        _validate_name(logstore, "logstore")
        if not ref_ids:
            return DetailResult(results=[])
        if len(ref_ids) > 100:
            raise ValidationError(f"max 100 ref_ids per request, got {len(ref_ids)}")
        resp = self._post(f"/v1/{project}/{logstore}/detail", {"ref_ids": ref_ids})
        entries = [
            DetailEntry(
                ref_id=r["ref_id"],
                payload=r["payload"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
            for r in resp.get("results", [])
        ]
        return DetailResult(results=entries)

    # --- list ---

    def list_projects(self) -> ListResult:
        """List all projects."""
        resp = self._get("/v1/projects")
        return ListResult(items=resp.get("projects", []))

    def list_logstores(self, project: str) -> ListResult:
        """List all logstores in a project."""
        _validate_name(project, "project")
        resp = self._get(f"/v1/{project}/logstores")
        return ListResult(items=resp.get("logstores", []))

    # --- internal ---

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "aepipe-sdk-python/0.1.0",
        }

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self._base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            text = e.read().decode()
            try:
                msg = json.loads(text).get("error", text)
            except json.JSONDecodeError:
                msg = text
            raise AepipeError(e.code, msg) from e

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post(self, path: str, body: Any) -> Any:
        return self._request("POST", path, body)
