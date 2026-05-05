/**
 * D1 payload storage layer.
 *
 * Table: payloads
 * - ref_id     TEXT PRIMARY KEY  — UUID linking to AE blob5
 * - payload    TEXT NOT NULL      — JSON string
 * - created_at INTEGER NOT NULL   — Unix timestamp (ms)
 * - expires_at INTEGER NOT NULL   — Unix timestamp (ms)
 *
 * Expiration: every read/write first deletes rows where expires_at <= now.
 */

/** Default TTL: 90 days in seconds (matches AE data retention). */
const DEFAULT_TTL_SECONDS = 90 * 24 * 60 * 60;

/** Max rows to delete per cleanup to avoid long-running queries. */
const CLEANUP_LIMIT = 1000;

/** Fraction of oldest rows evicted when D1 hits its size cap. */
const EVICTION_PERCENT = 0.3;

/** Same-isolate cooldown to prevent cascading evictions under concurrent load. */
const EVICTION_COOLDOWN_MS = 60_000;

/**
 * D1 capacity errors we recognize. The first is what D1 actually returned in
 * production; the second is the underlying SQLite message kept as defensive
 * fallback in case Cloudflare changes wording.
 */
const CAPACITY_ERROR_PATTERNS = [
  "Exceeded maximum DB size",
  "database or disk is full",
];

let lastEvictionAt = 0;

function isCapacityError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return CAPACITY_ERROR_PATTERNS.some((p) => msg.includes(p));
}

const CREATE_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS payloads (
    ref_id     TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
  )
`;

const CREATE_INDEX_SQL = `
  CREATE INDEX IF NOT EXISTS idx_payloads_expires_at ON payloads (expires_at)
`;

let tableReady = false;

async function ensureTable(db: D1Database): Promise<void> {
  if (tableReady) return;
  try {
    await db.batch([
      db.prepare(CREATE_TABLE_SQL),
      db.prepare(CREATE_INDEX_SQL),
    ]);
    tableReady = true;
  } catch (err) {
    tableReady = false;
    throw err;
  }
}

/** Best-effort cleanup. Failure here must NOT block reads/writes. */
async function cleanupExpired(db: D1Database): Promise<void> {
  const now = Date.now();
  try {
    await db
      .prepare(
        `DELETE FROM payloads WHERE ref_id IN (SELECT ref_id FROM payloads WHERE expires_at <= ? LIMIT ?)`,
      )
      .bind(now, CLEANUP_LIMIT)
      .run();
  } catch (err) {
    console.warn("payload cleanup failed", err);
  }
}

/**
 * Drop the oldest `percent` fraction of rows. Used as rolling-eviction when
 * D1 reports capacity exhaustion: gives the next write attempt headroom
 * without operator intervention.
 */
async function evictOldest(db: D1Database, percent: number): Promise<number> {
  const countRes = await db
    .prepare(`SELECT COUNT(*) AS n FROM payloads`)
    .first<{ n: number }>();
  const total = countRes?.n ?? 0;
  if (total === 0) return 0;

  const toDelete = Math.max(1, Math.floor(total * percent));
  const result = await db
    .prepare(
      `DELETE FROM payloads WHERE ref_id IN (
         SELECT ref_id FROM payloads ORDER BY created_at ASC LIMIT ?
       )`,
    )
    .bind(toDelete)
    .run();

  const deleted = result.meta?.changes ?? toDelete;
  console.warn(
    `D1 eviction: deleted ${deleted}/${total} oldest payloads (${Math.round(percent * 100)}%)`,
  );
  return deleted;
}

/**
 * Batch-write payloads to D1. Runs cleanup first, then inserts in a single
 * D1 batch (transactional). On capacity exhaustion, evicts oldest rows and
 * retries once; if the retry still fails, the error propagates so the caller
 * can degrade (ingest.ts surfaces this as `payload_degraded:true`).
 */
export async function batchWritePayloads(
  db: D1Database,
  items: { refId: string; payload: Record<string, unknown>; ttl?: number }[],
): Promise<void> {
  if (items.length === 0) return;
  await ensureTable(db);
  await cleanupExpired(db);

  // D1 PreparedStatements are single-use; rebuild on retry. Refreshing now
  // also keeps created_at honest if the retry happens after eviction work.
  const buildStmts = () => {
    const now = Date.now();
    return items.map((item) => {
      const ttl = item.ttl ?? DEFAULT_TTL_SECONDS;
      const expiresAt = now + ttl * 1000;
      return db
        .prepare(
          `INSERT INTO payloads (ref_id, payload, created_at, expires_at) VALUES (?, ?, ?, ?)`,
        )
        .bind(item.refId, JSON.stringify(item.payload), now, expiresAt);
    });
  };

  try {
    await db.batch(buildStmts());
  } catch (err) {
    if (!isCapacityError(err)) throw err;

    const now = Date.now();
    if (now - lastEvictionAt < EVICTION_COOLDOWN_MS) {
      console.warn("D1 capacity error during eviction cooldown; degrading");
      throw err;
    }
    lastEvictionAt = now;

    await evictOldest(db, EVICTION_PERCENT);
    await db.batch(buildStmts());
  }
}

export interface PayloadRow {
  ref_id: string;
  payload: string;
  created_at: number;
  expires_at: number;
}

/**
 * Read payloads by ref_ids. Runs cleanup first.
 */
export async function readPayloads(
  db: D1Database,
  refIds: string[],
): Promise<PayloadRow[]> {
  if (refIds.length === 0) return [];
  await ensureTable(db);
  await cleanupExpired(db);

  const placeholders = refIds.map(() => "?").join(", ");
  const sql = `SELECT ref_id, payload, created_at, expires_at FROM payloads WHERE ref_id IN (${placeholders})`;
  const result = await db.prepare(sql).bind(...refIds).all<PayloadRow>();
  return result.results ?? [];
}
