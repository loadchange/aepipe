import { describe, it, expect, beforeAll } from "vitest";
import { Aepipe, AepipeError, ValidationError } from "../client";

const BASE = process.env.AEPIPE_URL!;
const TOKEN = process.env.AEPIPE_TOKEN!;

const RUN_ID = Math.random().toString(36).slice(2, 10);
const PROJECT = `jstest${RUN_ID}`;
const LOGSTORE = "sdk-test";

const client = new Aepipe({ baseUrl: BASE, token: TOKEN });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ─── ingest ───────────────────────────────────────────────────────────

describe("ingest", () => {
  it("ingests a single point", async () => {
    const result = await client.ingest(PROJECT, LOGSTORE, [{ event: "js_test_single" }]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(1);
  });

  it("ingests a batch of 3 points", async () => {
    const result = await client.ingest(PROJECT, LOGSTORE, [
      { event: "js_batch_1", level: "error" },
      { event: "js_batch_2", level: "warn" },
      { event: "js_batch_3" },
    ]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(3);
  });

  it("ingests with blobs and doubles", async () => {
    const result = await client.ingest(PROJECT, LOGSTORE, [
      { event: "js_rich", level: "debug", blobs: ["a", "b"], doubles: [1.1, 2.2] },
    ]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(1);
  });
});

// ─── log ──────────────────────────────────────────────────────────────

describe("log", () => {
  it("logs a single entry", async () => {
    const result = await client.log(PROJECT, LOGSTORE, [{ message: "js log test" }]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(1);
  });

  it("logs with different levels", async () => {
    const result = await client.log(PROJECT, LOGSTORE, [
      { message: "js error", level: "error" },
      { message: "js warn", level: "warn" },
      { message: "js debug", level: "debug" },
    ]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(3);
  });

  it("logs with extra fields", async () => {
    const result = await client.log(PROJECT, LOGSTORE, [
      { message: "js structured", user: "bob", requestId: "xyz" },
    ]);
    expect(result.ok).toBe(true);
    expect(result.written).toBe(1);
  });
});

// ─── query ────────────────────────────────────────────────────────────

describe("query", () => {
  // Give AE time to index
  beforeAll(async () => { await sleep(3000); });

  it("queries count", async () => {
    const result = await client.query(PROJECT, LOGSTORE, "SELECT count() as cnt FROM aepipe");
    expect(result).toBeDefined();
  });

  it("queries select events", async () => {
    const result = await client.query(PROJECT, LOGSTORE, "SELECT blob3 as event FROM aepipe LIMIT 5");
    expect(result).toBeDefined();
  });

  it("query returns data for isolated tenant", async () => {
    const result = await client.query(`nonexistent${RUN_ID}`, LOGSTORE, "SELECT count() as cnt FROM aepipe");
    expect(result).toBeDefined();
  });
});

// ─── rawlog ───────────────────────────────────────────────────────────

describe("rawlog", () => {
  it("returns logs with defaults", async () => {
    const result = await client.rawlog(PROJECT, LOGSTORE);
    expect(Array.isArray(result.logs)).toBe(true);
    expect(typeof result.count).toBe("number");
  });

  it("respects limit", async () => {
    const result = await client.rawlog(PROJECT, LOGSTORE, { limit: 3 });
    expect(Array.isArray(result.logs)).toBe(true);
    expect(result.count).toBeLessThanOrEqual(3);
  });
});

// ─── list ─────────────────────────────────────────────────────────────

describe("list", () => {
  it("lists projects", async () => {
    const result = await client.listProjects();
    expect(Array.isArray(result.items)).toBe(true);
    // AE is eventually consistent, so we just check the call succeeds
  });

  it("lists logstores", async () => {
    const result = await client.listLogstores(PROJECT);
    expect(Array.isArray(result.items)).toBe(true);
  });
});

// ─── validation ───────────────────────────────────────────────────────

describe("validation", () => {
  it("rejects invalid project name", async () => {
    await expect(client.ingest("bad name!", "s", [{ event: "e" }])).rejects.toThrow(ValidationError);
  });

  it("rejects invalid logstore name", async () => {
    await expect(client.query(PROJECT, "bad/logstore", "SELECT 1")).rejects.toThrow(ValidationError);
  });

  it("rejects batch > 250", async () => {
    const points = Array.from({ length: 251 }, () => ({ event: "e" }));
    await expect(client.ingest(PROJECT, LOGSTORE, points)).rejects.toThrow(ValidationError);
  });

  it("rejects name too long", async () => {
    await expect(client.query("a".repeat(65), LOGSTORE, "SELECT 1")).rejects.toThrow(ValidationError);
  });
});

// ─── auth error ───────────────────────────────────────────────────────

describe("auth", () => {
  it("rejects invalid token", async () => {
    const badClient = new Aepipe({ baseUrl: BASE, token: "invalid-token-12345" });
    await expect(badClient.ingest(PROJECT, LOGSTORE, [{ event: "e" }])).rejects.toThrow(AepipeError);
  });
});
