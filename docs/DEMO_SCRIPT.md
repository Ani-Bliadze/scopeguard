# Live demo script (about 60 seconds, plus optional extras)

## Setup (before going on stage)

```powershell
.\.venv\Scripts\python.exe -m scripts.reset_demo
.\.venv\Scripts\python.exe -m scripts.run_local --mode live     # or --mode deterministic (offline)
```

Open `http://127.0.0.1:8000` and zoom the browser to 100%. Check the header badge:

- `Live LLM · gpt-4.1-mini` means live mode.
- `Deterministic demo` means the offline fallback. Both modes run the same enforcement.

## Click path

| Time | Action | What to say | What judges should see |
|---|---|---|---|
| 0:00 | Click **A · Safe replan** | "Ask for September sales by region." | The three stages turn green |
| 0:10 | Point at the candidate cards | "The planner proposed a full customer export, which asks for 5,000 customer rows. Policy denied it and it never ran. The aggregate route was selected instead." | `DENIED · NOT EXECUTED` on the broad candidates, `SELECTED` on the aggregate |
| 0:25 | Point at the metric tiles | "Customer records exposed to the model: 0. Personal values: 0. The task was answered." | `5,000` (estimate, never executed), `0`, `0`, `Answered` |
| 0:35 | Click **B1 · Secret request** | "Ask for the API key." | Hard deny before any planner, model or backend read |
| 0:45 | Click **B2 · Backend credential use** | "The backend may *use* the key. Only `connected: true` comes back." | The key icon on Private CRM, and only boolean status JSON |
| 0:55 | Click **Broad CRM export** under probes | "Even a compromised agent that holds a valid grant is stopped at the gateway." | `TOOL_NOT_ALLOWED_FOR_TASK` and `Prohibited upstream dispatches: 0` |

## Optional extras

**Scoped approval (C).** Click C. The dialog shows the tool, the field, customer #105, the purpose, the task ID and a 120 s countdown. Click **Approve once**. The run completes with exactly 1 personal value, and the email is masked in the browser.

**Policy drawer.** Shows the hard rule, the field classifications and the backend-only `crm_api_key` (`RESTRICTED_SECRET`). It also has a pause/resume control for data access.

**Export audit.** Downloads redacted JSON: names, codes and counts only.

## Fallbacks

- If the live LLM is slow or unavailable, the run falls back to the deterministic planner and answer adapter automatically. The UI labels the fallback and gives the reason. Alternatively, restart with `--mode deterministic`.
- If the laptop or network fails, use the screenshots in `docs/screenshots/` (deterministic) and `docs/screenshots/live/` (live). Say clearly that they are screenshots.
