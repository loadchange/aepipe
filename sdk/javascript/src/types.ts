export interface DataPoint {
  event: string;
  level?: string;
  blobs?: string[];
  doubles?: number[];
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

export interface AepipeOptions {
  /** aepipe worker URL, e.g. "https://aepipe.example.com" */
  baseUrl: string;
  /** ADMIN_TOKEN */
  token: string;
  /** Custom fetch (useful in Node.js < 18 or for testing) */
  fetch?: typeof globalThis.fetch;
}
