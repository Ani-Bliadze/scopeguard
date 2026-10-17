# Security model and limitations

ScopeGuard is a one-day hackathon MVP. It enforces real controls at a real MCP boundary, and those controls are tested. Its claims are deliberately narrow. This page lists what the MVP protects, where it stops, and what it does not claim.

## What is enforced (and tested)

The checks below run outside the LLM, on every MCP `tools/call`.

**Before a call reaches an upstream service:**

- The call needs a valid grant: a bearer token tied to a server-owned grant.
- The tool must be listed in the trusted registry.
- Arguments must pass strict schema validation.
- A pure policy engine checks role, task, field class, constraint and limit.
- The call must match an approved plan step that has not been used yet.
- A one-time scoped approval is consumed where the policy requires one.

**After the upstream call returns:**

- The result is rejected if any of these hold: an `is_error` flag, extra content blocks, application `_meta`, missing structured output, a schema violation, a mismatch between the two MCP channels, an unrequested or unclassified field, a scope mismatch, an oversized result, or a secret or unapproved personal pattern in either channel.

**Before data reaches a model:**

- The exact content is scanned and measured before every provider call.

**Logging:**

- Audit and logs keep field names, classes, reason codes and counts only. Every event is scanned before it is stored.

## Explicit limitations

- **Demo identity is not production authentication.** Personas are picked through a loopback-only demo endpoint and bound to an HttpOnly cookie. There is no SSO, OIDC or proof of identity.
- **Same-user code and host compromise are out of scope.** The agent worker is a separate process with an allowlisted environment and one fixed MCP destination. That is an application capability boundary, not an OS sandbox. Code running as the same Windows user, or a modified repository, could bypass it.
- **Only registered MCP tools are protected.** The gateway does not serve `resources/*`, `prompts/*`, sampling or roots, and no egress, email, SQL or HTTP tools exist. ScopeGuard is not a generic MCP reverse proxy.
- **Pattern scanning is a secondary defense and is incomplete.** It detects this demo's synthetic patterns: canary prefix, API-key-like strings, bearer tokens, PEM private keys, emails and `TEST-PID-…`. It will miss encoded, obfuscated or unfamiliar secret formats. The primary controls are schemas, field allowlists and policy.
- **Aggregates are not differential privacy.** A minimum group size of 20 distinct customers is enforced in SQL. This does not prove resistance to re-identification.
- **No real CRM, bank or customer system is connected.** All data is synthetic. The "CRM credential" is a random canary string generated at reset. "Connected" means the private CRM process verified that string against a stored SHA-256 digest.
- **Minimization is not proven optimal.** Selection uses a transparent ordering over policy-authorized, task-sufficient candidates from a small catalog: maximum class, then personal values, then rows, then bytes, then calls. Exposure numbers for rejected candidates are estimates taken from the registry and fixture metadata. They are not measurements, and the candidates never ran.
- **This is not compliance or breach prevention.** No regulatory certification is claimed, and no reduction in breach probability is claimed.
- **Session, task, grant and approval state is local and ephemeral.** It lives in memory in one process. Audit is also written to `.runtime/audit.sqlite`. A restart or reset clears it.
- **Prompt injection is only partly addressed.** An injection-looking note is seeded on customer 105, but no P0/P1 tool returns notes. The "compromised-agent" probes show that a tampered agent request is denied at the gateway whatever the model did. They are scripted, not an LLM following injected text. Text scanning is not claimed to make the system immune to injection.
- **Live LLM data flow:**
  - In live mode, the planner sends the canonical task text and the approved catalog to OpenAI (`gpt-4.1-mini`, set through `OPENAI_MODEL`).
  - The answer step sends the sanitized tool result to OpenAI as well. For sales, that is 4 aggregate rows. For the connection check, it is a boolean status.
  - In P1 scenario C, the answer step sends one approved synthetic email (customer #105's `@example.com` address) to the provider. This is the documented exception for an authorized personal field.
  - Secrets never go to the provider.
- **The Gemini adapter is untested.** It exists in code, but no Gemini key was available.

## P1 status

| P1 item | Status |
|---|---|
| Scoped one-time approval (customer #105 email, 120 s TTL, single use, task/resource/field/principal bound) | Implemented and tested: approve, deny, expiry, reuse and wrong-resource paths |
| Prompt-injection note scenario | Not implemented as a note-reading task. Replaced by the compromised-agent probes. |
| Tool-metadata poisoning cannot override the registry | Tested: registry description edits do not change policy, and upstream descriptions are never read |
| Invalid inputs, limits, scanner exceptions and timeouts fail closed | Tested |
| Persona switch cannot happen through tool or task parameters | Tested |
| Presidio | Not used |
| Docker | Not provided (Docker engine unavailable on the build machine) |
| Audit export (redacted JSON) | Implemented |
| GIF/video | Not produced. Static screenshots are in `docs/screenshots/`. |
