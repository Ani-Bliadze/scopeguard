import { Ban, CheckCircle2, Hourglass } from "lucide-react";
import { CLASS_STYLE, fmtInt, reason } from "../labels";
import type { Candidate, Task } from "../types";

function Decision({ c }: { c: Candidate }) {
  if (c.selected && c.decision === "ALLOW")
    return (
      <span className="chip bg-allow/15 text-allow ring-allow/40">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> SELECTED
      </span>
    );
  if (c.decision === "APPROVAL_REQUIRED")
    return (
      <span className="chip bg-pending/15 text-pending ring-pending/40">
        <Hourglass className="h-3.5 w-3.5" aria-hidden /> {c.selected ? "SELECTED · NEEDS APPROVAL" : "NEEDS APPROVAL"}
      </span>
    );
  return (
    <span className="chip bg-deny/15 text-deny ring-deny/40">
      <Ban className="h-3.5 w-3.5" aria-hidden /> {c.valid ? "DENIED · NOT EXECUTED" : "INVALID · NOT EXECUTED"}
    </span>
  );
}

function fieldName(f: string) {
  return f.split(":").pop() ?? f;
}

type ClassOf = (tool: string, field: string) => string;

function CandidateCard({ c, classOf }: { c: Candidate; classOf: ClassOf }) {
  const e = c.exposure;
  const border = c.selected ? "border-allow/60" : c.decision === "DENY" ? "border-deny/40" : "border-pending/40";
  return (
    <article className={`flex min-w-0 flex-col gap-2 rounded-xl border bg-panel2/60 p-3 ${border}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted">
          Candidate <b className="text-text">{c.candidate_id}</b> · {c.origin === "deterministic_template" ? "template planner" : c.origin}
          {c.self_reported_risk && <span title="LLM self-reported; informational only"> · LLM says “{c.self_reported_risk}”</span>}
        </span>
        <Decision c={c} />
      </div>
      <code className="block truncate font-mono text-sm text-sky-200" title={c.tools.join(" → ")}>{c.tools.join(" → ")}</code>
      <p className="line-clamp-2 text-xs text-muted">{c.rationale}</p>
      {e && (
        <>
          <div className="flex flex-wrap gap-1">
            {e.requested_fields.map((f) => {
              const tool = f.split(":")[0];
              return (
                <span key={f} className={`chip ${CLASS_STYLE[classOf(tool, fieldName(f))] ?? CLASS_STYLE.INTERNAL}`} title={`${tool} · ${classOf(tool, fieldName(f))}`}>
                  {fieldName(f)}
                </span>
              );
            })}
          </div>
          <dl className="grid grid-cols-3 gap-1 text-center text-[11px]">
            <div className="rounded-md bg-ink/50 p-1">
              <dt className="text-muted">Rows requested</dt>
              <dd className="text-base font-semibold tabular-nums">
                {fmtInt(e.customer_rows_requested + e.transaction_rows_requested + e.aggregate_rows_expected)}
              </dd>
            </div>
            <div className="rounded-md bg-ink/50 p-1">
              <dt className="text-muted">Personal values</dt>
              <dd className={`text-base font-semibold tabular-nums ${e.personal_field_values_requested ? "text-deny" : "text-allow"}`}>
                {fmtInt(e.personal_field_values_requested)}
              </dd>
            </div>
            <div className="rounded-md bg-ink/50 p-1">
              <dt className="text-muted">Max class</dt>
              <dd className="text-[11px] font-semibold leading-tight break-all">{e.max_classification}</dd>
            </div>
          </dl>
        </>
      )}
      <ul className="text-xs">
        {c.reason_codes.map((r) => (
          <li key={r} className={r.startsWith("ALLOWED") ? "text-allow" : r === "APPROVAL_REQUIRED" ? "text-pending" : "text-rose-200"}>
            • {reason(r)}
          </li>
        ))}
      </ul>
    </article>
  );
}

export function PlanComparison({ task, classOf }: { task: Task | null; classOf: ClassOf }) {
  const cands = task?.candidates ?? [];
  return (
    <section className="card p-4" aria-label="Plan comparison">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Candidate plans vs. selected safe plan</h2>
        <span className="text-[11px] text-muted">
          Requested data shown for unexecuted candidates is an <b>estimate</b> from the trusted registry, not a disclosure.
        </span>
      </div>
      {cands.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
          {task?.terminal
            ? "No planner was invoked for this request (it stopped at input screening or was a scripted probe)."
            : "Run a task to see the planner's candidates and the policy engine's decisions."}
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[...cands]
            .sort((a, b) => Number(a.selected) - Number(b.selected))
            .map((c) => (
              <CandidateCard key={c.candidate_id} c={c} classOf={classOf} />
            ))}
        </div>
      )}
    </section>
  );
}
