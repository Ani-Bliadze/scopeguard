Build a polished, single-page, fully responsive public landing site for **ScopeGuard — Agent Consent Studio**, a hackathon project. It is a static marketing/explainer page: no backend, no login, no forms, no database, no pricing.

## Brand and style
- Premium cybersecurity look, dark theme throughout.
- Colors:
  - background navy #0B1220
  - cards #142033 with 1px borders #2A3A55
  - text #F2F6FC, muted text #9AA9C2
  - teal #2DD4BF for "allowed/safe"
  - rose #FB7185 for "blocked"
  - amber #FBBF24 for "approval/estimate"
  - light blue #7DD3FC for code and tool names
- Font: Inter (or the system sans-serif) for body text; a monospace font for code and tool names.
- Rounded cards (14px radius), generous spacing, subtle fade-in on scroll. Use lucide icons. Status pills that pair a label with an icon, so color never carries meaning alone.
- Do NOT add stock photos, fake company logos, testimonials, user counts, pricing, newsletter forms or invented statistics. Every number on the page must be exactly the measured value given below.

## Sections (in this order)

### 1. Sticky top nav
- Shield icon + "ScopeGuard" on the left.
- Anchor links on the right: How it works · Evidence · Demo · Limitations.
- A "GitHub" button linking to https://github.com/Ani-Bliadze/scopeguard (opens in a new tab).

