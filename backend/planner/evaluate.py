"""Deterministic candidate validation, task-coverage checking, policy authorization and ranking.

Self-reported LLM risk is carried for display only and never read here. Exposure numbers are
registry/fixture-derived ESTIMATES for unexecuted candidates, not measurements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.contracts import (
    CLASS_TIER,
    Classification,
    Decision,
    ExposureEstimate,
    Intent,
    PlanCandidate,
    PlanEvaluation,
)
from backend.policy import engine
from backend.policy.registry import TrustedConfig
from backend.tool_schemas import SCHEMAS


@dataclass(frozen=True)
class FixtureMeta:
    customer_count: int
    sales_count: int
    months: int = 2
    regions: int = 4

    @property
    def transactions_per_month(self) -> int:
        return self.sales_count // self.months


def canonical_args(tool_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate and canonicalize; raises ValueError on any schema violation."""
    if tool_id not in SCHEMAS:
        raise ValueError("UNKNOWN_TOOL")
    try:
        return SCHEMAS[tool_id][0].model_validate(args).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        raise ValueError("INVALID_ARGUMENTS") from None


def estimate(config: TrustedConfig, steps: list[tuple[str, dict[str, Any]]], meta: FixtureMeta) -> ExposureEstimate:
    fields_all: list[str] = []
    classes: set[Classification] = set()
    cust = txn = agg = personal = est_bytes = 0
    for tool_id, args in steps:
        entry = config.tool(tool_id)
        fields = engine.requested_output_fields(entry, args)
        fields_all.extend(f"{tool_id}:{f}" for f in fields)
        for f in fields:
            classes.add(entry.fields[f].class_)
        n_personal = sum(1 for f in fields if entry.fields[f].class_ == Classification.PERSONAL)
        row_bytes = sum(len(f) + 4 + entry.fields[f].avg_value_bytes for f in fields) + 2
        if entry.row_kind == "customer":
            population = meta.customer_count // (meta.regions if args.get("region") else 1)
            rows = min(args.get("limit", 1), population) if entry.output_shape == "rows" else 1
            cust += rows
        elif entry.row_kind == "transaction":
            rows = min(args.get("limit", 1), meta.transactions_per_month)
            txn += rows
        elif entry.row_kind == "aggregate":
            rows = meta.regions
            agg += rows
        else:
            rows = 1
        personal += rows * n_personal
        est_bytes += rows * row_bytes + 40
    top = max(classes, key=lambda c: CLASS_TIER[c]) if classes else Classification.PUBLIC
    return ExposureEstimate(
        max_classification=top,
        requested_fields=fields_all,
        requested_classes=sorted(classes, key=lambda c: CLASS_TIER[c]),
        customer_rows_requested=cust,
        transaction_rows_requested=txn,
        aggregate_rows_expected=agg,
        personal_field_values_requested=personal,
        estimated_bytes=est_bytes,
        tool_calls=len(steps),
    )


def coverage(intent: Intent, cand: PlanCandidate, steps: list[tuple[str, dict[str, Any]]], meta: FixtureMeta) -> list[str]:
    """Return [] if the candidate fully answers the fixed task specification, else reason codes."""
    if len(steps) != 1:
        return ["UNSUPPORTED_MULTI_STEP_PLAN"]
    tool_id, a = steps[0]
    if intent == Intent.SALES_BY_REGION_2026_09:
        if tool_id == "analytics.get_sales_summary":
            problems = []
            if a.get("month") != "2026-09":
                problems.append("WRONG_MONTH")
            if a.get("metric") != "total_revenue":
                problems.append("WRONG_METRIC")
            if cand.reducer is not None:
                problems.append("UNNECESSARY_REDUCER")
            return problems
        if tool_id == "crm.get_customers":
            problems = []
            if a.get("month") != "2026-09":
                problems.append("WRONG_MONTH")
            if not {"region", "total_spend_cents"} <= set(a.get("fields", [])):
                problems.append("MISSING_REGION_OR_AMOUNT")
            if a.get("region") is not None:
                problems.append("OMITS_REGIONS")
            if a.get("limit", 0) < meta.customer_count:
                problems.append("LIMIT_TRUNCATES_DATA")
            if cand.reducer != "SUM_BY_REGION":
                problems.append("REDUCER_REQUIRED")
            return problems
        if tool_id == "analytics.get_transactions":
            problems = []
            if a.get("month") != "2026-09":
                problems.append("WRONG_MONTH")
            if not {"region", "amount_cents"} <= set(a.get("fields", [])):
                problems.append("MISSING_REGION_OR_AMOUNT")
            if a.get("limit", 0) < meta.transactions_per_month:
                problems.append("LIMIT_TRUNCATES_DATA")
            if cand.reducer != "SUM_BY_REGION":
                problems.append("REDUCER_REQUIRED")
            return problems
        return ["DOES_NOT_ANSWER_TASK"]
    if intent == Intent.CRM_CONNECTION_STATUS:
        if tool_id == "crm.get_connection_status":
            return []
        if tool_id == "crm.get_customers":
            return []  # a record read would also show connectivity; policy decides
        return ["DOES_NOT_ANSWER_TASK"]
    if intent == Intent.NOTIFY_CUSTOMER_105:
        if tool_id == "crm.get_customer_contact":
            return [] if a.get("customer_id") == 105 and a.get("fields") == ["email"] else ["WRONG_RESOURCE_OR_FIELD"]
        if tool_id == "crm.get_customers" and "email" in a.get("fields", []) and a.get("limit", 0) >= 105:
            return []
        return ["DOES_NOT_ANSWER_TASK"]
    return ["UNSUPPORTED_TASK"]


