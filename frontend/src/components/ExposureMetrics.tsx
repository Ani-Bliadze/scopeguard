import type { Task } from "../types";
import { fmtInt } from "../labels";

function Tile({ label, value, note, tone }: { label: string; value: string; note: string; tone: string }) {
  return (
    <div className="card flex min-w-0 flex-col justify-between p-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-muted" title={note}>{note}</div>
    </div>
  );
}

const num = (v: unknown) => (typeof v === "number" ? fmtInt(v) : "—");

export function ExposureMetrics({ task }: { task: Task | null }) {
  const m = task?.metrics ?? {};
  const done = !!task?.terminal;
  if (task?.kind === "probe") {
    return (
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="Measured exposure">
        <Tile label="Tampered MCP calls sent" value={done ? num(m.mcp_calls) : "—"} note="by the compromised agent worker" tone="text-text" />
        <Tile label="Denied at the gateway" value={done ? num(m.gateway_calls_denied) : "—"} note={(m.deny_reasons as string[] | undefined)?.join(", ") ?? "measured"} tone="text-deny" />
        <Tile label="Prohibited upstream dispatches" value={done ? num(m.prohibited_upstream_dispatches) : "—"} note="measured at the private MCP client" tone="text-allow" />
        <Tile label="Values sent to the model" value={done ? num(m.personal_field_values_returned_to_model) : "—"} note="probes never reach a model" tone="text-allow" />
      </div>
    );
  }
  const outcome = !task ? "—" : task.status === "COMPLETED" ? "Answered" : task.terminal ? "Blocked safely" : task.status === "AWAITING_APPROVAL" ? "Awaiting" : "Running";
  const outcomeTone = task?.status === "COMPLETED" ? "text-allow" : task?.terminal ? "text-deny" : "text-pending";
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="Measured exposure">
      <Tile
        label="Customer records requested by rejected plan"
        value={typeof m.risky_candidate_customer_rows_requested === "number" ? num(m.risky_candidate_customer_rows_requested) : "—"}
        note="requested / estimated — never executed"
        tone="text-pending"
      />
      <Tile
        label="Customer records exposed to model"
        value={done ? num(m.customer_rows_returned_to_model ?? 0) : "—"}
        note="measured at the model boundary"
        tone={(m.customer_rows_returned_to_model as number) > 0 ? "text-pending" : "text-allow"}
      />
      <Tile
        label="Personal values exposed to model"
        value={done ? num(m.personal_field_values_returned_to_model ?? 0) : "—"}
        note={(m.personal_field_values_returned_to_model as number) > 0 ? "approved field only (scoped approval)" : "measured at the model boundary"}
        tone={(m.personal_field_values_returned_to_model as number) > 0 ? "text-pending" : "text-allow"}
      />
      <Tile
        label="Task outcome"
        value={outcome}
        note={
          task?.status === "COMPLETED"
            ? `${num(m.aggregate_rows_returned_to_model)} aggregate rows · ${num(m.tool_result_bytes_model_bound)} B tool result`
            : task?.block?.code ?? "—"
        }
        tone={outcomeTone}
      />
    </div>
  );
}