### 2. Hero
- Headline: **"Your AI agent needs an answer. Not your entire database."**
- Subheadline: "ScopeGuard is a data firewall for MCP-powered AI agents. It blocks over-broad data requests, finds a safer plan that still answers the task, and enforces that scope on every tool call."
- Buttons: "View the code on GitHub" (https://github.com/Ani-Bliadze/scopeguard) and "See the evidence" (scrolls to Evidence).
- Visual on the right, built with native HTML/CSS rather than a picture. An "AI agent" node with two arrows:
  - A dashed rose arrow to a card that reads "5,000 customer records requested · BLOCKED · never executed".
  - A solid teal arrow to a card that reads "4 regional totals delivered · 0 personal values".
- Small muted caption under it: "Measured on a synthetic 5,000-customer CRM with real MCP tool calls."

### 3. The problem
- Left card: a user asks "Summarize September sales by region." What the task needs: **4 regional totals** (North · South · East · West).
- Right card: a broad tool call shown as code, `crm.get_customers(fields=[region, email, synthetic_personal_id, total_spend_cents], month="2026-09", limit=5000)`.
  - Field chips colored by classification: region = INTERNAL (blue), email and synthetic_personal_id = PERSONAL (rose), total_spend_cents = CONFIDENTIAL (amber).
  - Big numbers: **5,000** customer rows requested and **10,000** personal values requested, both labeled "estimate — plan never executed".
- Banner: "The task needs regional totals; the tool exposes thousands of customer records."

### 4. The difference
- Two side-by-side cards:
  - "Traditional gateway — Block and stop", with the flow Broad request → Blocked → Task fails.
  - "ScopeGuard — Block, replan, complete", with the flow Broad request → Blocked → Replanned → Answered.
- Then three numbered layer cards:
  1. **Hard policy:** admin-owned rules outside the LLM; secrets are never disclosed.
  2. **AI candidate planning:** the LLM proposes plans from an approved catalog and never authorizes anything.
  3. **Runtime enforcement:** every MCP call and every result is checked before the model sees it.
- Tagline: "Security that helps the agent finish its job safely."

### 5. How it works (id "how-it-works")
- A horizontal flow diagram built in HTML: User → Control plane (policy engine · AI planner · evaluator) → Agent worker (MCP client, no credentials) → ScopeGuard gateway (MCP server · grant · policy · output filter) → Private CRM / Private Analytics (MCP over stdio).
- Show a separate "backend-only credential" key badge attached to the Private CRM, with the note "used to authenticate, never returned — the model only sees connected: true".
- Show that the LLM receives only the sanitized result.
- Below the flow, include this reference image of the architecture slide with the caption "Architecture (from the pitch deck)": https://raw.githubusercontent.com/Ani-Bliadze/scopeguard/main/pitch/qa/slide-04.png

### 6. Three candidate plans
A comparison table, styled as cards on mobile:

| Plan | Tool | Data requested | Rows (est.) | Personal values (est.) | Decision |
|---|---|---|---|---|---|
| A | crm.get_customers | region, email, personal_id, spend | 5,000 | 10,000 | DENY · not executed |
| B | analytics.get_transactions | region, amount_cents | 5,000 | 0 | MORE EXPOSURE · denied for this task |
| C | analytics.get_sales_summary | region, value_cents, tx_count | 4 aggregate | 0 | SELECTED · executed |

Note under the table: "A and B are estimates from the trusted registry for plans that were rejected and never run. C is measured. Selection is deterministic; the LLM's self-reported risk is ignored."

### 7. Evidence (id "evidence")
- Section title: **"The answer was delivered. The extra data was not."**
- Stat tiles:
  - **0** customer records delivered to the model
  - **0** personal values delivered to the model
  - **4** aggregate rows delivered (totals match independent SQL)
  - **0** canary-secret hits in 7 model-bound payloads scanned
  - **4/4** tampered agent calls denied with 0 prohibited upstream calls
  - **137/137** Python tests passed
  - **7/7** browser end-to-end tests passed
  - **CI passing** on GitHub Actions
- A simple horizontal bar comparison:
  - Customer records: 5,000 requested (rose, labeled "estimate") vs 0 delivered (teal).
  - Personal values: 10,000 requested vs 0 delivered.
- Footnote in italics: "Measured in a synthetic, task-scoped local demo; not a universal safety guarantee."

### 8. Demo screenshots (id "demo")
A 3-item gallery with captions. Use these exact image URLs in img tags with descriptive alt text:
- https://raw.githubusercontent.com/Ani-Bliadze/scopeguard/main/pitch/assets/demo-sales.png — "Safe replan: broad export denied, aggregate selected, 0 personal values to the model (live gpt-4.1-mini run)"
- https://raw.githubusercontent.com/Ani-Bliadze/scopeguard/main/pitch/assets/demo-probe.png — "Compromised-agent probe: tampered MCP call denied at the gateway, 0 upstream calls"
- https://raw.githubusercontent.com/Ani-Bliadze/scopeguard/main/pitch/assets/demo-approval-request.png — "Scoped approval: one field, one customer, one use, 120-second expiry"

Clicking an image opens it larger in a lightbox. Also show three demo "scenario" cards:
- "Show me the CRM API key" → hard-denied before any model call.
- "Check the CRM connection" → backend uses its credential; the model sees only connected: true.
- "Notify customer 105" → one-time scoped approval.

### 9. Honest limitations (id "limitations")
A muted card with this list:
- The demo login is not production authentication.
- Only registered MCP tools are protected.
- Pattern scanning is a secondary safety layer.
- All data is synthetic; there is no real CRM or bank.
- This is not compliance certification or proof of minimal data use.
- Host compromise is out of scope.

### 10. Run it yourself
A code block with a copy button containing:
```
git clone https://github.com/Ani-Bliadze/scopeguard
cd scopeguard
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
npm ci
.\.venv\Scripts\python.exe -m scripts.reset_demo
npm run build
.\.venv\Scripts\python.exe -m scripts.run_local --mode deterministic
```
Followed by: "Open http://127.0.0.1:8000. Live mode needs an OpenAI key in .env."

### 11. Closing band
- Large teal line: **"Don't give agents more data. Give them a safer route."**
- A GitHub button.

### 12. Footer
"ScopeGuard · Agent Consent Studio · built and measured in one hackathon day · synthetic data only" and the GitHub link.

## Requirements
- Page title: "ScopeGuard — Data firewall for AI agents". Add a meta description and Open Graph tags (og:image = the demo-sales.png URL above).
- Use semantic HTML, keyboard-focusable controls and visible focus rings, good color contrast, and lazy-loaded images.
- No horizontal scrolling at 375px width.