def rank_key(ev: PlanEvaluation) -> tuple:
    e = ev.exposure
    return (
        CLASS_TIER[e.max_classification],
        e.personal_field_values_requested,
        e.customer_rows_requested + e.transaction_rows_requested,
        e.estimated_bytes,
        e.tool_calls,
        ev.candidate_id,
    )


def evaluate_candidates(
    config: TrustedConfig, role: str, intent: Intent, candidates: list[PlanCandidate], meta: FixtureMeta
) -> tuple[list[PlanEvaluation], PlanEvaluation | None, dict[str, list[tuple[str, dict[str, Any]]]]]:
    evaluations: list[PlanEvaluation] = []
    canon_steps: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    max_calls = config.policy.tasks[intent].max_tool_calls
    for cand in candidates:
        tools = [s.tool_id for s in cand.steps]
        base = {
            "candidate_id": cand.candidate_id,
            "origin": cand.origin,
            "tools": tools,
            "rationale": cand.rationale,
            "self_reported_risk": cand.self_reported_risk,
        }
        steps: list[tuple[str, dict[str, Any]]] = []
        invalid = None
        for s in cand.steps:
            if config.tool(s.tool_id) is None:
                invalid = "UNKNOWN_TOOL"
                break
            try:
                steps.append((s.tool_id, canonical_args(s.tool_id, s.arguments)))
            except ValueError as exc:
                invalid = str(exc)
                break
        if invalid:
            evaluations.append(
                PlanEvaluation(**base, valid=False, covers_task=False, decision=Decision.DENY,
                               reason_codes=[invalid], exposure=None)
            )
            continue
        canon_steps[cand.candidate_id] = steps
        exposure = estimate(config, steps, meta)
        reasons: list[str] = []
        decision = Decision.ALLOW
        if len(steps) > max_calls:
            decision = Decision.DENY
            reasons.append("TOO_MANY_TOOL_CALLS")
        for tool_id, args in steps:
            d = engine.evaluate(config, role, intent, tool_id, args, approval_valid=False)
            if d.decision == Decision.DENY:
                decision = Decision.DENY
                reasons.append(d.reason_code)
            elif d.decision == Decision.APPROVAL_REQUIRED and decision != Decision.DENY:
                decision = Decision.APPROVAL_REQUIRED
                reasons.append(d.reason_code)
        cov = coverage(intent, cand, steps, meta)
        if decision == Decision.ALLOW:
            reasons.append("ALLOWED_BY_TASK_POLICY")
        evaluations.append(
            PlanEvaluation(**base, valid=True, covers_task=not cov, decision=decision,
                           reason_codes=reasons + cov, exposure=exposure)
        )

    eligible = [e for e in evaluations if e.valid and e.covers_task and e.decision == Decision.ALLOW]
    if not eligible:
        eligible = [e for e in evaluations if e.valid and e.covers_task and e.decision == Decision.APPROVAL_REQUIRED]
    eligible.sort(key=rank_key)
    for i, e in enumerate(eligible):
        e.rank = i + 1
    selected = eligible[0] if eligible else None
    if selected:
        selected.selected = True
    return evaluations, selected, canon_steps
