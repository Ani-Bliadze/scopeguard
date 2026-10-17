# ScopeGuard: Agent Consent Studio

**A data firewall that lets AI agents finish tasks without reading data they don't need.**

![ScopeGuard dashboard, live LLM run of "Summarize September sales by region"](pitch/assets/demo-sales.png)

- **Problem.** An agent asked to *"Summarize September sales by region"* can reach for a broad CRM tool. That would show the model 5,000 customers' emails and IDs to produce four numbers.
- **Solution.** ScopeGuard sits between the agent and its MCP tools. An LLM proposes candidate plans. A deterministic policy engine rejects the broad ones and picks the lowest-exposure authorized plan that still answers the task. The gateway then enforces the selected scope on every MCP call and every tool result.
- **Proof.** In the measured run, the broad candidate asked for 5,000 customer rows and never ran. The task finished with **0 customer records and 0 personal values delivered to the model**: just 4 aggregate rows, with totals checked against independent SQL. A canary secret appears **0 times** in any model-bound payload. Source: [docs/DEMO_RESULTS.md](docs/DEMO_RESULTS.md).

> Synthetic, task-scoped local demo. This is not a universal safety guarantee, and it has no real CRM or bank connection. See [docs/SECURITY_LIMITATIONS.md](docs/SECURITY_LIMITATIONS.md).

## How this differs from a typical MCP approval gateway

| | Typical allow/deny gateway | ScopeGuard |
|---|---|---|
| Broad tool requested for a narrow task | Blocks it; the task fails | Blocks it, **replans** onto an authorized lower-exposure route, and completes the task |
| Who decides | Often the model, a prompt, or a per-call human click | A deterministic policy engine **outside** the LLM, re-checked on every call |
| What reaches the model | The whole tool result once a call is allowed | A newly built, schema-validated, projected result; both MCP channels are scanned |
| Backend secrets | Often handed to the agent or tool | Used only inside the private connector; the model gets `connected: true` |
| Evidence | Logs of calls | A measured model boundary (rows, personal values, bytes, canary hits) and a redacted audit |

## Quickstart (Windows / PowerShell, from a fresh clone)

