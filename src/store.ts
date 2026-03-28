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
  await db.batch([
    db.prepare(CREATE_TABLE_SQL),
    db.prepare(CREATE_INDEX_SQL),
  ]);
  tableReady = true;
}

async function cleanupExpired(db: D1Database): Promise<void> {
  const now = Date.now();
  await db
    .prepare(
      `DELETE FROM payloads WHERE ref_id IN (SELECT ref_id FROM payloads WHERE expires_at <= ? LIMIT ?)`,
    )
    .bind(now, CLEANUP_LIMIT)
    .run();
}

/**
 * Batch-write payloads to D1. Runs cleanup first, then inserts in a single
 * D1 batch (transactional).
 */
export async function batchWritePayloads(
  db: D1Database,
  items: { refId: string; payload: Record<string, unknown>; ttl?: number }[],
): Promise<void> {
  if (items.length === 0) return;
  await ensureTable(db);
  await cleanupExpired(db);

  const now = Date.now();
  const stmts = items.map((item) => {
    const ttl = item.ttl ?? DEFAULT_TTL_SECONDS;
    const expiresAt = now + ttl * 1000;
    return db
      .prepare(
        `INSERT INTO payloads (ref_id, payload, created_at, expires_at) VALUES (?, ?, ?, ?)`,
      )
      .bind(item.refId, JSON.stringify(item.payload), now, expiresAt);
  });

  await db.batch(stmts);
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
