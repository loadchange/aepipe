import type { Env } from "./index";
import { jsonResponse } from "./index";

async function cfAnalyticsQuery(
  env: Env,
  sql: string,
): Promise<{ ok: boolean; data?: unknown; error?: string }> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "text/plain",
    },
    body: sql,
  });
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `CF API ${res.status}: ${text}` };
  }
  const data = await res.json();
  return { ok: true, data };
}

function injectTenantFilter(
  sql: string,
  project: string,
  logstore: string,
): string {
  const filter = `blob1 = '${project}' AND blob2 = '${logstore}'`;

  const whereMatch = sql.match(/\bWHERE\b/i);
  if (whereMatch && whereMatch.index !== undefined) {
    const insertPos = whereMatch.index + whereMatch[0].length;
    return (
      sql.slice(0, insertPos) +
      ` ${filter} AND` +
      sql.slice(insertPos)
    );
  }

  // No WHERE — insert before GROUP BY / ORDER BY / LIMIT / end
  const clauseMatch = sql.match(/\b(GROUP\s+BY|ORDER\s+BY|LIMIT|FORMAT)\b/i);
  if (clauseMatch && clauseMatch.index !== undefined) {
    return (
      sql.slice(0, clauseMatch.index) +
      `WHERE ${filter} ` +
      sql.slice(clauseMatch.index)
    );
  }

  return `${sql} WHERE ${filter}`;
}

export async function handleQuery(
  request: Request,
  env: Env,
  project: string,
  logstore: string,
): Promise<Response> {
  let body: { sql?: string };
  try {
    body = await request.json<{ sql?: string }>();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  if (typeof body.sql !== "string" || body.sql.trim() === "") {
    return jsonResponse({ error: "sql is required" }, 400);
  }

  const rewritten = injectTenantFilter(body.sql, project, logstore);
  const result = await cfAnalyticsQuery(env, rewritten);

  if (!result.ok) {
    return jsonResponse({ error: result.error }, 502);
  }

  return jsonResponse(result.data);
}

export async function handleRawLog(
  request: Request,
  env: Env,
  project: string,
  logstore: string,
): Promise<Response> {
  let body: { limit?: number; start?: string; end?: string };
  try {
    body = await request.json<typeof body>();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  const limit = Math.min(body.limit ?? 50, 200);
  const now = Date.now();
  const endTime = body.end ? new Date(body.end).getTime() : now;
  const startTime = body.start
    ? new Date(body.start).getTime()
    : now - 6 * 3600_000;

  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/observability/telemetry/query`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      queryId: "",
      view: "events",
      parameters: {
        filters: [
          {
            key: "$workers.scriptName",
            operation: "eq",
            type: "string",
            value: "aepipe",
          },
          {
            key: "project",
            operation: "eq",
            type: "string",
            value: project,
          },
          {
            key: "logstore",
            operation: "eq",
            type: "string",
            value: logstore,
          },
        ],
        filterCombination: "and",
        limit,
      },
      timeframe: {
        from: startTime,
        to: endTime,
      },
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    return jsonResponse(
      { error: `CF Telemetry API ${res.status}: ${text}` },
      502,
    );
  }

  const result = await res.json<{
    success: boolean;
    errors?: { message: string }[];
    result?: {
      events?: {
        count?: number;
        events?: {
          $metadata?: { message?: string; level?: string };
          timestamp?: number;
          [key: string]: unknown;
        }[];
      };
    };
  }>();

  if (!result.success || result.errors?.length) {
    const msg = result.errors?.map((e) => e.message).join("; ") ?? "unknown";
    return jsonResponse({ error: msg }, 502);
  }

  const events = result.result?.events?.events ?? [];
  const logs: { timestamp: string; level: string; data: unknown }[] = [];

  for (const evt of events) {
    const source = (evt as Record<string, unknown>).source as Record<string, unknown> | undefined;
    const metadata = evt.$metadata ?? {};
    logs.push({
      timestamp: evt.timestamp
        ? new Date(evt.timestamp).toISOString()
        : "",
      level: (source?.level as string) ?? metadata.level ?? "info",
      data: source ?? metadata.message ?? "",
    });
  }

  return jsonResponse({ logs, count: logs.length });
}

export async function handleListProjects(env: Env): Promise<Response> {
  const sql = "SELECT blob1 FROM aepipe GROUP BY blob1 ORDER BY blob1";
  const result = await cfAnalyticsQuery(env, sql);

  if (!result.ok) {
    return jsonResponse({ error: result.error }, 502);
  }

  const rows = (result.data as { data?: { blob1: string }[] })?.data ?? [];
  const projects = [...new Set(rows.map((r) => r.blob1))];
  return jsonResponse({ projects });
}

export async function handleListLogStores(
  env: Env,
  project: string,
): Promise<Response> {
  const sql = `SELECT blob2 FROM aepipe WHERE blob1 = '${project}' GROUP BY blob2 ORDER BY blob2`;
  const result = await cfAnalyticsQuery(env, sql);

  if (!result.ok) {
    return jsonResponse({ error: result.error }, 502);
  }

  const rows = (result.data as { data?: { blob2: string }[] })?.data ?? [];
  const logstores = [...new Set(rows.map((r) => r.blob2))];
  return jsonResponse({ logstores });
}
