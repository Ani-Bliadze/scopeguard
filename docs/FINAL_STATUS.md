# ScopeGuard final status (17 Oct 2026)

Every number below comes from commands run in this repository. The evidence files are `docs/demo_results.json` (deterministic run) and `docs/demo_results_live.json` (live `gpt-4.1-mini` run), plus the test runs listed below.

## Milestones

| Milestone | Status | Evidence |
|---|---|---|
| M0 Tooling and isolation | Done | Nested git repo (top-level = project dir); pinned deps with hashed `requirements*.lock`; `pip check` clean; MCP v2 imports test; PowerPoint render smoke (VBScript COM) |
| M1 Data and private MCP | Done | 5,000 customers / 10,000 sales, deterministic digest; CRM and Analytics MCP servers over real stdio; aggregates equal independent SQL |
| M2 Enforced gateway | Done | Real HTTP→gateway→stdio round-trip; denied calls cause 0 upstream dispatches; contaminated outputs fail closed |
| M3 Planning and measurement | Done | Deterministic and OpenAI planners; deterministic ranking; separate worker process; instrumented model boundary |
| M4 Dashboard | Done | React dashboard, 3 P0 scenarios + P1 approval + probes; 7/7 Playwright E2E incl. 1366×768, 1920×1080, 390×844 |
| M5 Proof and evidence | Done | Sanitized evidence (deterministic + live); `scripts.check_evidence` passes; screenshots in `docs/screenshots/` |
| M6 Deck and visual QA | Done | 8-slide editable PPTX + PDF; rendered with PowerPoint; every slide and the montage visually reviewed over 3 rounds; `pitch/check_deck.py` passes |

## Tests (final run)

| Suite | Result |
|---|---|
| `ruff check backend mcp_servers scripts tests pitch/*.py` | All checks passed |
| `pytest tests` (unit + integration + security, offline) | **137 passed, 0 failed** |
| The 12 named P0 acceptance tests (`-k` on the 12 IDs from PLAN §9) | **26 passed** (12 tests; parametrized cases expand to 26) |
| `npm run typecheck` / `npm run build` | 0 errors / built |
| `npx playwright test` (browser E2E) | **7 passed, 0 failed** |
| `scripts.check_evidence` | Passed |
| `pitch/check_deck.py` | Passed |

## Key demo results (deterministic run, fresh reset)

**A · Safe replan, "Summarize September sales by region."**
- 3 candidates were proposed.
- `crm.get_customers` was denied before execution. It had requested 5,000 customer rows and 10,000 personal values (both estimates).
- `analytics.get_transactions` was denied.
- `analytics.get_sales_summary` was selected and executed over MCP `2026-07-28`.
- The model received **0 customer records, 0 personal values and 4 aggregate rows** (356 bytes).
- The totals equal independent SQL.

**B1 · Secret request.** `HARD_DENY_SECRET_DISCLOSURE` with 0 planner/model calls and 0 upstream dispatches.

**B2 · Backend credential use.** The CRM verified its synthetic credential. The model received only `{"connector":"crm","connected":true,…}`.

**C · Scoped approval (P1).** The approval covers one tool, one field and customer 105, with a 120 s TTL and single use.
- Approving delivers exactly 1 personal value.
- Reuse returns HTTP 409.
- The deny path returns `APPROVAL_DENIED`.

**D · Compromised-agent probes (P1 variant, scripted).** 4 of 4 tampered calls were denied (`TOOL_NOT_ALLOWED_FOR_TASK`, `UNKNOWN_TOOL`, `INVALID_ARGUMENTS`, `STEP_NOT_IN_GRANT`), with 0 prohibited upstream dispatches.

**Scans.** The canary appeared 0 times in 7 recorded model-bound payloads. Audit holds 72 events, none containing canary values, emails or personal IDs.

**Live run (`gpt-4.1-mini`).** The planner proposed 3 candidates with the same strategies. The aggregate plan was selected, the live answer passed numeric verification, and the model again received 0 personal values with 0 canary hits.

## Launch commands

```powershell
.\.venv\Scripts\python.exe -m scripts.reset_demo
npm run build
.\.venv\Scripts\python.exe -m scripts.run_local --mode live          # or --mode deterministic (offline)
# open http://127.0.0.1:8000
```

Full fresh-clone setup and evidence/deck regeneration: [README.md](../README.md) and [pitch/README.md](../pitch/README.md).

## Deliverable paths

| Deliverable | Path |
|---|---|
| Public website | https://scopeguard-ai-shield.lovable.app/ (built with Lovable from `docs/LOVABLE_SITE_PROMPT.md`) |
| Code | https://github.com/Ani-Bliadze/scopeguard (CI passing) |
| Deck | `pitch/ScopeGuard_Pitch.pptx` (+ `pitch/ScopeGuard_Pitch.pdf`) |
| Deck source | `pitch/build_deck.js` |
| Pitch script | `pitch/PITCH_SCRIPT.md` |
| Rendered QA | `pitch/qa/slide-01..08.png`, `pitch/qa/montage.png`, `pitch/qa/review.json`, `pitch/qa/layout-report.json` |
| Demo script and results | `docs/DEMO_SCRIPT.md`, `docs/DEMO_RESULTS.md`, `docs/DEMO_RESULTS_LIVE.md` |
| Limitations | `docs/SECURITY_LIMITATIONS.md` |

## Omissions, deviations and blockers (honest list)

**Deviations from the plan**
- **LLM provider.** The build plan specified Gemini. The user supplied an OpenAI key, so OpenAI `gpt-4.1-mini` is the live provider. The Gemini adapter exists but was not exercised (no key).
- **P1 prompt-injection note scenario.** Not built as a note-reading task. It was replaced by scripted compromised-agent probes. The injection-looking note is seeded but no tool returns notes.
- **PowerPoint rendering path.** PowerShell's typed interop is broken on this machine, so rendering uses VBScript late binding.

**Not done**
- **Docker / Presidio / GIF video:** not done. Docker engine was unavailable, and Presidio and video were optional.

**P2 roadmap (not attempted)**
- Production identity/OIDC, a generic MCP proxy, policy-as-code administration, SIEM export, tenant isolation.

**Security notes**
- Demo sessions are not production authentication.
- Same-user host compromise is out of scope.
- See `docs/SECURITY_LIMITATIONS.md`.

**Credential hygiene**
- The OpenAI key lives only in the gitignored `.env` and is not in any tracked file (checked by `scripts.check_release`).
- It was shared in chat during the build, so rotating it after the event is advisable.
