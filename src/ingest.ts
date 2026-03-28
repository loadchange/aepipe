import type { Env, DataPoint, IngestPayload } from "./index";
import { jsonResponse } from "./index";
import { batchWritePayloads } from "./store";

interface LogEntry {
  message: string;
  level?: string;
  [key: string]: unknown;
}

/**
 * Map an aepipe DataPoint to a Cloudflare Analytics Engine data point.
 *
 * Cloudflare AE limits (https://developers.cloudflare.com/analytics/analytics-engine/limits/):
 * - 20 blobs max per data point, each is a UTF-8 string
 * - 20 doubles max per data point, each is a 64-bit IEEE 754 float
 * - 1 index max, up to 96 bytes — used as sampling key
 * - **Total blob size per data point: 16 KB** — exceeding causes SILENT TRUNCATION
 * - 250 data points per Worker invocation
 * - Data retained for 3 months
 *
 * Blob slot allocation:
 *   blob1  = project name  (grouping / tenant isolation)
 *   blob2  = logstore name (sub-tenant isolation)
 *   blob3  = event         (user-provided, required)
 *   blob4  = level         (user-provided, defaults to "info")
 *   blob5  = ref_id        (D1 payload UUID, empty string "" when no payload)
 *   blob6–blob20 = user blobs[0..14] (max 15 extra)
 *
 * Double slot allocation:
 *   double1–double20 = user doubles[0..19] (passed through unchanged)
 */
export function mapDataPoint(
  project: string,
  logstore: string,
  p: DataPoint,
  refId?: string,
): AnalyticsEngineDataPoint {
  const blobs: string[] = [
    project,           // blob1 — project (tenant key)
    logstore,          // blob2 — logstore (sub-tenant key)
    p.event,           // blob3 — event name
    p.level ?? "info", // blob4 — log level
    refId ?? "",       // blob5 — D1 payload ref_id (empty if no payload)
    ...(p.blobs ?? []),  // blob6–blob20 — user blobs (max 15)
  ];
  return {
    indexes: [`${project}/${logstore}`], // max 96 bytes
    blobs,    // total size of all blobs must not exceed 16 KB
    doubles: p.doubles ?? [],  // 64-bit floats, aggregatable (SUM/AVG/QUANTILE/MIN/MAX)
  };
}

export async function handleIngest(
  request: Request,
  env: Env,
  project: string,
  logstore: string,
): Promise<Response> {
  let body: IngestPayload;
  try {
    body = await request.json<IngestPayload>();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  if (!Array.isArray(body.points) || body.points.length === 0) {
    return jsonResponse({ error: "points must be a non-empty array" }, 400);
  }

  if (body.points.length > 250) {
    return jsonResponse({ error: "max 250 points per request" }, 400);
  }

  // Phase 1: collect valid points and D1 operations
  const d1Ops: { refId: string; payload: Record<string, unknown>; ttl?: number }[] = [];
  const validPoints: { point: DataPoint; refId?: string }[] = [];

  for (const point of body.points) {
    if (typeof point.event !== "string" || point.event === "") {
      continue;
    }
    let refId: string | undefined;
    if (point.payload && env.DB) {
      refId = crypto.randomUUID();
      d1Ops.push({ refId, payload: point.payload, ttl: point.ttl });
    }
    validPoints.push({ point, refId });
  }

  // Phase 2: batch write to D1 (cleanup expired + insert)
  if (d1Ops.length > 0 && env.DB) {
    await batchWritePayloads(env.DB, d1Ops);
  }

  // Phase 3: write all AE data points
  for (const { point, refId } of validPoints) {
    env.LOGS.writeDataPoint(mapDataPoint(project, logstore, point, refId));
    console.log(JSON.stringify({ project, logstore, ...point }));
  }

  return jsonResponse({ ok: true, written: validPoints.length });
}

export async function handleLog(
  request: Request,
  _env: Env,
  project: string,
  logstore: string,
): Promise<Response> {
  let body: { logs?: LogEntry[] };
  try {
    body = await request.json<typeof body>();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  if (!Array.isArray(body.logs) || body.logs.length === 0) {
    return jsonResponse({ error: "logs must be a non-empty array" }, 400);
  }

  if (body.logs.length > 250) {
    return jsonResponse({ error: "max 250 logs per request" }, 400);
  }

  let written = 0;
  for (const entry of body.logs) {
    if (typeof entry.message !== "string" || entry.message === "") {
      continue;
    }
    const level = entry.level ?? "info";
    const log = { project, logstore, level, ...entry };
    switch (level) {
      case "error":
        console.error(JSON.stringify(log));
        break;
      case "warn":
        console.warn(JSON.stringify(log));
        break;
      case "debug":
        console.debug(JSON.stringify(log));
        break;
      default:
        console.log(JSON.stringify(log));
    }
    written++;
  }

  return jsonResponse({ ok: true, written });
}
