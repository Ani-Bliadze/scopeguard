"""Pure, deterministic policy evaluation. No LLM/provider imports; no I/O.

Inputs are server-attested principal and task identity plus already schema-validated arguments.
Approval can only authorize inside an existing enterprise allowance and never overrides hard rules."""

from __future__ import annotations

from typing import Any

from backend.contracts import Classification, Decision, Intent, PolicyDecision, Role
from backend.policy.registry import TrustedConfig


def requested_output_fields(entry, args: dict[str, Any]) -> list[str]:
    """Fields the call would return, derived from the trusted registry (not from the caller)."""
    if entry.selectable_fields and "fields" in args:
        fields = list(args["fields"])
        if entry.tool_id == "crm.get_customer_contact":
            fields = ["customer_id", *fields]
        return fields
    return list(entry.fields)


def _deny(tool_id: str, code: str, message: str) -> PolicyDecision:
    return PolicyDecision(decision=Decision.DENY, reason_code=code, tool_id=tool_id, message=message)


def evaluate(
    config: TrustedConfig,
    role: Role | str,
    intent: Intent | str,
    tool_id: str,
    args: dict[str, Any],
    approval_valid: bool = False,
) -> PolicyDecision:
    entry = config.tool(tool_id)
    if entry is None:
        return _deny(tool_id, "UNKNOWN_TOOL", "Tool is not in the trusted registry.")

    try:
        role = Role(role)
    except ValueError:
        return _deny(tool_id, "UNKNOWN_ROLE", "Role is not recognized by policy.")
    try:
        intent = Intent(intent)
    except ValueError:
        return _deny(tool_id, "UNKNOWN_TASK", "Task is not a supported intent.")

    task_policy = config.policy.tasks.get(intent)
    if task_policy is None:
        return _deny(tool_id, "UNKNOWN_TASK", "Task has no policy.")
    if task_policy.terminal_decision == "HARD_DENY_SECRET_DISCLOSURE":
        return _deny(tool_id, "HARD_DENY_SECRET_DISCLOSURE", "Secret values are never disclosed to the model.")

    fields = requested_output_fields(entry, args)
    classes: list[Classification] = []
    for f in fields:
        spec = entry.fields.get(f)
        if spec is None:
            return _deny(tool_id, "UNKNOWN_FIELD", "Requested field is not classified in the registry.")
        classes.append(spec.class_)

    # Hard rule first: nothing in RESTRICTED_SECRET can be model-visible, regardless of role/approval.
    non_disclosable = set(config.policy.hard_rules.non_disclosable_classes)
    if any(c in non_disclosable for c in classes):
        return _deny(tool_id, "HARD_DENY_SECRET_DISCLOSURE", "Secret values are never disclosed to the model.")

    role_policy = config.policy.roles.get(role)
    if role_policy is None:
        return _deny(tool_id, "UNKNOWN_ROLE", "Role is not recognized by policy.")
    if intent not in role_policy.tasks:
        return _deny(tool_id, "TASK_NOT_PERMITTED_FOR_ROLE", "This role may not run this task.")

    rule = task_policy.tools.get(tool_id)
    if rule is None:
        return _deny(
            tool_id,
            "TOOL_NOT_ALLOWED_FOR_TASK",
            "This tool is not approved for the current task purpose.",
        )
    if rule.roles is not None and role not in rule.roles:
        return _deny(tool_id, "ROLE_NOT_PERMITTED_FOR_TOOL", "This role may not use this tool.")

    allowed_classes = set(task_policy.model_visible_classes)
    if any(c not in allowed_classes for c in classes):
        return _deny(
            tool_id,
            "FIELD_CLASS_NOT_PERMITTED",
            "Requested fields include data classes not permitted for this task.",
        )

    for key, expected in rule.constraints.items():
        if args.get(key) != expected:
            return _deny(tool_id, "ARGUMENT_OUT_OF_SCOPE", f"Argument '{key}' is outside the task scope.")

    limit = args.get("limit")
    if isinstance(limit, int) and limit > entry.max_rows:
        return _deny(tool_id, "LIMIT_EXCEEDS_POLICY", "Requested row limit exceeds policy.")

    if rule.decision == Decision.APPROVAL_REQUIRED:
        if approval_valid:
            return PolicyDecision(
                decision=Decision.ALLOW,
                reason_code="ALLOWED_WITH_SCOPED_APPROVAL",
                tool_id=tool_id,
                approved_fields=fields,
                message="Allowed by a one-time approval bound to this task, resource and field.",
            )
        return PolicyDecision(
            decision=Decision.APPROVAL_REQUIRED,
            reason_code="APPROVAL_REQUIRED",
            tool_id=tool_id,
            approved_fields=fields,
            message="A scoped one-time approval is required.",
        )
    if rule.decision == Decision.ALLOW:
        return PolicyDecision(
            decision=Decision.ALLOW,
            reason_code="ALLOWED_BY_TASK_POLICY",
            tool_id=tool_id,
            approved_fields=fields,
            message="Allowed by task policy.",
        )
    return _deny(tool_id, "DEFAULT_DENY", "Denied by default.")
