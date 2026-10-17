import { AlertTriangle, Bot, CheckCircle2, Cpu, Loader2, ShieldAlert } from "lucide-react";
import { fmtInt, fmtUSD, INTENT_LABELS, PROBE_LABELS, reason } from "../labels";
import type { SalesRow, Task } from "../types";

function ModeLabel({ task }: { task: Task }) {
  const a = task.answer;
  if (!a.mode) return null;
  const live = a.mode !== "deterministic";
  return (
    <span className={`chip ${live ? "bg-allow/10 text-allow ring-allow/40" : "bg-pending/10 text-pending ring-pending/40"}`}>
      {live ? <Bot className="h-3.5 w-3.5" aria-hidden /> : <Cpu className="h-3.5 w-3.5" aria-hidden />}
      {live ? `Live answer · ${a.model}` : a.attempted ? `Deterministic fallback (${a.fallback_reason})` : "Deterministic demo answer"}
      {a.live_answer_discarded && " · live text failed verification, deterministic rendering shown"}
    </span>
  );
}

function SalesTable({ rows }: { rows: SalesRow[] }) {
  const max = Math.max(...rows.map((r) => r.value_cents), 1);
  const total = rows.reduce((s, r) => s + r.value_cents, 0);
  return (
    <div className="mt-3">
      <table className="w-full text-sm">
        <caption className="sr-only">September 2026 revenue by region</caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="py-1 font-medium">Region</th>
            <th className="py-1 font-medium">Revenue (synthetic USD)</th>
            <th className="py-1 text-right font-medium">Transactions</th>
          </tr>
        </thead>
        <tbody>
          {[...rows].sort((a, b) => b.value_cents - a.value_cents).map((r) => (
            <tr key={r.region} className="border-t border-line/60">
              <td className="py-1.5 font-medium">{r.region}</td>
              <td className="py-1.5">
                <div className="flex items-center gap-2">
                  <div className="h-2 rounded bg-allow/70" style={{ width: `${Math.max(8, (r.value_cents / max) * 160)}px` }} aria-hidden />
                  <span className="tabular-nums">{fmtUSD(r.value_cents)}</span>
                </div>
              </td>
              <td className="py-1.5 text-right tabular-nums">{fmtInt(r.transaction_count)}</td>
            </tr>
          ))}
          <tr className="border-t border-line text-muted">
            <td className="py-1.5">Total</td>
            <td className="py-1.5 tabular-nums">{fmtUSD(total)}</td>
            <td className="py-1.5 text-right tabular-nums">{fmtInt(rows.reduce((s, r) => s + r.transaction_count, 0))}</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-muted">Authoritative table = validated tool result delivered to the model (source of truth for the answer).</p>
    </div>
  );
}

export function ResultPanel({ task, error }: { task: Task | null; error: string | null }) {
  if (error)
    return (
      <section className="card flex items-start gap-3 border-deny/50 p-4" role="alert">
        <AlertTriangle className="h-5 w-5 text-deny" aria-hidden />
        <div className="text-sm">{error}</div>
      </section>
    );
  if (!task)
    return (
      <section className="card p-4 text-sm text-muted">
        <b className="text-text">Ready.</b> Pick a scenario on the left. Every value on this dashboard comes from the live run and its redacted audit trail.
      </section>
    );
  const title = task.kind === "probe" ? PROBE_LABELS[task.probe ?? ""] ?? "Probe" : INTENT_LABELS[task.intent ?? ""] ?? "Unsupported request";
  const done = task.status === "COMPLETED";
  const rows = (task.result?.data?.rows as SalesRow[] | undefined) ?? null;
  return (
    <section className="card p-4" aria-live="polite" aria-label="Result" data-testid="result" data-task-id={task.task_id} data-status={task.status} data-terminal={String(task.terminal)}>
      <div className="flex flex-wrap items-center gap-2">
        {done ? (
          <CheckCircle2 className="h-5 w-5 text-allow" aria-hidden />
        ) : task.terminal ? (
          <ShieldAlert className="h-5 w-5 text-deny" aria-hidden />
        ) : (
          <Loader2 className="h-5 w-5 animate-spin text-sky-300" aria-hidden />
        )}
        <h2 className="text-base font-semibold">{title}</h2>
        <span className="text-xs text-muted">· {task.status.replaceAll("_", " ").toLowerCase()} · {fmtInt(task.duration_ms)} ms</span>
        <span className="ml-auto"><ModeLabel task={task} /></span>
      </div>
      {task.planner.attempted && (
        <p className="mt-1 text-xs text-pending">
          Live planner unavailable ({task.planner.fallback_reason}); clearly labeled deterministic template planner used instead.
        </p>
      )}
      {task.block && (
        <div className={`mt-3 rounded-lg border p-3 text-sm ${task.status === "COMPLETED" ? "" : "border-deny/40 bg-deny/5"}`}>
          <div className="font-mono text-xs text-deny">{task.block.code}</div>
          <div className="mt-0.5">{task.block.message}</div>
          {task.kind === "probe" && task.execution.steps && (
            <ul className="mt-2 space-y-0.5 font-mono text-xs">
              {task.execution.steps.map((s, i) => (
                <li key={i} className={s.ok ? "text-allow" : "text-rose-200"}>
                  {s.ok ? "✓" : "✗"} tools/call {s.tool_id} → {s.ok ? "allowed (approved step)" : `${s.error_code} · ${reason(s.error_code)}`}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {task.result && (
        <>
          <p className="mt-3 whitespace-pre-wrap rounded-lg bg-ink/50 p-3 text-[15px] leading-relaxed">{task.result.answer_text}</p>
          {rows && <SalesTable rows={rows} />}
          {task.result.kind === "connection_status" && (
            <pre className="mt-3 rounded-lg bg-ink/60 p-2 font-mono text-xs text-sky-200">{JSON.stringify(task.result.data)}</pre>
          )}
          {task.result.kind === "customer_contact" && (
            <p className="mt-2 text-xs text-muted">Email masked in the browser; only the approved field for customer #105 reached the model, once.</p>
          )}
        </>
      )}
    </section>
  );
}
