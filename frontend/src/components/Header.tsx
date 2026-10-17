import { Bot, Cpu, RotateCcw, ScrollText, ShieldCheck, UserRound } from "lucide-react";
import type { Health, Persona, SessionInfo } from "../types";

interface Props {
  session: SessionInfo | null;
  health: Health | null;
  busy: boolean;
  onPersona: (p: Persona) => void;
  onPolicy: () => void;
  onReset: () => void;
}

export function Header({ session, health, busy, onPersona, onPolicy, onReset }: Props) {
  const live = health && health.planner_mode !== "deterministic";
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line/80 bg-ink/70 px-5 py-3 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-allow/15 ring-1 ring-allow/40">
          <ShieldCheck className="h-6 w-6 text-allow" aria-hidden />
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight">ScopeGuard</div>
          <div className="text-xs text-muted">Privacy-aware AI agent gateway · Agent Consent Studio</div>
        </div>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-sm">
          <UserRound className="h-4 w-4 text-muted" aria-hidden />
          <span className="text-muted">Demo persona</span>
          <select
            aria-label="Demo persona"
            className="bg-transparent font-medium text-text outline-none"
            value={session?.persona ?? "sales_analyst"}
            disabled={busy}
            onChange={(e) => onPersona(e.target.value as Persona)}
          >
            <option value="sales_analyst">Sales analyst</option>
            <option value="customer_support">Customer support</option>
          </select>
        </label>

        <span
          title={live ? `Planner and answer use ${health?.live_model}` : "Offline template planner and deterministic answer adapter"}
          className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium ring-1 ${
            live ? "bg-allow/10 text-allow ring-allow/40" : "bg-pending/10 text-pending ring-pending/40"
          }`}
        >
          {live ? <Bot className="h-4 w-4" aria-hidden /> : <Cpu className="h-4 w-4" aria-hidden />}
          {health ? (live ? `Live LLM · ${health.live_model}` : "Deterministic demo") : "…"}
        </span>

        <button
          onClick={onPolicy}
          className="flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-sm hover:border-allow/60"
        >
          <ScrollText className="h-4 w-4" aria-hidden /> Policy
        </button>
        <button
          onClick={onReset}
          disabled={busy}
          title={busy ? "Unavailable while a task is running" : "Reset synthetic data, sessions, grants and audit"}
          className="flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-sm hover:border-pending/60 disabled:opacity-40"
        >
          <RotateCcw className="h-4 w-4" aria-hidden /> Reset demo
        </button>
      </div>
    </header>
  );
}
