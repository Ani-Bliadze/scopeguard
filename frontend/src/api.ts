import type { AuditEvent, Health, PolicySummary, Persona, SessionInfo, Task } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let csrf = "";

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (init.method && init.method !== "GET") headers["x-csrf-token"] = csrf;
  const r = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) }, credentials: "same-origin" });
  let body: any = null;
  try {
    body = await r.json();
  } catch {
    body = null;
  }
  if (!r.ok) throw new ApiError(r.status, body?.error ?? "HTTP_" + r.status, body?.message ?? "Request failed");
  return body as T;
}

export const api = {
  health: () => req<Health>("/api/health"),
  async session(): Promise<SessionInfo | null> {
    const s = await req<SessionInfo & { active: boolean }>("/api/session");
    if (!s.active) return null;
    csrf = s.csrf_token;
    return s;
  },
  async persona(persona: Persona): Promise<SessionInfo> {
    const s = await req<SessionInfo>("/api/demo/session", { method: "POST", body: JSON.stringify({ persona }) });
    csrf = s.csrf_token;
    return s;
  },
  startTask: (request: string) =>
    req<{ task_id: string }>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ request, client_request_id: crypto.randomUUID() }),
    }),
  startProbe: (probe: string) =>
    req<{ task_id: string }>("/api/demo/probe", { method: "POST", body: JSON.stringify({ probe }) }),
  task: (id: string) => req<Task>(`/api/tasks/${id}`),
  events: (id: string) => req<{ events: AuditEvent[] }>(`/api/tasks/${id}/events`),
  policy: () => req<PolicySummary>("/api/policy/summary"),
  decide: (approvalId: string, decision: "approve" | "deny") =>
    req(`/api/approvals/${approvalId}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  access: (paused: boolean) =>
    req<{ access_paused: boolean }>("/api/session/access", { method: "POST", body: JSON.stringify({ paused }) }),
  reset: () => req<{ reset: boolean }>("/api/demo/reset", { method: "POST" }),
  auditExport: () => req<unknown>("/api/audit/export"),
};
