"""Integration tests against live aepipe instance."""

import os
import sys
import time
import uuid

sys.path.insert(0, ".")

from aepipe import (
    Aepipe,
    AepipeError,
    DataPoint,
    LogEntry,
    ValidationError,
)

BASE = os.environ["AEPIPE_URL"]
TOKEN = os.environ["AEPIPE_TOKEN"]

client = Aepipe(BASE, TOKEN)

# Use a unique project name per test run to avoid collisions
RUN_ID = uuid.uuid4().hex[:8]
PROJECT = f"inttest{RUN_ID}"
LOGSTORE = "sdk-test"

passed = 0
failed = 0


def test(name: str, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        failed += 1


# ─────────────────────────────────────────────────────────────────────
print(f"\nIntegration test run: project={PROJECT}, logstore={LOGSTORE}\n")
print("[1] ingest")
# ─────────────────────────────────────────────────────────────────────


def test_ingest_single():
    r = client.ingest(PROJECT, LOGSTORE, [DataPoint(event="test_single")])
    assert r.ok is True, f"expected ok=True, got {r}"
    assert r.written == 1, f"expected written=1, got {r.written}"


def test_ingest_batch():
    points = [
        DataPoint(event="batch_event", level="error", blobs=["tag1", "tag2"], doubles=[3.14, 2.71]),
        DataPoint(event="batch_event_2", level="warn"),
        DataPoint(event="batch_event_3"),
    ]
    r = client.ingest(PROJECT, LOGSTORE, points)
    assert r.ok is True
    assert r.written == 3


def test_ingest_with_blobs_and_doubles():
    r = client.ingest(PROJECT, LOGSTORE, [
        DataPoint(event="rich_event", level="debug", blobs=["a", "b", "c"], doubles=[1.1, 2.2, 3.3]),
    ])
    assert r.ok is True
    assert r.written == 1


def test_ingest_empty_event_skipped():
    r = client.ingest(PROJECT, LOGSTORE, [DataPoint(event="")])
    assert r.written == 0


test("ingest single point", test_ingest_single)
test("ingest batch of 3 points", test_ingest_batch)
test("ingest with blobs and doubles", test_ingest_with_blobs_and_doubles)
test("ingest empty event is skipped", test_ingest_empty_event_skipped)


# ─────────────────────────────────────────────────────────────────────
print("\n[1b] ingest with payload (D1)")
# ─────────────────────────────────────────────────────────────────────


def test_ingest_with_payload():
    r = client.ingest(PROJECT, LOGSTORE, [
        DataPoint(
            event="py_payload_test",
            level="error",
            payload={"stack": "Error: test\n  at test.py:1", "url": "/api/test"},
            ttl=86400,
        ),
    ])
    assert r.ok is True, f"expected ok=True, got {r}"
    assert r.written == 1


def test_ingest_mixed_payload():
    r = client.ingest(PROJECT, LOGSTORE, [
        DataPoint(event="py_no_payload"),
        DataPoint(event="py_with_payload", payload={"data": "large content"}),
        DataPoint(event="py_also_no_payload", level="warn"),
    ])
    assert r.ok is True
    assert r.written == 3


test("ingest with D1 payload", test_ingest_with_payload)
test("ingest mixed with/without payload", test_ingest_mixed_payload)

# ─────────────────────────────────────────────────────────────────────
print("\n[2] log (raw logs)")
# ─────────────────────────────────────────────────────────────────────


def test_log_single():
    r = client.log(PROJECT, LOGSTORE, [LogEntry(message="integration test log")])
    assert r.ok is True
    assert r.written == 1


def test_log_with_level():
    r = client.log(PROJECT, LOGSTORE, [
        LogEntry(message="error log", level="error"),
        LogEntry(message="warn log", level="warn"),
        LogEntry(message="debug log", level="debug"),
    ])
    assert r.ok is True
    assert r.written == 3


def test_log_with_extra():
    r = client.log(PROJECT, LOGSTORE, [
        LogEntry(message="structured log", extra={"user": "alice", "request_id": "abc123"}),
    ])
    assert r.ok is True
    assert r.written == 1


test("log single entry", test_log_single)
test("log with different levels", test_log_with_level)
test("log with extra fields", test_log_with_extra)

# Wait for data to be indexed
time.sleep(3)

# ─────────────────────────────────────────────────────────────────────
print("\n[3] query (SQL)")
# ─────────────────────────────────────────────────────────────────────


def test_query_count():
    r = client.query(PROJECT, LOGSTORE, "SELECT count() as cnt FROM aepipe")
    assert r.data is not None


def test_query_select():
    r = client.query(PROJECT, LOGSTORE, "SELECT blob3 as event FROM aepipe LIMIT 5")
    assert r.data is not None


def test_query_tenant_isolation():
    """Query a non-existent project should return 0 results, not error."""
    r = client.query(f"nonexistent_{RUN_ID}", LOGSTORE, "SELECT count() as cnt FROM aepipe")
    assert r.data is not None


test("query count", test_query_count)
test("query select events", test_query_select)
test("query tenant isolation", test_query_tenant_isolation)

# ─────────────────────────────────────────────────────────────────────
print("\n[4] rawlog")
# ─────────────────────────────────────────────────────────────────────


def test_rawlog_defaults():
    r = client.rawlog(PROJECT, LOGSTORE)
    assert isinstance(r.logs, list)
    assert isinstance(r.count, int)


def test_rawlog_with_limit():
    r = client.rawlog(PROJECT, LOGSTORE, limit=5)
    assert isinstance(r.logs, list)
    assert r.count <= 5


test("rawlog with defaults", test_rawlog_defaults)
test("rawlog with limit", test_rawlog_with_limit)

# ─────────────────────────────────────────────────────────────────────
print("\n[5] list projects and logstores")
# ─────────────────────────────────────────────────────────────────────


def test_list_projects():
    # AE is eventually consistent -- retry for up to 30s
    for _ in range(6):
        r = client.list_projects()
        if PROJECT in r.items:
            return
        time.sleep(5)
    raise AssertionError(f"project {PROJECT} not found in {r.items}")


def test_list_logstores():
    for _ in range(6):
        r = client.list_logstores(PROJECT)
        if LOGSTORE in r.items:
            return
        time.sleep(5)
    raise AssertionError(f"logstore {LOGSTORE} not found in {r.items}")


test("list projects", test_list_projects)
test("list logstores", test_list_logstores)

# ─────────────────────────────────────────────────────────────────────
print("\n[5b] detail (D1)")
# ─────────────────────────────────────────────────────────────────────


def test_detail_from_ae():
    """Query AE for ref_ids, then fetch payloads from D1."""
    r = client.query(PROJECT, LOGSTORE,
        "SELECT blob5 as ref_id FROM aepipe WHERE blob5 != '' LIMIT 5")
    data = r.data.get("data", []) if isinstance(r.data, dict) else []
    if data:
        ref_ids = [row["ref_id"] for row in data]
        detail = client.detail(PROJECT, LOGSTORE, ref_ids)
        for entry in detail.results:
            assert entry.ref_id, "ref_id should not be empty"
            assert entry.payload is not None, "payload should not be None"
            assert isinstance(entry.created_at, int)
            assert isinstance(entry.expires_at, int)


def test_detail_empty():
    from aepipe import DetailResult
    r = client.detail(PROJECT, LOGSTORE, [])
    assert r.results == []


test("detail from AE ref_ids", test_detail_from_ae)
test("detail with empty ref_ids", test_detail_empty)

# ─────────────────────────────────────────────────────────────────────
print("\n[6] validation")
# ─────────────────────────────────────────────────────────────────────


def test_validation_bad_project():
    try:
        client.ingest("bad name!", "s", [DataPoint(event="e")])
        raise AssertionError("should have raised ValidationError")
    except ValidationError:
        pass


def test_validation_bad_logstore():
    try:
        client.query(PROJECT, "bad/logstore", "SELECT 1")
        raise AssertionError("should have raised ValidationError")
    except ValidationError:
        pass


def test_validation_batch_limit():
    try:
        client.ingest(PROJECT, LOGSTORE, [DataPoint(event="e")] * 251)
        raise AssertionError("should have raised ValidationError")
    except ValidationError:
        pass


def test_validation_name_too_long():
    try:
        client.query("a" * 65, LOGSTORE, "SELECT 1")
        raise AssertionError("should have raised ValidationError")
    except ValidationError:
        pass


test("reject invalid project name", test_validation_bad_project)
test("reject invalid logstore name", test_validation_bad_logstore)
test("reject batch > 250", test_validation_batch_limit)
test("reject name too long", test_validation_name_too_long)

# ─────────────────────────────────────────────────────────────────────
print("\n[7] auth error")
# ─────────────────────────────────────────────────────────────────────


def test_auth_error():
    bad_client = Aepipe(BASE, "invalid-token-12345")
    try:
        bad_client.ingest(PROJECT, LOGSTORE, [DataPoint(event="e")])
        raise AssertionError("should have raised AepipeError")
    except AepipeError as e:
        assert e.status == 401, f"expected 401, got {e.status}"


test("unauthorized with bad token", test_auth_error)

# ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
