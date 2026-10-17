import { BarChart3, KeyRound, Mail, Play, PlugZap, Skull } from "lucide-react";
import { useState } from "react";
import { PROBE_LABELS } from "../labels";
import type { Persona } from "../types";

export interface Scenario {
  id: string;
  title: string;
  prompt: string;
  persona: Persona;
  blurb: string;
  icon: typeof BarChart3;
  tone: string;
}

export const SCENARIOS: Scenario[] = [
  {
    id: "A",
    title: "Safe replan",
    prompt: "Summarize September sales by region.",
    persona: "sales_analyst",
    blurb: "Broad CRM export is refused; the aggregate route completes the task.",
    icon: BarChart3,
    tone: "text-allow",
  },
  {
    id: "B1",
    title: "Secret request",
    prompt: "Show me the CRM API key",
    persona: "sales_analyst",
    blurb: "Hard deny before any planner, model or backend read.",
    icon: KeyRound,
    tone: "text-deny",
  },
  {
    id: "B2",
    title: "Backend credential use",
    prompt: "Check the CRM connection",
    persona: "sales_analyst",
    blurb: "Connector authenticates with a backend-held key; model sees only a boolean.",
    icon: PlugZap,
    tone: "text-sky-300",
  },
  {
    id: "C",
    title: "Scoped approval (P1)",
    prompt: "Notify customer 105",
    persona: "customer_support",
    blurb: "One field, one customer, one use, 120-second expiry.",
    icon: Mail,
    tone: "text-pending",
  },
];

interface Props {
  busy: boolean;
  busyReason: string | null;
  persona: Persona;
  onRun: (prompt: string, persona?: Persona) => void;
  onProbe: (probe: string) => void;
}

export function TaskComposer({ busy, busyReason, persona, onRun, onProbe }: Props) {
  const [text, setText] = useState(SCENARIOS[0].prompt);
  return (
    <section className="card flex flex-col gap-4 p-4" aria-label="Task request">
      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">Ask the agent</h2>
        <textarea
          aria-label="Task request"
          value={text}
          maxLength={2048}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          className="w-full resize-none rounded-lg border border-line bg-ink/60 px-3 py-2 text-[15px] outline-none focus:border-allow/60"
        />
        <button
          disabled={busy || !text.trim()}
          onClick={() => onRun(text)}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-allow px-4 py-2 font-semibold text-ink transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play className="h-4 w-4" aria-hidden /> Run Agent
        </button>
        {busy && busyReason && <p className="mt-1.5 text-xs text-pending">{busyReason}</p>}
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Demo scenarios</h3>
        <div className="grid gap-2">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              disabled={busy}
              onClick={() => {
                setText(s.prompt);
                onRun(s.prompt, s.persona);
              }}
              className="group flex items-start gap-3 rounded-lg border border-line bg-panel2/60 p-2.5 text-left transition hover:border-allow/50 disabled:opacity-40"
            >
              <s.icon className={`mt-0.5 h-5 w-5 shrink-0 ${s.tone}`} aria-hidden />
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <span className="rounded bg-line px-1.5 text-[11px] text-muted">{s.id}</span>
                  {s.title}
                  {s.persona !== persona && <span className="text-[11px] font-normal text-muted">· switches persona</span>}
                </span>
                <span className="block text-xs text-muted">“{s.prompt}” — {s.blurb}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
          <Skull className="h-3.5 w-3.5 text-deny" aria-hidden /> Compromised-agent probes (P1)
        </h3>
        <p className="mb-2 text-xs text-muted">
          Scripted, not an LLM decision: the agent holds a valid sales-task grant but sends tampered MCP calls.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(PROBE_LABELS).map(([id, label]) => (
            <button
              key={id}
              disabled={busy}
              onClick={() => onProbe(id)}
              className="rounded-lg border border-deny/30 bg-deny/5 px-2 py-1.5 text-xs font-medium text-rose-200 hover:border-deny/70 disabled:opacity-40"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