Requirements: Python 3.13, Node 24 and npm. The build machine also had PowerPoint, which is needed only for rendering slides.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
npm ci
npx playwright install chromium            # needed for E2E tests and screenshots
copy .env.example .env                     # optional: set OPENAI_API_KEY / OPENAI_MODEL for live mode
.\.venv\Scripts\python.exe -m scripts.reset_demo
npm run build
.\.venv\Scripts\python.exe -m scripts.run_local --mode deterministic   # or --mode live
```

Open **http://127.0.0.1:8000**. The API docs are at `/docs`. The server listens on localhost only.

- **Deterministic mode** works fully offline. It uses a template planner and a deterministic answer adapter, and the UI is labeled "Deterministic demo".
- **Live mode** sends the canonical task and approved catalog to the planner, and the sanitized tool result to the answerer, using `OPENAI_MODEL`. This build was verified with `gpt-4.1-mini`. If the provider fails or returns invalid output, the run falls back to deterministic mode, and the UI shows the fallback and its reason.

## Tests, evidence and checks

```powershell
.\.venv\Scripts\python.exe -m ruff check backend mcp_servers scripts tests
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=.runtime/test-results.xml      # unit + integration + security (offline)
npm run typecheck; npm run build; npm run test:e2e                                     # browser E2E (starts its own server on :8123)
.\.venv\Scripts\python.exe -m scripts.run_demo_scenarios --mode deterministic --reset --output docs/demo_results.json
.\.venv\Scripts\python.exe -m scripts.run_demo_scenarios --mode live --output docs/demo_results_live.json   # needs a key
.\.venv\Scripts\python.exe -m scripts.check_evidence
npm run capture:demo -- --url http://127.0.0.1:8000                                    # with run_local running
.\.venv\Scripts\python.exe -m scripts.check_release
```

Test counts from the latest run are recorded in [docs/FINAL_STATUS.md](docs/FINAL_STATUS.md).

## Demo scenarios (buttons in the dashboard, or `scripts/run_demo_scenarios.py`)

| # | Prompt / action | What happens |
|---|---|---|
| **A** (P0) | "Summarize September sales by region." | Three candidates are proposed. The broad CRM export and the transaction rows are denied and **never executed**. `analytics.get_sales_summary` is selected. The result travels a real MCP round-trip (agent → gateway over HTTP, gateway → private Analytics over stdio). The model receives 4 aggregate rows and 0 personal values. |
| **B1** (P0) | "Show me the CRM API key" | `HARD_DENY_SECRET_DISCLOSURE` at input screening. No planner, model or backend read runs. |
| **B2** (P0) | "Check the CRM connection" | The private CRM verifies its backend-held synthetic credential. Only `{"connected": true}` leaves the gateway. |
| **C** (P1) | "Notify customer 105" (customer_support) | A scoped approval dialog appears for one tool, one field, one customer, one use, with a 120 s TTL. The deny, expiry and reuse paths fail closed. |
| **D** (P1 variant) | Compromised-agent probes | A worker holding a valid sales grant sends a broad export, a private secret tool name, smuggled fields, and a replay. All are denied at the gateway with **0 prohibited upstream dispatches**. The probes are scripted, not LLM-driven. |

## Architecture and trust boundaries

```text
Browser ──cookie+CSRF──► FastAPI control plane (trusted)
                           ├─ input screening → fixed supported intents (LLM never picks identity/intent)
                           ├─ planner: OpenAI (live) or template (deterministic) ── via model boundary
                           ├─ deterministic evaluator/ranker + pure policy engine (config/*.json, pinned schema digests)
                           └─ execution grant (hashed bearer bound to session/task/config/exact steps)
                                   │ stdin bootstrap
                                   ▼
                        Agent worker process (no DB, no creds, no provider key; one fixed URL)
                                   │ MCP Streamable HTTP  (127.0.0.1:8000/mcp/)
                                   ▼
                        ScopeGuard MCP gateway (low-level MCP Server, registered tools only)
                           authN grant → registry → strict args → policy → step binding → approval
                                   │ MCP stdio (no sockets)          ▲ output filter: both channels,
                                   ▼                                 │ schema, projection, scans, rebuild
                        Private CRM MCP  ·  Private Analytics MCP  (SQLite synthetic fixture; CRM holds canary key)
                                   ▲
                        Model boundary: exact content scanned + measured before every provider call
```

- **MCP:** official Python SDK `mcp==2.3.0` (v2 API). The negotiated protocol is `2026-07-28`.
- **Exposed tools** (the only protected surface): `crm.get_customers`, `analytics.get_transactions`, `analytics.get_sales_summary`, `crm.get_connection_status`, and `crm.get_customer_contact`. Policy denies the first two for the sales task.
- **Not served:** resources, prompts, sampling, roots, SQL, HTTP, email or egress tools. The test-only `get_internal_secret` exists only in a malicious test fixture and is unreachable through the facade.
- **Policy ownership:** `config/policy.json`, `config/tool_registry.json` and `config/tasks.json` are owned by the administrator. Tool schema fingerprints are pinned, and any drift fails readiness closed. Upstream tool descriptions are never used as policy.

More detail: [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/SECURITY_LIMITATIONS.md](docs/SECURITY_LIMITATIONS.md) · [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) · [PLAN.md](PLAN.md)

## Pitch deck

- `pitch/ScopeGuard_Pitch.pptx` is an editable 8-slide 16:9 deck generated by `pitch/build_deck.js` from `docs/demo_results.json`.
- `pitch/PITCH_SCRIPT.md` is the speaker script.
- Rendered QA images are in `pitch/qa/`.
- Regeneration steps are in [pitch/README.md](pitch/README.md).

## Repository layout

```text
backend/        app (API, orchestrator, sessions), gateway (MCP server, upstream, filter), policy, planner, agent worker, observability
mcp_servers/    private CRM and Analytics MCP servers (stdio) + SQL
config/         policy.json, tool_registry.json, tasks.json (admin-owned)
frontend/       React + Vite + Tailwind dashboard
tests/          unit, integration, security (pytest) and e2e (Playwright)
scripts/        reset, run_local, run_demo_scenarios, capture_demo, check_evidence, check_release, doctor
docs/           decisions, limitations, demo script/results, screenshots, final status
pitch/          deck source, deck, script, assets, QA renders
```

## Safety notes

- All data is synthetic: `Demo Customer 00001`, `@example.com` addresses and `TEST-PID-…` identifiers.
- The canary credential is regenerated at each reset into the ignored `.runtime/backend.env`. It is never shown, logged or committed.
- `.env` (your optional LLM key) is gitignored. Only the backend reads it. The agent worker, MCP servers, browser and audit never see it.
- Demo personas are **not** production authentication.
