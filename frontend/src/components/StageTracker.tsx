import { Check, CircleDashed, Clock, Database, KeyRound, Loader2, Network, ShieldCheck, Sparkles, X } from "lucide-react";
import type { Task } from "../types";

type StageState = "idle" | "active" | "ok" | "blocked" | "pending";

const INPUT_BLOCKS = new Set(["UNSUPPORTED_TASK", "HARD_DENY_SECRET_DISCLOSURE", "EMPTY_INPUT", "INPUT_TOO_LONG",
  "TASK_NOT_PERMITTED_FOR_ROLE", "SESSION_ACCESS_PAUSED"]);

export function stages(task: Task | null): [StageState, StageState, StageState] {
  if (!task) return ["idle", "idle", "idle"];
  const code = task.block?.code ?? "";
  if (task.kind === "probe") {
    const denied = (task.metrics.gateway_calls_denied as number) > 0;
    return ["ok", "ok", task.terminal ? (denied ? "blocked" : "ok") : "active"];
  }
  const s1: StageState = INPUT_BLOCKS.has(code) ? "blocked" : task.status === "CHECKING_INPUT" ? "active" : "ok";
  let s2: StageState = "idle";
  if (s1 === "ok") {
    if (task.selected_candidate_id) s2 = task.status === "AWAITING_APPROVAL" ? "pending" : "ok";
    else if (code === "BLOCKED_NO_SAFE_PLAN") s2 = "blocked";
    else s2 = "active";
  }
  if (code === "APPROVAL_DENIED" || code === "APPROVAL_EXPIRED") s2 = "blocked";
  let s3: StageState = "idle";
  if (s2 === "ok") {
    if (task.execution.verified_mcp_round_trip) s3 = "ok";
    else if (task.terminal) s3 = "blocked";
    else s3 = "active";
  }
  return [s1, s2, s3];
}

const STYLE: Record<StageState, string> = {
  idle: "border-line text-muted",
  active: "border-sky-400/60 text-sky-200",
  ok: "border-allow/60 text-allow",
  blocked: "border-deny/60 text-deny",
  pending: "border-pending/60 text-pending",
};

function Icon({ s }: { s: StageState }) {
  if (s === "ok") return <Check className="h-4 w-4" aria-hidden />;
  if (s === "blocked") return <X className="h-4 w-4" aria-hidden />;
  if (s === "active") return <Loader2 className="h-4 w-4 animate-spin" aria-hidden />;
  if (s === "pending") return <Clock className="h-4 w-4" aria-hidden />;
  return <CircleDashed className="h-4 w-4" aria-hidden />;
}

const WORD: Record<StageState, string> = { idle: "Waiting", active: "Running", ok: "Passed", blocked: "Stopped", pending: "Awaiting approval" };

export function StageTracker({ task }: { task: Task | null }) {
  const st = stages(task);
  const labels = ["1. Policy checked", "2. Safe plan selected", "3. MCP execution verified"];
  const subs = [
    task?.intent ? `Intent ${task.intent}` : "Input screening + supported task",
    task?.selected_candidate_id ? `Candidate ${task.selected_candidate_id} selected` : "Deterministic evaluation",
    task?.execution.protocol_version ? `MCP ${task.execution.protocol_version}` : "Real MCP round-trip",
  ];
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="list" aria-label="Pipeline stages">
      {st.map((s, i) => (
        <div key={i} role="listitem" className={`flex items-center gap-3 rounded-xl border bg-panel px-3 py-2.5 ${STYLE[s]}`}>
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-current/10 ring-1 ring-current/40">
            <Icon s={s} />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-text">{labels[i]}</span>
            <span className="block truncate text-xs">
              {WORD[s]} · <span className="text-muted">{subs[i]}</span>
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** Live data-path illustration driven by the actual execution record. */
export function DataPath({ task }: { task: Task | null }) {
  const steps = task?.execution.steps ?? [];
  const reached = steps.some((s) => s.ok);
  const denied = steps.some((s) => !s.ok);
  const tool = steps[0]?.tool_id ?? task?.candidates.find((c) => c.selected)?.tools[0] ?? "";
  const server = tool.startsWith("crm.") ? "crm" : tool.startsWith("analytics.") ? "analytics" : null;
  const secretUse = tool === "crm.get_connection_status" && reached;
  const blockedEarly = task?.terminal && !steps.length;
  const line = (on: boolean, bad = false) =>
    `h-0.5 flex-1 rounded ${bad ? "bg-deny/70" : on ? "bg-allow/80" : "bg-line"}`;
  const node = (on: boolean, bad = false) =>
    `flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-center text-[11px] leading-tight ${
      bad ? "border-deny/60 bg-deny/10" : on ? "border-allow/60 bg-allow/10" : "border-line bg-panel2/50"
    }`;
  return (
    <div className="card p-3" aria-label="Data path">
      <div className="mb-2 flex items-center justify-between text-xs text-muted">
        <span className="font-semibold uppercase tracking-wider">Data path (from this run's MCP trace)</span>
        {blockedEarly && <span className="text-deny">Stopped before any tool call</span>}
      </div>
      <div className="flex items-center gap-1.5">
        <div className={node(!!task && !blockedEarly)}>
          <Network className="h-4 w-4" aria-hidden />
          Agent worker
          <span className="text-muted">MCP client</span>
        </div>
        <div className={line(steps.length > 0)} />
        <div className={node(steps.length > 0, denied && !reached)}>
          <ShieldCheck className="h-4 w-4 text-allow" aria-hidden />
          ScopeGuard
          <span className="text-muted">policy · filter</span>
        </div>
        <div className={line(reached, denied && !reached)} />
        <div className="flex flex-col gap-1.5">
          {(["crm", "analytics"] as const).map((sv) => (
            <div key={sv} className={node(reached && server === sv)}>
              <span className="flex items-center gap-1">
                <Database className="h-3.5 w-3.5" aria-hidden />
                {sv === "crm" ? "Private CRM" : "Private Analytics"}
                {sv === "crm" && <KeyRound className={`h-3 w-3 ${secretUse ? "text-pending" : "text-muted"}`} aria-label="backend-held credential" />}
              </span>
            </div>
          ))}
        </div>
        <div className={line(task?.status === "COMPLETED")} />
        <div className={node(task?.status === "COMPLETED")}>
          <Sparkles className="h-4 w-4" aria-hidden />
          Model
          <span className="text-muted">sanitized result</span>
        </div>
      </div>
      {secretUse && (
        <p className="mt-2 text-xs text-pending">
          The CRM used its backend-held synthetic credential; only <code>connected: true</code> left the gateway.
        </p>
      )}
    </div>
  );
}
