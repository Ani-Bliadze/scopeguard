import { KeyRound, Lock, PauseCircle, PlayCircle, X } from "lucide-react";
import { CLASS_STYLE } from "../labels";
import type { PolicySummary, SessionInfo } from "../types";

interface Props {
  policy: PolicySummary | null;
  session: SessionInfo | null;
  onClose: () => void;
  onToggleAccess: (paused: boolean) => void;
}

export function PolicyDrawer({ policy, session, onClose, onToggleAccess }: Props) {
  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="scroll-thin h-full w-full max-w-xl overflow-y-auto border-l border-line bg-panel p-5"
        onClick={(e) => e.stopPropagation()}
        aria-label="Enterprise policy"
      >
        <div className="flex items-center gap-2">
          <Lock className="h-5 w-5 text-allow" aria-hidden />
          <h2 className="text-lg font-semibold">Enterprise policy (read-only)</h2>
          <button onClick={onClose} className="ml-auto rounded p-1 hover:bg-line" aria-label="Close policy">
            <X className="h-5 w-5" />
          </button>
        </div>
        {!policy ? (
          <p className="mt-4 text-sm text-muted">Loading…</p>
        ) : (
          <div className="mt-3 space-y-4 text-sm">
            <p className="text-xs text-muted">
              Policy {policy.policy_version} · registry {policy.registry_version} · default decision <b>{policy.default_decision}</b>. Administrator-owned
              files; the model, agent and browser cannot change them.
            </p>
            <div className="rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 p-3">
              <div className="flex items-center gap-1.5 font-semibold text-fuchsia-200">
                <KeyRound className="h-4 w-4" aria-hidden /> Hard rule
              </div>
              <p className="mt-1">{policy.hard_rules}</p>
            </div>

            <div className="rounded-lg border border-line p-3">
              <div className="mb-1 font-semibold">Session data access</div>
              <p className="text-xs text-muted">Pausing stops new tasks and revokes active grants for this session. It cannot widen permissions.</p>
              <button
                onClick={() => onToggleAccess(!session?.access_paused)}
                className={`mt-2 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ${
                  session?.access_paused ? "bg-pending/15 text-pending ring-pending/40" : "bg-allow/10 text-allow ring-allow/40"
                }`}
              >
                {session?.access_paused ? <PlayCircle className="h-4 w-4" /> : <PauseCircle className="h-4 w-4" />}
                {session?.access_paused ? "Resume data access" : "Pause data access"}
              </button>
            </div>

            <div>
              <h3 className="mb-1 font-semibold">Roles</h3>
              {Object.entries(policy.roles).map(([r, v]) => (
                <div key={r} className="mb-1.5 rounded-lg bg-ink/50 p-2">
                  <div className="font-mono text-xs text-sky-200">{r}</div>
                  <div className="text-xs">{v.description}</div>
                  <div className="text-[11px] text-muted">tasks: {v.tasks.join(", ")}</div>
                </div>
              ))}
            </div>

            <div>
              <h3 className="mb-1 font-semibold">Registered MCP tools (the only protected surface)</h3>
              {policy.tools.map((t) => (
                <div key={t.tool_id} className="mb-1.5 rounded-lg bg-ink/50 p-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-sky-200">{t.tool_id}</span>
                    <span className="text-[11px] text-muted">max {t.max_rows} rows · approval {t.approval_mode}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(t.fields).map(([f, c]) => (
                      <span key={f} className={`chip ${CLASS_STYLE[c]}`}>{f}: {c}</span>
                    ))}
                    {Object.entries(t.backend_secrets_used).map(([f, c]) => (
                      <span key={f} className={`chip ${CLASS_STYLE[c]}`} title="used by the backend connector, never returned">
                        <KeyRound className="h-3 w-3" /> {f}: {c} (backend-only)
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted">Not served by the gateway: {policy.unsupported_surfaces.join(", ")}.</p>
          </div>
        )}
      </aside>
    </div>
  );
}
