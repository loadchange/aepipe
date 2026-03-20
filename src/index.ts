export interface Env {
  LOGS: AnalyticsEngineDataset;
  ADMIN_TOKEN: string;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

export interface DataPoint {
  event: string;
  level?: string;
  blobs?: string[];
  doubles?: number[];
}

export interface IngestPayload {
  points: DataPoint[];
}

const NAME_RE = /^[a-zA-Z0-9_-]{1,64}$/;

export function authorize(request: Request, env: Env): boolean {
  const header = request.headers.get("Authorization");
  if (!header) return false;
  const [scheme, token] = header.split(" ", 2);
  return scheme === "Bearer" && token === env.ADMIN_TOKEN;
}

export function validateName(name: string): boolean {
  return NAME_RE.test(name);
}

function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status, headers: corsHeaders() });
}

import { handleIngest } from "./ingest";
import { handleQuery, handleListProjects, handleListLogStores } from "./query";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    // parts[0] = "v1", parts[1..] = route segments

    if (parts[0] !== "v1") {
      return jsonResponse({ error: "not found" }, 404);
    }

    if (!authorize(request, env)) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }

    // GET /v1/projects
    if (parts.length === 2 && parts[1] === "projects" && request.method === "GET") {
      return handleListProjects(env);
    }

    // GET /v1/{project}/logstores
    if (parts.length === 3 && parts[2] === "logstores" && request.method === "GET") {
      const project = parts[1];
      if (!validateName(project)) {
        return jsonResponse({ error: "invalid project name" }, 400);
      }
      return handleListLogStores(env, project);
    }

    // POST /v1/{project}/{logstore}/{action}
    if (parts.length === 4 && request.method === "POST") {
      const [, project, logstore, action] = parts;
      if (!validateName(project)) {
        return jsonResponse({ error: "invalid project name" }, 400);
      }
      if (!validateName(logstore)) {
        return jsonResponse({ error: "invalid logstore name" }, 400);
      }

      if (action === "ingest") {
        return handleIngest(request, env, project, logstore);
      }
      if (action === "query") {
        return handleQuery(request, env, project, logstore);
      }
    }

    return jsonResponse({ error: "not found" }, 404);
  },
};
