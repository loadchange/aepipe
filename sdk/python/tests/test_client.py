"""Tests for the Python aepipe SDK."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from aepipe import Aepipe, AepipeError, DataPoint, LogEntry, ValidationError

BASE = "https://aepipe.example.com"
TOKEN = "test-token"


def _mock_response(status: int = 200, body: dict | None = None):
    """Build a fake urllib HTTPResponse."""
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    payload = json.dumps(body if body is not None else {}).encode()
    resp.read.return_value = payload
    return resp


def _capture_request(mock_urlopen):
    """Extract the Request object passed to urlopen."""
    return mock_urlopen.call_args[0][0]


# ─── ingest ───────────────────────────────────────────────────────────

class TestIngest:
    @patch("aepipe.client.urlopen")
    def test_ingest_single_point(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 1})
        client = Aepipe(BASE, TOKEN)
        result = client.ingest("proj", "store", [DataPoint(event="click")])
        assert result.ok is True
        assert result.written == 1

        req = _capture_request(mock_urlopen)
        assert req.method == "POST"
        assert req.full_url == f"{BASE}/v1/proj/store/ingest"
        assert req.get_header("Authorization") == f"Bearer {TOKEN}"
        sent = json.loads(req.data)
        assert len(sent["points"]) == 1
        assert sent["points"][0]["event"] == "click"

    @patch("aepipe.client.urlopen")
    def test_ingest_multiple_points(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 3})
        client = Aepipe(BASE, TOKEN)
        points = [
            DataPoint(event="a", level="error", blobs=["x"], doubles=[1.0]),
            DataPoint(event="b"),
            DataPoint(event="c"),
        ]
        result = client.ingest("p", "s", points)
        assert result.written == 3

        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["points"][0]["level"] == "error"
        assert sent["points"][0]["blobs"] == ["x"]
        assert sent["points"][0]["doubles"] == [1.0]

    @patch("aepipe.client.urlopen")
    def test_ingest_default_level(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 1})
        client = Aepipe(BASE, TOKEN)
        client.ingest("p", "s", [DataPoint(event="e")])
        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["points"][0]["level"] == "info"


# ─── log ──────────────────────────────────────────────────────────────

class TestLog:
    @patch("aepipe.client.urlopen")
    def test_log_entries(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 2})
        client = Aepipe(BASE, TOKEN)
        result = client.log("p", "s", [
            LogEntry(message="hello"),
            LogEntry(message="world", level="error"),
        ])
        assert result.ok is True
        assert result.written == 2

        sent = json.loads(_capture_request(mock_urlopen).data)
        assert len(sent["logs"]) == 2
        assert sent["logs"][0]["message"] == "hello"
        assert sent["logs"][1]["level"] == "error"

    @patch("aepipe.client.urlopen")
    def test_log_with_extra_fields(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 1})
        client = Aepipe(BASE, TOKEN)
        client.log("p", "s", [LogEntry(message="m", extra={"user": "alice"})])
        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["logs"][0]["user"] == "alice"


# ─── query ────────────────────────────────────────────────────────────

class TestQuery:
    @patch("aepipe.client.urlopen")
    def test_query(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"data": [{"cnt": 42}]})
        client = Aepipe(BASE, TOKEN)
        result = client.query("p", "s", "SELECT count() FROM aepipe")
        assert result.data["data"] == [{"cnt": 42}]

        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["sql"] == "SELECT count() FROM aepipe"

    @patch("aepipe.client.urlopen")
    def test_query_empty_result(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"data": []})
        client = Aepipe(BASE, TOKEN)
        result = client.query("p", "s", "SELECT 1")
        assert result.data == {"data": []}


# ─── rawlog ───────────────────────────────────────────────────────────

class TestRawLog:
    @patch("aepipe.client.urlopen")
    def test_rawlog_defaults(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={
            "logs": [{"timestamp": "2025-01-01T00:00:00Z", "level": "info", "data": "msg"}],
            "count": 1,
        })
        client = Aepipe(BASE, TOKEN)
        result = client.rawlog("p", "s")
        assert result.count == 1
        assert result.logs[0].timestamp == "2025-01-01T00:00:00Z"
        assert result.logs[0].level == "info"

        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["limit"] == 50
        assert "start" not in sent
        assert "end" not in sent

    @patch("aepipe.client.urlopen")
    def test_rawlog_with_options(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"logs": [], "count": 0})
        client = Aepipe(BASE, TOKEN)
        client.rawlog("p", "s", limit=100, start="2025-01-01", end="2025-01-02")
        sent = json.loads(_capture_request(mock_urlopen).data)
        assert sent["limit"] == 100
        assert sent["start"] == "2025-01-01"
        assert sent["end"] == "2025-01-02"

    @patch("aepipe.client.urlopen")
    def test_rawlog_empty(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={})
        client = Aepipe(BASE, TOKEN)
        result = client.rawlog("p", "s")
        assert result.logs == []
        assert result.count == 0


# ─── list ─────────────────────────────────────────────────────────────

class TestList:
    @patch("aepipe.client.urlopen")
    def test_list_projects(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"projects": ["alpha", "beta"]})
        client = Aepipe(BASE, TOKEN)
        result = client.list_projects()
        assert result.items == ["alpha", "beta"]

        req = _capture_request(mock_urlopen)
        assert req.method == "GET"
        assert req.full_url == f"{BASE}/v1/projects"

    @patch("aepipe.client.urlopen")
    def test_list_projects_empty(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={})
        result = Aepipe(BASE, TOKEN).list_projects()
        assert result.items == []

    @patch("aepipe.client.urlopen")
    def test_list_logstores(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"logstores": ["access", "error"]})
        client = Aepipe(BASE, TOKEN)
        result = client.list_logstores("alpha")
        assert result.items == ["access", "error"]

        req = _capture_request(mock_urlopen)
        assert req.full_url == f"{BASE}/v1/alpha/logstores"


# ─── error handling ───────────────────────────────────────────────────

class TestErrors:
    @patch("aepipe.client.urlopen")
    def test_http_error_json(self, mock_urlopen):
        from urllib.error import HTTPError
        err_body = json.dumps({"error": "bad request"}).encode()
        mock_urlopen.side_effect = HTTPError(
            f"{BASE}/v1/p/s/ingest", 400, "Bad Request", {}, BytesIO(err_body)
        )
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(AepipeError) as exc_info:
            client.ingest("p", "s", [DataPoint(event="x")])
        assert exc_info.value.status == 400
        assert "bad request" in exc_info.value.message

    @patch("aepipe.client.urlopen")
    def test_http_error_non_json(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            f"{BASE}/v1/p/s/ingest", 502, "Bad Gateway", {}, BytesIO(b"gateway timeout")
        )
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(AepipeError) as exc_info:
            client.ingest("p", "s", [DataPoint(event="x")])
        assert exc_info.value.status == 502
        assert "gateway timeout" in exc_info.value.message


# ─── base URL handling ────────────────────────────────────────────────

class TestBaseUrl:
    @patch("aepipe.client.urlopen")
    def test_trailing_slash_stripped(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"projects": []})
        client = Aepipe(BASE + "///", TOKEN)
        client.list_projects()
        req = _capture_request(mock_urlopen)
        assert req.full_url == f"{BASE}/v1/projects"

    @patch("aepipe.client.urlopen")
    def test_no_trailing_slash(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"projects": []})
        client = Aepipe(BASE, TOKEN)
        client.list_projects()
        req = _capture_request(mock_urlopen)
        assert "//v1" not in req.full_url


# ─── validation ──────────────────────────────────────────────────────

class TestValidation:
    def test_invalid_project_name(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError, match="invalid project"):
            client.ingest("bad name!", "s", [DataPoint(event="e")])

    def test_invalid_logstore_name(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError, match="invalid logstore"):
            client.ingest("p", "", [DataPoint(event="e")])

    def test_empty_name(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError):
            client.query("", "s", "SELECT 1")

    def test_name_too_long(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError):
            client.query("a" * 65, "s", "SELECT 1")

    def test_ingest_batch_limit(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError, match="max 250"):
            client.ingest("p", "s", [DataPoint(event="e")] * 251)

    def test_log_batch_limit(self):
        client = Aepipe(BASE, TOKEN)
        with pytest.raises(ValidationError, match="max 250"):
            client.log("p", "s", [LogEntry(message="m")] * 251)

    @patch("aepipe.client.urlopen")
    def test_valid_name_with_dashes_and_underscores(self, mock_urlopen):
        """Names with hyphens and underscores should pass validation."""
        mock_urlopen.return_value = _mock_response(body={"data": []})
        client = Aepipe(BASE, TOKEN)
        result = client.query("my-project_v1", "log_store-2", "SELECT 1")
        assert result.data == {"data": []}

    @patch("aepipe.client.urlopen")
    def test_empty_blobs_doubles_omitted(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(body={"ok": True, "written": 1})
        client = Aepipe(BASE, TOKEN)
        client.ingest("p", "s", [DataPoint(event="e")])
        sent = json.loads(_capture_request(mock_urlopen).data)
        assert "blobs" not in sent["points"][0]
        assert "doubles" not in sent["points"][0]
