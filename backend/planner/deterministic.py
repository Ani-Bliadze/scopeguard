"""Deterministic, offline template planner and answer adapter (clearly labeled 'Deterministic demo').

The template planner intentionally proposes broad candidates alongside the safe one so the policy
engine's rejection and replanning are visible and reproducible."""

from __future__ import annotations

import json
from typing import Any

from backend.contracts import Intent, PlanCandidate

TEMPLATES: dict[Intent, list[dict[str, Any]]] = {
    Intent.SALES_BY_REGION_2026_09: [
        {
            "candidate_id": "A",
            "steps": [
                {
                    "step_id": "s1",
                    "tool_id": "crm.get_customers",
                    "arguments": {
                        "fields": ["region", "email", "synthetic_personal_id", "total_spend_cents"],
                        "limit": 5000,
                        "month": "2026-09",
                    },
                }
            ],
            "reducer": "SUM_BY_REGION",
            "rationale": "Export every customer with September spend, then sum spend by region.",
            "self_reported_risk": "high",
        },
        {
            "candidate_id": "B",
            "steps": [
                {
                    "step_id": "s1",
                    "tool_id": "analytics.get_transactions",
                    "arguments": {"month": "2026-09", "fields": ["region", "amount_cents"], "limit": 5000},
                }
            ],
            "reducer": "SUM_BY_REGION",
            "rationale": "Pull all September transactions with region and amount, then sum by region.",
            "self_reported_risk": "medium",
        },
        {
            "candidate_id": "C",
            "steps": [
                {
                    "step_id": "s1",
                    "tool_id": "analytics.get_sales_summary",
                    "arguments": {"month": "2026-09", "group_by": "region", "metric": "total_revenue"},
                }
            ],
            "reducer": None,
            "rationale": "Ask the analytics service for the September revenue aggregate per region.",
            "self_reported_risk": "low",
        },
    ],
    Intent.CRM_CONNECTION_STATUS: [
        {
            "candidate_id": "A",
            "steps": [{"step_id": "s1", "tool_id": "crm.get_customers", "arguments": {"fields": ["id"], "limit": 1}}],
            "reducer": None,
            "rationale": "Probe connectivity by reading one customer record.",
            "self_reported_risk": "medium",
        },
        {
            "candidate_id": "B",
            "steps": [{"step_id": "s1", "tool_id": "crm.get_connection_status", "arguments": {}}],
            "reducer": None,
            "rationale": "Use the connector health check, which authenticates with the backend credential.",
            "self_reported_risk": "low",
        },
    ],
    Intent.NOTIFY_CUSTOMER_105: [
        {
            "candidate_id": "A",
            "steps": [
                {"step_id": "s1", "tool_id": "crm.get_customers", "arguments": {"fields": ["id", "email"], "limit": 5000}}
            ],
            "reducer": None,
            "rationale": "Load the customer directory and look up customer 105's email.",
            "self_reported_risk": "high",
        },
        {
            "candidate_id": "B",
            "steps": [
                {
                    "step_id": "s1",
                    "tool_id": "crm.get_customer_contact",
                    "arguments": {"customer_id": 105, "fields": ["email"]},
                }
            ],
            "reducer": None,
            "rationale": "Request only customer 105's email for the notification purpose.",
            "self_reported_risk": "low",
        },
    ],
}


class DeterministicPlanner:
    name = "deterministic"

    def __init__(self, intent: Intent) -> None:
        self.intent = intent

    async def propose(self, messages: list[dict[str, Any]]) -> list[PlanCandidate]:
        return [
            PlanCandidate.model_validate({**c, "origin": "deterministic_template"}, strict=False)
            for c in TEMPLATES.get(self.intent, [])
        ]


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def deterministic_answer(intent: Intent, result: dict[str, Any] | None) -> str:
    if intent == Intent.SALES_BY_REGION_2026_09 and result:
        rows = sorted(result["rows"], key=lambda r: -r["value_cents"])
        total = sum(r["value_cents"] for r in rows)
        parts = "; ".join(f"{r['region']} {dollars(r['value_cents'])} ({r['transaction_count']:,} transactions)" for r in rows)
        top = rows[0]["region"] if rows else "n/a"
        return (
            f"September 2026 revenue by region (synthetic USD): {parts}. "
            f"Total {dollars(total)} across {len(rows)} regions; {top} is highest."
        )
    if intent == Intent.CRM_CONNECTION_STATUS and result is not None:
        if result.get("connected"):
            return (
                "The CRM connector authenticated successfully with its backend-held credential "
                "(synthetic local digest check). The credential value was never shared with the model."
            )
        return "The CRM connector could not authenticate. No credential value was shared with the model."
    if intent == Intent.NOTIFY_CUSTOMER_105 and result:
        return (
            f"Notification draft prepared for customer #{result['customer_id']} at the approved address "
            f"{result['email']}. Nothing was sent: no email-sending tool exists."
        )
    return "No answer available."


class DeterministicAnswerer:
    name = "deterministic"

    def __init__(self, intent: Intent) -> None:
        self.intent = intent

    async def summarize(self, messages: list[dict[str, Any]]) -> str:
        # Reads the tool result from the exact same model-bound messages a live model would receive.
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        result = json.loads(tool_msgs[-1]["content"]) if tool_msgs else None
        return deterministic_answer(self.intent, result)
