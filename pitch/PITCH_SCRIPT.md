# ScopeGuard pitch script (3 min 40 s, 8 slides, live demo)

**Deck:** `pitch/ScopeGuard_Pitch.pptx` (also `pitch/ScopeGuard_Pitch.pdf`). Every slide has speaker notes.

**Numbers:** every figure comes from `docs/demo_results.json`, a deterministic run from a fresh reset. A matching live run with `gpt-4.1-mini` is in `docs/demo_results_live.json`. If you regenerate the evidence, rebuild the deck so the two stay in sync.

**Before you go on stage:**

```powershell
.\.venv\Scripts\python.exe -m scripts.reset_demo
.\.venv\Scripts\python.exe -m scripts.run_local --mode live      # offline: --mode deterministic
```

Open `http://127.0.0.1:8000` in a second window at 100% zoom. Check the header badge and the *System* card: both upstreams should show **up**.

---

## Slide 1 · Hook (0:00 to 0:15)

> "Your AI agent needs an answer, not your entire database. ScopeGuard is a data firewall that lets AI agents finish the job without reading data they don't need."

Point at the two cards. A broad plan asked for 5,000 customer records and was blocked before it ran. The model got 4 regional totals and 0 personal values.

*Transition:* "Here's how that happens in practice."

## Slide 2 · The problem (0:15 to 0:40)

> "Someone asks a simple question: September sales by region. The task needs four numbers. But the CRM tool on hand can return every customer, with email, personal ID and spend. That's 5,000 rows and 10,000 personal values, just to add them up."

Be careful with the wording: 5,000 is the size of the *synthetic demo fixture*, and the counts are what the plan *requested*. Nothing leaked, because the plan was never run.

## Slide 3 · The difference (0:40 to 1:05)

> "A typical gateway blocks this, and the task fails. ScopeGuard blocks it, replans, and completes the task."

Walk the three layers left to right:

1. Hard policy set by the admin, which the LLM can't change.
2. An LLM that only *proposes* plans.
3. Runtime enforcement on every MCP call and every result.

> "Security that helps the agent finish its job safely."

## Slide 4 · How it works (1:05 to 1:35)

> "The agent talks to exactly one thing: ScopeGuard's MCP server. Every call is checked again there, against server-owned state, whatever the planner chose."

Point at the CRM and the key:

> "The CRM *uses* its credential to authenticate. The model only ever sees `connected: true`. Using a secret is not the same as exposing it."

## Slide 5 · Plans compared (1:35 to 2:00)

> "Three candidate plans. A, the customer export: denied and never executed. B, raw transactions: more exposure than the task needs, so denied for this task. C, a SQL aggregate: selected and executed. The amber box shows estimates for plans that never ran. The teal box shows what was measured."

Selection is deterministic. The LLM's own risk scores are ignored.

## Slide 6 · Live demo (2:00 to 2:55)

Switch to the browser.

1. **Click "A · Safe replan".** While it runs (about 3 s offline, about 8–10 s live): "The planner is proposing candidates, and policy is evaluating them."
2. Point at the candidate cards: "Broad CRM export, *denied, not executed*. Aggregate, *selected*."
3. Point at the tiles: "5,000 requested, never executed. **0 customer records, 0 personal values** reached the model. Answered."
4. **Click "B1 · Secret request":** "Hard deny before any planner or model is called."
5. **Click "B2 · Backend credential use":** "The connector authenticated. The model sees one boolean."
6. *(If time allows)* **Click "Broad CRM export" under the probes:** "Even a compromised agent with a valid grant is stopped at the gateway. Zero upstream calls."

Switch back to the deck.

**Fallbacks:**

- **The LLM is slow or unavailable.** The app falls back to the deterministic planner automatically and labels it. Say so.
- **The laptop or network is dead.** Stay on slide 6. It shows a real screenshot of the running app. Say "this is a screenshot of the run". More screenshots are in `docs/screenshots/` (deterministic) and `docs/screenshots/live/`.

