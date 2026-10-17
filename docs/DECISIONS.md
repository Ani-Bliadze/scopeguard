# ScopeGuard implementation decisions

Recorded during the build (17 Oct 2026). `PLAN.md` remains the product contract; this file records the choices made while implementing `docs/CLAUDE_BUILD_PLAN.md`, including where the build deviated from it.

## Environment (observed)

| Item | Value |
|---|---|
| OS / shell | Windows 11, PowerShell + Git Bash |
| Python | project `.venv`, 3.13.5 (bare `python` is 3.10: always use `.venv\Scripts\python.exe`) |
| Node / npm | 24.16.0 / 11.13.0 |
| Git | Nested repo initialised at the project root (`git rev-parse --show-toplevel` = project dir); the parent home-directory repo is untouched |
| PowerPoint | 16.0, automation available via late-bound IDispatch (VBScript). The typed PowerShell interop fails with `TYPE_E_ELEMENTNOTFOUND` on this machine |

## Dependencies

The pins from the build plan were installed and resolved without conflict (`pip check` clean). Hashed lockfiles were generated: `requirements.lock` and `requirements-dev.lock`, both via `pip-tools 7.6.2`. JavaScript dependencies are exact pins in npm workspaces (`frontend`, `pitch`), with one root `package-lock.json`.

## MCP (official Python SDK `mcp==2.3.0`, v2 API)

- **Private upstreams:** `mcp.server.MCPServer` + `@server.tool(...)` + `run(transport="stdio")`.
- **Gateway:** low-level `mcp.server.Server` with `on_list_tools` / `on_call_tool` / `get_tool_input_schema`. It is mounted into FastAPI at `/mcp` through `streamable_http_app(streamable_http_path="/", json_response=True, stateless_http=True, max_request_body_size=32 KiB)`, and `session_manager.run()` is entered in the FastAPI lifespan.
- **Client:** `mcp.Client`. The worker uses `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(headers=bearer)))`, and the gateway uses `Client(stdio_client(StdioServerParameters(...), errlog=file))`.
- **Protocol:** the negotiated version observed at runtime is `2026-07-28` (modern, no initialize handshake).
- **`_meta` handling:** upstream results carry SDK metadata `_meta["io.modelcontextprotocol/serverInfo"]`. The output filter tolerates only keys in the `io.modelcontextprotocol/` namespace and never forwards them; any other `_meta` key fails closed.
- **Task ownership:** anyio task groups must be exited by the task that entered them, so `UpstreamManager` runs a single owner task. Reset signals that task to cycle the upstream processes.
- **Unsupported surfaces:** the gateway registers no resources, prompts or other handlers, so those methods return `Method not found`. This is covered by a test.

## LLM provider (deviation from the build plan)

The build plan named Gemini. The user supplied an **OpenAI** key during the build, so OpenAI is the default live provider. The OpenAI integration calls Chat Completions with strict `json_schema` output through plain `httpx`, which avoids adding an SDK dependency. It has no automatic tool calling and no retries.

- **Model:** chosen through `OPENAI_MODEL` in `.env`. It was set to `gpt-4.1-mini` after confirming with the key's `/v1/models` listing and a structured-output smoke test.
- **Gemini:** an adapter remains in `backend/planner/llm.py` (`google-genai`) for `GEMINI_API_KEY`/`GEMINI_MODEL`. It was **not exercised** because no Gemini key was available.
- **Fallback:** on any provider error, invalid JSON or too few candidates, the run switches to the deterministic template planner/answerer. The fallback is recorded per phase with a reason code and shown in the UI. It is never labeled "Live".
- **Answer verification:** live answers are checked against the authoritative table (dollar figures within 1%, every region named, no secret or unapproved personal patterns). If verification fails, the run discards the live text and shows the deterministic rendering with a label.

## Security design choices

- **Identity:** a demo persona is bound to an HttpOnly, SameSite=Strict cookie through a loopback-only endpoint. CSRF tokens protect mutations. This is not production authentication.
- **Execution grants:** each grant is a random bearer token, of which only the SHA-256 hash is stored. It is bound to the session, principal, task, run, combined config digest and the exact canonical step hashes. Steps are consumed atomically and never replenished.
- **Gateway check order:** HTTP gate (Host/Origin, body size, bearer → active grant) → registry lookup → strict Pydantic argument validation (no detail echo) → pure policy engine → step binding → single-use approval consumption → upstream call with a 5 s timeout and no retry → complete output filter → newly constructed result.
- **Output filter:** checks both MCP channels. Secret patterns in either channel reject the whole result, regardless of approval.
- **Model boundary:** every planner/answer call, including deterministic ones, is scanned and measured immediately before dispatch. Tests can turn on an in-memory recorder that captures exact payloads.
- **Agent worker:** a separate process (`python -m backend.agent.worker`) receives its bootstrap on stdin and gets an allowlisted environment (the SDK's safe default list). The gateway URL is validated against `^http://127\.0\.0\.1:\d+/mcp/$`.
- **Audit:** events carry field names, classes, reason codes and counts only. Every event is pattern-scanned before persistence. Storage is in memory plus `.runtime/audit.sqlite`.
- **Browser emails:** authorized synthetic emails (P1) are masked in every browser-facing response (`c•••105@example.com`).

## Scenario set

| Scenario | Description |
|---|---|
| P0 A | Sales by region (safe replan) |
| P0 B1 | Secret request hard-denied |
| P0 B2 | Backend credential use without exposure |
| P1 C | Scoped one-time approval for customer #105's email (TTL 120 s, single use) |
| P1 D (variant) | "Compromised agent" probes. A worker holding a valid sales grant sends tampered MCP calls (broad export, private secret tool, smuggled fields, replay). This shows runtime enforcement independent of the planner/model. It is scripted, not an LLM decision, and is labeled that way. The free-text prompt-injection *note* scenario was not built as a separate task. The injection-looking note is seeded on customer 105, but no P0/P1 tool returns notes. |
