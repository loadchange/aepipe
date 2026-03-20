import type { Env, DataPoint, IngestPayload } from "./index";
import { jsonResponse } from "./index";

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
    written++;
  }

  return jsonResponse({ ok: true, written });
}