## Slide 7 · Evidence (2:55 to 3:20)

> "The answer was delivered. The extra data was not."

Read the chart: rose is what the rejected plan *asked for*, teal is what the model *received*, and teal is zero. Then the cards:

- 4 aggregate rows, matching independent SQL.
- 0 canary hits across every model-bound payload.
- 4 of 4 tampered calls denied.
- The test counts.

Read the footnote aloud: "Measured in a synthetic, task-scoped local demo, not a universal safety guarantee."

## Slide 8 · Close (3:20 to 3:40)

> "This is for teams putting MCP agents in front of real data: enterprise AI builders, banks, support and analytics teams. Next on the roadmap, none of it built yet: more connectors, verified approvals, production identity, and policy as code."

> **"Don't give agents more data. Give them a safer route."** Thank you. Happy to take questions.

The slide shows the website (https://scopeguard-ai-shield.lovable.app/) and the code (https://github.com/Ani-Bliadze/scopeguard). Leave it up during Q&A.

---

## Judge Q&A

**1. Why not just tell the LLM to be careful?**
Prompts are suggestions, and a model can be wrong or manipulated. ScopeGuard's authorization is deterministic code outside the model. It is re-checked on every MCP call, and every result is inspected before the model sees it. The test `test_policy_is_independent_of_planner` feeds in a planner that proposes only prohibited plans, and nothing executes. The compromised-agent probes show that a tampered call is denied at the gateway no matter what the model wanted.

**2. Why not just deny everything risky?**
Then the task fails and people route around the control. ScopeGuard denies the broad plan and finds an authorized, lower-exposure plan that still answers the question. Here, that is the SQL aggregate. If no safe plan exists, it reports `BLOCKED_NO_SAFE_PLAN` and does not widen permissions.

**3. Who approves the classifications and policies? Can they be trusted?**
An administrator owns three checked-in files: `config/policy.json`, `config/tool_registry.json` and `config/tasks.json`. Tool schemas are pinned by SHA-256, so any drift fails readiness closed. Upstream tool descriptions are never used as policy. Changing a description in a test does not change any decision.

**4. What exactly does the model see?**
For the sales task, one tool message with 4 aggregate rows (356 bytes): region, value in cents and transaction count. For the connection check, `{"connector":"crm","connected":true,…}`. Every provider call goes through an instrumented boundary that scans and measures the exact content. Across the recorded run there were 0 canary hits, 0 personal IDs and 0 emails outside the approved P1 task.

**5. How is this different from an ordinary API gateway?**
It understands *task scope*, not just endpoints:

- It picks among candidate plans by data exposure.
- It binds each grant to the exact approved MCP steps.
- It validates both MCP result channels and rebuilds the result before the model sees it.
- It tells apart a secret being *used* by a backend and a secret being *revealed* to a model.

**Limits to state honestly if asked:**

- Demo personas are not production authentication.
- Same-user host compromise is out of scope.
- Only registered MCP tools are protected.
- Pattern scanning is a secondary layer.
- All data is synthetic.

Details are in `docs/SECURITY_LIMITATIONS.md`.

---

## Short Georgian version of the opening and close (optional)

> Machine-drafted. Have a native speaker check it before using it on stage.

- **Opening:** „თქვენს AI აგენტს პასუხი სჭირდება და არა თქვენი მთლიანი მონაცემთა ბაზა. ScopeGuard არის მონაცემთა ფაიერვოლი, რომელიც აგენტს ამოცანის შესრულების საშუალებას აძლევს ზედმეტი მონაცემების წაკითხვის გარეშე.“
- **Evidence:** „პასუხი მიწოდებულია. ზედმეტი მონაცემები — არა. მოდელმა მიიღო 4 აგრეგირებული სტრიქონი და 0 პერსონალური მნიშვნელობა.“
- **Close:** „ნუ მისცემთ აგენტებს მეტ მონაცემს. მიეცით მათ უფრო უსაფრთხო გზა.“
