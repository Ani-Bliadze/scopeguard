import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { ApprovalDrawer } from "./components/ApprovalDrawer";
import { DecisionTimeline } from "./components/DecisionTimeline";
import { ExposureMetrics } from "./components/ExposureMetrics";
import { Header } from "./components/Header";
import { PlanComparison } from "./components/PlanComparison";
import { PolicyDrawer } from "./components/PolicyDrawer";
import { ResultPanel } from "./components/ResultPanel";
import { DataPath, StageTracker } from "./components/StageTracker";
import { TaskComposer } from "./components/TaskComposer";
import type { AuditEvent, Health, Persona, PolicySummary, SessionInfo, Task } from "./types";

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [policy, setPolicy] = useState<PolicySummary | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPolicy, setShowPolicy] = useState(false);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<number | null>(null);

  const ensureSession = useCallback(async (persona: Persona = "sales_analyst") => {
    const existing = await api.session();
    const s = existing ?? (await api.persona(persona));
    setSession(s);
    return s;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setHealth(await api.health());
        await ensureSession();
        setPolicy(await api.policy());
      } catch (e) {
        setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "ScopeGuard backend is not reachable on this origin.");
      }
    })();
  }, [ensureSession]);

  // Poll the server-owned task state and redacted events while a task is active.
  useEffect(() => {
    if (!taskId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const [t, ev] = await Promise.all([api.task(taskId), api.events(taskId)]);
        if (stopped) return;
        setTask(t);
        setEvents(ev.events);
        if (t.terminal) {
          stopped = true;
          if (pollRef.current) window.clearInterval(pollRef.current);
        }
      } catch (e) {
        if (e instanceof ApiError && (e.status === 404 || e.status === 401)) {
          stopped = true;
          if (pollRef.current) window.clearInterval(pollRef.current);
        }
      }
    };
    tick();
    pollRef.current = window.setInterval(tick, 500);
    return () => {
      stopped = true;
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [taskId]);

  const busy = starting || (!!task && !task.terminal);
  const busyReason = busy
    ? task?.status === "AWAITING_APPROVAL"
      ? "Waiting for your approval decision."
      : "A task is running; controls unlock when it finishes."
    : null;

  const switchPersona = async (p: Persona) => {
    setError(null);
    const s = await api.persona(p);
    setSession(s);
    setTask(null);
    setEvents([]);
    setTaskId(null);
  };

  const launch = async (fn: () => Promise<{ task_id: string }>, persona?: Persona) => {
    setError(null);
    setStarting(true);
    try {
      if (persona && session?.persona !== persona) await switchPersona(persona);
      setTask(null);
      setEvents([]);
      const { task_id } = await fn();
      setTaskId(task_id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await ensureSession(persona ?? session?.persona ?? "sales_analyst");
        setError("Your demo session was reset. Please run the scenario again.");
      } else setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "Request failed.");
    } finally {
      setStarting(false);
    }
  };

  const reset = async () => {
    setError(null);
    try {
      await api.reset();
      const s = await api.persona(session?.persona ?? "sales_analyst");
      setSession(s);
      setTask(null);
      setEvents([]);
      setTaskId(null);
      setHealth(await api.health());
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "Reset failed.");
    }
  };

  const toggleAccess = async (paused: boolean) => {
    await api.access(paused);
    setSession(await api.session());
  };

  const classOf = useMemo(() => {
    const map = new Map<string, string>();
    policy?.tools.forEach((t) => Object.entries(t.fields).forEach(([f, c]) => map.set(`${t.tool_id}:${f}`, c)));
    return (tool: string, field: string) => map.get(`${tool}:${field}`) ?? "INTERNAL";
  }, [policy]);

  const t0 = events.length ? events[0].ts : null;

  return (
    <div className="flex h-full min-h-screen flex-col">
      <Header
        session={session}
        health={health}
        busy={busy}
        onPersona={switchPersona}
        onPolicy={() => setShowPolicy(true)}
        onReset={reset}
      />
      {session?.access_paused && (
        <div className="bg-pending/15 px-5 py-1.5 text-sm text-pending">Data access is paused for this session (Policy → Resume).</div>
      )}
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[340px_1fr]">
        <aside className="flex flex-col gap-4">
          <TaskComposer
            busy={busy}
            busyReason={busyReason}
            persona={session?.persona ?? "sales_analyst"}
            onRun={(prompt, persona) => launch(() => api.startTask(prompt), persona)}
            onProbe={(probe) => launch(() => api.startProbe(probe), "sales_analyst")}
          />
          {health && (
            <div className="card p-3 text-xs text-muted">
              <div className="mb-1 font-semibold uppercase tracking-wider">System</div>
              <div>Fixture: {health.fixture?.customers.toLocaleString()} synthetic customers · {health.fixture?.sales.toLocaleString()} sales</div>
              <div>
                Private MCP upstreams (stdio):{" "}
                {Object.entries(health.upstreams).map(([k, v]) => (
                  <span key={k} className={v ? "text-allow" : "text-deny"}>{k} {v ? "up" : "down"} </span>
                ))}
              </div>
              <div>Policy digest {health.config_digest}</div>
              <div className="mt-1 text-[11px]">{session?.label}</div>
            </div>
          )}
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <StageTracker task={task} />
          <ExposureMetrics task={task} />
          <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
              <ResultPanel task={task} error={error} />
              <DataPath task={task} />
            </div>
            <div className="relative h-[480px] xl:h-auto xl:min-h-[420px]">
              <div className="absolute inset-0 flex flex-col">
                <DecisionTimeline events={events} t0={t0} />
              </div>
            </div>
          </div>
          <PlanComparison task={task} classOf={classOf} />
        </div>
      </main>

      {task?.status === "AWAITING_APPROVAL" && task.approval && (
        <ApprovalDrawer
          approval={task.approval}
          onDecide={async (d) => {
            try {
              await api.decide(task.approval!.approval_id, d);
            } catch (e) {
              setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "Decision failed.");
            }
          }}
        />
      )}
      {showPolicy && (
        <PolicyDrawer policy={policy} session={session} onClose={() => setShowPolicy(false)} onToggleAccess={toggleAccess} />
      )}
    </div>
  );
}
