import type {
  AepipeOptions,
  DataPoint,
  DetailResult,
  IngestResult,
  ListResult,
  LogEntry,
  LogResult,
  QueryResult,
  RawLogResult,
} from "./types";

const NAME_RE = /^[a-zA-Z0-9_-]{1,64}$/;
const MAX_BATCH = 250;
/**
 * Cloudflare Analytics Engine limit: total blob size per data point is 16 KB.
 * @see https://developers.cloudflare.com/analytics/analytics-engine/limits/
 */
const MAX_BLOB_BYTES = 16 * 1024;
/**
 * Cloudflare Analytics Engine limit: index must not exceed 96 bytes.
 * Index is formatted as "{project}/{logstore}".
 */
const MAX_INDEX_BYTES = 96;

export class AepipeError extends Error {
  public readonly status: number;
  public readonly message: string;

  constructor(status: number, message: string) {
    super(`aepipe error ${status}: ${message}`);
    this.name = "AepipeError";
    this.status = status;
    this.message = message;
  }
}

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

function validateName(name: string, label: string): void {
  if (!NAME_RE.test(name)) {
    throw new ValidationError(`invalid ${label}: '${name}'`);
  }
}

/** Estimate UTF-8 byte length of a string. */
function byteLength(s: string): number {
  // TextEncoder is available in Node 18+ and all modern browsers
  if (typeof TextEncoder !== "undefined") {
    return new TextEncoder().encode(s).byteLength;
  }
  // Fallback: each char is at most 4 bytes in UTF-8
  let len = 0;
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    if (code <= 0x7f) len += 1;
    else if (code <= 0x7ff) len += 2;
    else if (code >= 0xd800 && code <= 0xdbff) { len += 4; i++; }
    else len += 3;
  }
  return len;
}

/**
 * Validate that total blob size (including system blobs) does not exceed 16 KB.
 * System blobs: project, logstore, event, level, ref_id.
 */
function validateBlobSize(
  project: string,
  logstore: string,
  p: DataPoint,
  index: number,
): void {
  // ref_id is a UUID (36 bytes) when payload is set, empty string otherwise
  const refIdEstimate = p.payload ? "00000000-0000-0000-0000-000000000000" : "";
  const allBlobs = [project, logstore, p.event, p.level ?? "info", refIdEstimate, ...(p.blobs ?? [])];
  let total = 0;
  for (const b of allBlobs) {
    total += byteLength(b);
  }
  if (total > MAX_BLOB_BYTES) {
    throw new ValidationError(
      `points[${index}]: total blob size ${total} bytes exceeds the 16 KB (${MAX_BLOB_BYTES} bytes) ` +
      `Cloudflare Analytics Engine limit. Reduce blob content to prevent silent data truncation.`,
    );
  }
}

function serializePoint(p: DataPoint): Record<string, unknown> {
  const d: Record<string, unknown> = { event: p.event, level: p.level ?? "info" };
  if (p.blobs?.length) d.blobs = p.blobs;
  if (p.doubles?.length) d.doubles = p.doubles;
  if (p.payload) d.payload = p.payload;
  if (p.ttl !== undefined) d.ttl = p.ttl;
  return d;
}

export class Aepipe {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchFn: typeof globalThis.fetch;

  constructor(options: AepipeOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.token = options.token;
    this.fetchFn = options.fetch ?? globalThis.fetch;
  }

  // --- ingest ---

  async ingest(
    project: string,
    logstore: string,
    points: DataPoint[],
  ): Promise<IngestResult> {
    validateName(project, "project");
    validateName(logstore, "logstore");
    if (byteLength(`${project}/${logstore}`) > MAX_INDEX_BYTES) {
      throw new ValidationError(
        `index "${project}/${logstore}" exceeds the 96-byte Cloudflare Analytics Engine limit. ` +
        `Use shorter project/logstore names.`,
      );
    }
    if (points.length > MAX_BATCH) {
      throw new ValidationError(`max ${MAX_BATCH} points per request, got ${points.length}`);
    }
    for (let i = 0; i < points.length; i++) {
      if ((points[i].blobs?.length ?? 0) > 15) {
        throw new ValidationError(
          `points[${i}]: max 15 user blobs (blob6–blob20), got ${points[i].blobs!.length}`,
        );
      }
      if ((points[i].doubles?.length ?? 0) > 20) {
        throw new ValidationError(
          `points[${i}]: max 20 doubles, got ${points[i].doubles!.length}`,
        );
      }
      validateBlobSize(project, logstore, points[i], i);
    }
    return this.post<IngestResult>(`/v1/${project}/${logstore}/ingest`, {
      points: points.map(serializePoint),
    });
  }

  // --- log ---

  async log(
    project: string,
    logstore: string,
    logs: LogEntry[],
  ): Promise<LogResult> {
    validateName(project, "project");
    validateName(logstore, "logstore");
    if (logs.length > MAX_BATCH) {
      throw new ValidationError(`max ${MAX_BATCH} logs per request, got ${logs.length}`);
    }
    return this.post<LogResult>(`/v1/${project}/${logstore}/log`, { logs });
  }

  // --- query ---

  async query(project: string, logstore: string, sql: string): Promise<QueryResult> {
    validateName(project, "project");
    validateName(logstore, "logstore");
    return this.post<QueryResult>(`/v1/${project}/${logstore}/query`, { sql });
  }

  // --- rawlog ---

  async rawlog(
    project: string,
    logstore: string,
    opts?: { limit?: number; start?: string; end?: string },
  ): Promise<RawLogResult> {
    validateName(project, "project");
    validateName(logstore, "logstore");
    const body = { limit: 50, ...opts };
    const resp = await this.post<RawLogResult>(`/v1/${project}/${logstore}/rawlog`, body);
    return { logs: resp.logs ?? [], count: resp.count ?? 0 };
  }

  // --- detail ---

  async detail(
    project: string,
    logstore: string,
    refIds: string[],
  ): Promise<DetailResult> {
    validateName(project, "project");
    validateName(logstore, "logstore");
    if (refIds.length === 0) {
      return { results: [] };
    }
    if (refIds.length > 100) {
      throw new ValidationError(`max 100 ref_ids per request, got ${refIds.length}`);
    }
    return this.post<DetailResult>(`/v1/${project}/${logstore}/detail`, {
      ref_ids: refIds,
    });
  }

  // --- list ---

  async listProjects(): Promise<ListResult> {
    const resp = await this.get<{ projects?: string[] }>("/v1/projects");
    return { items: resp.projects ?? [] };
  }

  async listLogstores(project: string): Promise<ListResult> {
    validateName(project, "project");
    const resp = await this.get<{ logstores?: string[] }>(`/v1/${project}/logstores`);
    return { items: resp.logstores ?? [] };
  }

  // --- internal ---

  private headers(): HeadersInit {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
      "User-Agent": "aepipe-sdk-js/0.1.0",
    };
  }

  private async request<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
    const init: RequestInit = {
      method,
      headers: this.headers(),
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }
    const res = await this.fetchFn(`${this.baseUrl}${path}`, init);
    if (!res.ok) {
      const text = await res.text();
      throw new AepipeError(res.status, text);
    }
    return res.json() as Promise<T>;
  }

  private get<T = unknown>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  private post<T = unknown>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }
}
