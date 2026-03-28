export interface DataPoint {
  /**
   * Event name (required, non-empty).
   * Mapped to blob3 in Analytics Engine.
   */
  event: string;
  /**
   * Log level. Defaults to "info".
   * Mapped to blob4 in Analytics Engine.
   */
  level?: string;
  /**
   * Extra string metadata fields for grouping/filtering (NOT aggregatable).
   *
   * - Max **15** items (the system uses blob1–blob5 for project, logstore, event, level, ref_id;
   *   your blobs occupy blob6–blob20)
   * - All blobs in a data point (including system blobs) share a **16 KB total size limit**.
   *   Exceeding this causes **silent truncation** by Cloudflare — data is lost without error.
   * - Each blob is a UTF-8 string; keep individual values short to stay within the 16 KB budget.
   *
   * @see https://developers.cloudflare.com/analytics/analytics-engine/limits/
   */
  blobs?: string[];
  /**
   * Numeric metric fields (64-bit IEEE 754 floats). Can be aggregated with
   * SUM, AVG, QUANTILE, MIN, MAX in queries.
   *
   * - Max **20** items (doubles[0]–doubles[19] map to double1–double20)
   *
   * @see https://developers.cloudflare.com/analytics/analytics-engine/limits/
   */
  doubles?: number[];
  /**
   * Extended JSON data stored in Cloudflare D1 (separate from Analytics Engine).
   * Requires D1 binding (`DB`) configured on the server. If D1 is not configured,
   * this field is silently ignored.
   *
   * Use this for large data that would exceed AE's 16 KB blob limit
   * (e.g., stack traces, full request/response dumps).
   * A UUID reference (`ref_id`) is automatically generated and stored in AE blob5,
   * linking the AE data point to the D1 payload.
   */
  payload?: Record<string, unknown>;
  /**
   * Payload TTL in seconds. Default: 7,776,000 (90 days, matching AE retention).
   * Only meaningful when `payload` is set.
   */
  ttl?: number;
}

export interface LogEntry {
  message: string;
  level?: string;
  [key: string]: unknown;
}

export interface IngestResult {
  ok: boolean;
  written: number;
}

export interface LogResult {
  ok: boolean;
  written: number;
}

export interface RawLogEntry {
  timestamp: string;
  level: string;
  data: unknown;
}

export interface RawLogResult {
  logs: RawLogEntry[];
  count: number;
}

export type QueryResult = unknown;

export interface ListResult {
  items: string[];
}

export interface DetailEntry {
  ref_id: string;
  payload: Record<string, unknown>;
  created_at: number;
  expires_at: number;
}

export interface DetailResult {
  results: DetailEntry[];
}

export interface AepipeOptions {
  /** aepipe worker URL, e.g. "https://aepipe.example.com" */
  baseUrl: string;
  /** ADMIN_TOKEN */
  token: string;
  /** Custom fetch (useful in Node.js < 18 or for testing) */
  fetch?: typeof globalThis.fetch;
}
