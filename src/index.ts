export interface Env {
  LOGS: AnalyticsEngineDataset;
  INGEST_TOKEN: string;
}

interface DataPoint {
  event: string;
  level?: string;
  index?: string;
  blobs?: string[];
  doubles?: number[];
}

interface IngestPayload {
  points: DataPoint[];
}

function authorize(request: Request, env: Env): boolean {
  const header = request.headers.get("Authorization");
  if (!header) return false;
  const [scheme, token] = header.split(" ", 2);
  return scheme === "Bearer" && token === env.INGEST_TOKEN;
}

function mapDataPoint(p: DataPoint): AnalyticsEngineDataPoint {
  // blob1 = event, blob2 = level, blob3+ = extra blobs
  const blobs: string[] = [p.event, p.level ?? "info", ...(p.blobs ?? [])];
  return {
    indexes: p.index ? [p.index] : [],
    blobs,
    doubles: p.doubles ?? [],
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204 });
    }

    if (request.method !== "POST") {
      return Response.json({ error: "method not allowed" }, { status: 405 });
    }

    if (!authorize(request, env)) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    let payload: IngestPayload;
    try {
      payload = await request.json<IngestPayload>();
    } catch {
      return Response.json({ error: "invalid json" }, { status: 400 });
    }

    if (!Array.isArray(payload.points) || payload.points.length === 0) {
      return Response.json({ error: "points must be a non-empty array" }, { status: 400 });
    }

    if (payload.points.length > 250) {
      return Response.json({ error: "max 250 points per request" }, { status: 400 });
    }

    let written = 0;
    for (const point of payload.points) {
      if (typeof point.event !== "string" || point.event === "") {
        continue;
      }
      env.LOGS.writeDataPoint(mapDataPoint(point));
      written++;
    }

    return Response.json({ ok: true, written });
  },
};
