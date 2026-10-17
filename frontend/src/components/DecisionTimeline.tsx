import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { reason } from "../labels";
import type { AuditEvent } from "../types";

const GROUPS: Record<string, string[]> = {
  All: [],
  Planning: ["PLANNER_STARTED", "PLANNER_FALLBACK", "CANDIDATE_EVALUATED", "PLAN_SELECTED", "NO_SAFE_PLAN"],
  "MCP gateway": ["GRANT_MINTED", "MCP_REQUEST", "POLICY_DECISION", "UPSTREAM_DISPATCH", "OUTPUT_ACCEPTED", "OUTPUT_DENIED"],
  Model: ["MODEL_BOUND", "ANSWER_READY"],
  Denials: [],
};

function tone(e: AuditEvent) {
  if (e.decision === "DENY" || e.stage === "INPUT_DENIED" || e.stage === "OUTPUT_DENIED" || e.stage === "TASK_FAILED") return "bg-deny";
  if (e.decision === "APPROVAL_REQUIRED" || e.stage === "APPROVAL_REQUESTED" || e.stage === "PLANNER_FALLBACK") return "bg-pending";
  if (e.stage === "UPSTREAM_DISPATCH" || e.stage === "MCP_REQUEST") return "bg-sky-400";
  if (e.decision === "ALLOW" || e.stage === "TASK_COMPLETED" || e.stage === "PLAN_SELECTED" || e.stage === "OUTPUT_ACCEPTED") return "bg-allow";
  return "bg-slate-500";
}

export function DecisionTimeline({ events, t0 }: { events: AuditEvent[]; t0: number | null }) {
  const [group, setGroup] = useState("All");
  const shown = useMemo(() => {
    if (group === "All") return events;
    if (group === "Denials") return events.filter((e) => tone(e) === "bg-deny");
    return events.filter((e) => GROUPS[group].includes(e.stage));
  }, [events, group]);

  const download = async () => {
    const data = await api.auditExport();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "scopeguard-audit-redacted.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="card flex h-full min-h-0 flex-col p-4" aria-label="Decision timeline">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Access decision trace</h2>
        <span className="text-[11px] text-muted">redacted: names, classes, codes and counts — never values</span>
        <button onClick={download} className="ml-auto flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs hover:border-allow/60">
          <Download className="h-3.5 w-3.5" aria-hidden /> Export audit
        </button>
      </div>
      <div className="mb-2 flex flex-wrap gap-1" role="tablist">
        {Object.keys(GROUPS).map((g) => (
          <button
            key={g}
            role="tab"
            aria-selected={g === group}
            onClick={() => setGroup(g)}
            className={`rounded-md px-2 py-0.5 text-xs ${g === group ? "bg-allow/20 text-allow" : "text-muted hover:text-text"}`}
          >
            {g}
          </button>
        ))}
      </div>
      <ol className="scroll-thin min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {shown.length === 0 && <li className="text-sm text-muted">No events yet.</li>}
        {shown.map((e) => (
          <li key={e.seq} className="grid grid-cols-[52px_10px_1fr] items-start gap-2 text-xs">
            <span className="pt-0.5 text-right font-mono text-muted tabular-nums">
              +{t0 ? Math.max(0, Math.round((e.ts - t0) * 1000)) : 0}ms
            </span>
            <span className={`mt-1.5 h-2 w-2 rounded-full ${tone(e)}`} aria-hidden />
            <span className="min-w-0">
              <span className="font-mono font-semibold text-text">{e.stage}</span>
              {e.candidate_id && <span className="text-muted"> · cand {e.candidate_id}</span>}
              {e.tool_id && <span className="font-mono text-sky-200"> · {e.tool_id}</span>}
              {e.decision && <span className="text-muted"> · {e.decision}</span>}
              {e.reason_code && <span className="block text-muted">{e.reason_code} — {reason(e.reason_code)}</span>}
              {e.fields.length > 0 && <span className="block text-muted">fields: {e.fields.join(", ")}{e.classes.length ? ` · classes: ${e.classes.join(", ")}` : ""}</span>}
              {Object.keys(e.counts).length > 0 && (
                <span className="block text-muted">{Object.entries(e.counts).map(([k, v]) => `${k}=${v}`).join(" · ")}</span>
              )}
              {e.message && <span className="block text-muted/80">{e.message}</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
