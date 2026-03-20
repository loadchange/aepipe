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

export async function handleListProjects(env: Env): Promise<Response> {
  const sql = "SELECT DISTINCT blob1 FROM aepipe";
  const result = await cfAnalyticsQuery(env, sql);

  if (!result.ok) {
    return jsonResponse({ error: result.error }, 502);
  }

  const rows = (result.data as { data?: { blob1: string }[] })?.data ?? [];
  const projects = rows.map((r) => r.blob1);
  return jsonResponse({ projects });
}

export async function handleListLogStores(
  env: Env,
  project: string,
): Promise<Response> {
  const sql = `SELECT DISTINCT blob2 FROM aepipe WHERE blob1 = '${project}'`;
  const result = await cfAnalyticsQuery(env, sql);

  if (!result.ok) {
    return jsonResponse({ error: result.error }, 502);
  }

  const rows = (result.data as { data?: { blob2: string }[] })?.data ?? [];
  const logstores = rows.map((r) => r.blob2);
  return jsonResponse({ logstores });
}
