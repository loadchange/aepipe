import type { Env, DataPoint, IngestPayload } from "./index";
import { jsonResponse } from "./index";

interface LogEntry {
  message: string;
  level?: string;
  [key: string]: unknown;
}

export function mapDataPoint(
  project: string,
  logstore: string,
  p: DataPoint,
): AnalyticsEngineDataPoint {
  const blobs: string[] = [
    project,
    logstore,
    p.event,
    p.level ?? "info",
    ...(p.blobs ?? []),
  ];
  return {
    indexes: [`${project}/${logstore}`],
    blobs,
    doubles: p.doubles ?? [],
  };
}

export async function handleIngest(
  request: Request,
  env: Env,
  project: string,
  logstore: string,
): Promise<Response> {
  let payload: IngestPayload;
  try {
    payload = await request.json<IngestPayload>();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  if (!Array.isArray(payload.points) || payload.points.length === 0) {
    return jsonResponse({ error: "points must be a non-empty array" }, 400);
  }

  if (payload.points.length > 250) {
    return jsonResponse({ error: "max 250 points per request" }, 400);
  }

  let written = 0;
  for (const point of payload.points) {
    if (typeof point.event !== "string" || point.event === "") {
      continue;
    }
    env.LOGS.writeDataPoint(mapDataPoint(project, logstore, point));
    console.log(JSON.stringify({ project, logstore, ...point }));
    written++;
  }

  return jsonResponse({ ok: true, written });
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
