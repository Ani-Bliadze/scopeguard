import { Check, Clock, ShieldQuestion, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Approval } from "../types";

export function ApprovalDrawer({ approval, onDecide }: { approval: Approval; onDecide: (d: "approve" | "deny") => void }) {
  const [now, setNow] = useState(Date.now() / 1000);
  const [sending, setSending] = useState(false);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.round(approval.expires_at - now));
  const decide = (d: "approve" | "deny") => {
    setSending(true);
    onDecide(d);
  };
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="approval-title">
      <div className="card w-full max-w-lg border-pending/50 p-5 shadow-2xl">
        <div className="flex items-center gap-2">
          <ShieldQuestion className="h-6 w-6 text-pending" aria-hidden />
          <h2 id="approval-title" className="text-lg font-semibold">Scoped access request</h2>
          <span className="ml-auto flex items-center gap-1 text-sm text-pending tabular-nums">
            <Clock className="h-4 w-4" aria-hidden /> {left}s
          </span>
        </div>
        <p className="mt-1 text-sm text-muted">
          The agent asks to read <b className="text-text">one field</b> for <b className="text-text">one customer</b>. Approval is bound to
          this task, resource, field and principal; it is single-use and cannot override enterprise policy.
        </p>
        <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1.5 rounded-lg bg-ink/60 p-3 text-sm">
          <dt className="text-muted">Tool</dt>
          <dd className="font-mono text-sky-200">{approval.tool_id}</dd>
          <dt className="text-muted">Field</dt>
          <dd><span className="chip bg-rose-500/15 text-rose-200 ring-rose-400/40">{approval.fields.join(", ")} · PERSONAL</span></dd>
          <dt className="text-muted">Resource</dt>
          <dd>customer #{String(approval.resource.customer_id)}</dd>
          <dt className="text-muted">Purpose</dt>
          <dd>{approval.purpose}</dd>
          <dt className="text-muted">Task ID</dt>
          <dd className="font-mono text-xs">{approval.task_id}</dd>
          <dt className="text-muted">Expires</dt>
          <dd>{new Date(approval.expires_at * 1000).toLocaleTimeString()} · {approval.single_use ? "single use" : "reusable"}</dd>
        </dl>
        <div className="mt-4 flex gap-2">
          <button
            disabled={sending || left === 0}
            onClick={() => decide("approve")}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-pending px-3 py-2 font-semibold text-ink disabled:opacity-40"
          >
            <Check className="h-4 w-4" aria-hidden /> Approve once
          </button>
          <button
            disabled={sending}
            onClick={() => decide("deny")}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-deny/60 px-3 py-2 font-semibold text-deny disabled:opacity-40"
          >
            <X className="h-4 w-4" aria-hidden /> Deny
          </button>
        </div>
        <p className="mt-2 text-[11px] text-muted">No email is sent: ScopeGuard registers no email-sending or egress tool.</p>
      </div>
    </div>
  );
}
