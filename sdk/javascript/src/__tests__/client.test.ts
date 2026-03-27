import { describe, it, expect, vi, beforeEach } from "vitest";
import { Aepipe, AepipeError, ValidationError } from "../client";

const BASE = "https://aepipe.example.com";
const TOKEN = "test-token";

function mockFetch(status = 200, body: unknown = {}) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
  return fn;
}

let fetchFn: ReturnType<typeof mockFetch>;
let client: Aepipe;

beforeEach(() => {
  fetchFn = mockFetch();
  client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });
});

function lastCall(): [string, RequestInit] {
  return fetchFn.mock.calls[fetchFn.mock.calls.length - 1];
}

// ─── ingest ───────────────────────────────────────────────────────────

describe("ingest", () => {
  it("sends points and returns result", async () => {
    fetchFn = mockFetch(200, { ok: true, written: 2 });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.ingest("proj", "store", [
      { event: "click" },
      { event: "scroll", level: "debug", blobs: ["x"], doubles: [1.5] },
    ]);

    expect(result).toEqual({ ok: true, written: 2 });
    const [url, init] = lastCall();
    expect(url).toBe(`${BASE}/v1/proj/store/ingest`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string).points).toHaveLength(2);
  });

  it("sends default level as info", async () => {
    await client.ingest("p", "s", [{ event: "e" }]);
    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.points[0].level).toBe("info");
  });

  it("omits empty blobs and doubles", async () => {
    await client.ingest("p", "s", [{ event: "e" }]);
    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.points[0]).not.toHaveProperty("blobs");
    expect(sent.points[0]).not.toHaveProperty("doubles");
  });
});

// ─── log ──────────────────────────────────────────────────────────────

describe("log", () => {
  it("sends log entries", async () => {
    fetchFn = mockFetch(200, { ok: true, written: 1 });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.log("p", "s", [
      { message: "hello", level: "error" },
    ]);
    expect(result).toEqual({ ok: true, written: 1 });

    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.logs[0].message).toBe("hello");
    expect(sent.logs[0].level).toBe("error");
  });

  it("spreads extra fields", async () => {
    await client.log("p", "s", [{ message: "m", user: "alice" }]);
    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.logs[0].user).toBe("alice");
  });
});

// ─── query ────────────────────────────────────────────────────────────

describe("query", () => {
  it("sends SQL and returns data", async () => {
    const data = { data: [{ cnt: 10 }] };
    fetchFn = mockFetch(200, data);
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.query("p", "s", "SELECT count() FROM aepipe");
    expect(result).toEqual(data);

    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.sql).toBe("SELECT count() FROM aepipe");
  });
});

// ─── rawlog ───────────────────────────────────────────────────────────

describe("rawlog", () => {
  it("returns parsed logs with default options", async () => {
    const body = {
      logs: [{ timestamp: "2025-01-01T00:00:00Z", level: "info", data: "msg" }],
      count: 1,
    };
    fetchFn = mockFetch(200, body);
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.rawlog("p", "s");
    expect(result.count).toBe(1);
    expect(result.logs[0].level).toBe("info");

    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent.limit).toBe(50);
  });

  it("passes limit, start, end", async () => {
    fetchFn = mockFetch(200, { logs: [], count: 0 });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    await client.rawlog("p", "s", { limit: 100, start: "2025-01-01", end: "2025-01-02" });
    const sent = JSON.parse(lastCall()[1].body as string);
    expect(sent).toEqual({ limit: 100, start: "2025-01-01", end: "2025-01-02" });
  });

  it("handles empty response", async () => {
    fetchFn = mockFetch(200, {});
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });
    const result = await client.rawlog("p", "s");
    expect(result.logs).toEqual([]);
    expect(result.count).toBe(0);
  });
});

// ─── list ─────────────────────────────────────────────────────────────

describe("listProjects", () => {
  it("returns project list", async () => {
    fetchFn = mockFetch(200, { projects: ["alpha", "beta"] });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.listProjects();
    expect(result.items).toEqual(["alpha", "beta"]);

    const [url, init] = lastCall();
    expect(init.method).toBe("GET");
    expect(url).toBe(`${BASE}/v1/projects`);
  });

  it("returns empty list when no projects key", async () => {
    fetchFn = mockFetch(200, {});
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });
    const result = await client.listProjects();
    expect(result.items).toEqual([]);
  });
});

describe("listLogstores", () => {
  it("returns logstore list", async () => {
    fetchFn = mockFetch(200, { logstores: ["access", "error"] });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    const result = await client.listLogstores("alpha");
    expect(result.items).toEqual(["access", "error"]);

    const [url] = lastCall();
    expect(url).toBe(`${BASE}/v1/alpha/logstores`);
  });
});

// ─── error handling ───────────────────────────────────────────────────

describe("errors", () => {
  it("throws AepipeError on non-ok response", async () => {
    fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('{"error":"unauthorized"}'),
    });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    await expect(client.ingest("p", "s", [{ event: "x" }])).rejects.toThrow(AepipeError);
  });

  it("includes status and message in error", async () => {
    fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      text: () => Promise.resolve("bad gateway"),
    });
    client = new Aepipe({ baseUrl: BASE, token: TOKEN, fetch: fetchFn });

    try {
      await client.query("p", "s", "SELECT 1");
      expect.unreachable("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(AepipeError);
      const err = e as AepipeError;
      expect(err.status).toBe(502);
      expect(err.message).toBe("bad gateway");
    }
  });
});

// ─── base URL handling ────────────────────────────────────────────────

describe("baseUrl", () => {
  it("strips trailing slashes", async () => {
    fetchFn = mockFetch(200, { projects: [] });
    client = new Aepipe({ baseUrl: BASE + "///", token: TOKEN, fetch: fetchFn });
    await client.listProjects();
    const [url] = lastCall();
    expect(url).toBe(`${BASE}/v1/projects`);
  });

  it("sends Authorization header", async () => {
    await client.ingest("p", "s", [{ event: "e" }]);
    const [, init] = lastCall();
    expect(init.headers).toMatchObject({
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    });
  });
});

// ─── validation ───────────────────────────────────────────────────────

describe("validation", () => {
  it("rejects invalid project name", async () => {
    await expect(client.ingest("bad name!", "s", [{ event: "e" }])).rejects.toThrow(ValidationError);
  });

  it("rejects empty project name", async () => {
    await expect(client.query("", "s", "SELECT 1")).rejects.toThrow(ValidationError);
  });

  it("rejects name too long", async () => {
    await expect(client.query("a".repeat(65), "s", "SELECT 1")).rejects.toThrow(ValidationError);
  });

  it("rejects ingest batch > 250", async () => {
    const points = Array.from({ length: 251 }, () => ({ event: "e" }));
    await expect(client.ingest("p", "s", points)).rejects.toThrow(ValidationError);
  });

  it("rejects log batch > 250", async () => {
    const logs = Array.from({ length: 251 }, () => ({ message: "m" }));
    await expect(client.log("p", "s", logs)).rejects.toThrow(ValidationError);
  });

  it("accepts valid names with dashes and underscores", async () => {
    await expect(
      client.query("my-project_v1", "log_store-2", "SELECT 1"),
    ).resolves.toBeDefined();
  });
});
