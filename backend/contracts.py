"""Shared strict models and enums. Every model forbids extra fields and validates strictly."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=False)


class Classification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PERSONAL = "PERSONAL"
    RESTRICTED_SECRET = "RESTRICTED_SECRET"


# Higher number = more sensitive. Used for deterministic ranking only.
CLASS_TIER: dict[Classification, int] = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.PERSONAL: 3,
    Classification.RESTRICTED_SECRET: 4,
}


class Role(StrEnum):
    SALES_ANALYST = "sales_analyst"
    CUSTOMER_SUPPORT = "customer_support"


class Intent(StrEnum):
    SALES_BY_REGION_2026_09 = "SALES_BY_REGION_2026_09"
    CRM_CONNECTION_STATUS = "CRM_CONNECTION_STATUS"
    SECRET_DISCLOSURE_ATTEMPT = "SECRET_DISCLOSURE_ATTEMPT"
    NOTIFY_CUSTOMER_105 = "NOTIFY_CUSTOMER_105"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    TRANSFORM = "TRANSFORM"


class TaskStatus(StrEnum):
    CHECKING_INPUT = "CHECKING_INPUT"
    PLANNING = "PLANNING"
    EVALUATING = "EVALUATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    FILTERING = "FILTERING"
    ANSWERING = "ANSWERING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.EXPIRED,
    TaskStatus.CANCELLED,
}


class EventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    INPUT_DENIED = "INPUT_DENIED"
    INPUT_ACCEPTED = "INPUT_ACCEPTED"
    PLANNER_STARTED = "PLANNER_STARTED"
    PLANNER_FALLBACK = "PLANNER_FALLBACK"
    CANDIDATE_EVALUATED = "CANDIDATE_EVALUATED"
    PLAN_SELECTED = "PLAN_SELECTED"
    NO_SAFE_PLAN = "NO_SAFE_PLAN"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"
    GRANT_MINTED = "GRANT_MINTED"
    MCP_REQUEST = "MCP_REQUEST"
    POLICY_DECISION = "POLICY_DECISION"
    UPSTREAM_DISPATCH = "UPSTREAM_DISPATCH"
    OUTPUT_ACCEPTED = "OUTPUT_ACCEPTED"
    OUTPUT_DENIED = "OUTPUT_DENIED"
    MODEL_BOUND = "MODEL_BOUND"
    ANSWER_READY = "ANSWER_READY"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"


class Principal(Strict):
    principal_id: str
    organization: Literal["demo-local"] = "demo-local"
    role: Role
    session_id: str


class ToolStep(Strict):
    step_id: str = Field(min_length=1, max_length=16)
    tool_id: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]


class PlanCandidate(Strict):
    candidate_id: str = Field(min_length=1, max_length=8)
    steps: list[ToolStep] = Field(min_length=1, max_length=3)
    reducer: Literal["SUM_BY_REGION"] | None = None
    rationale: str = Field(max_length=400)
    origin: Literal["deterministic_template", "openai", "gemini", "scripted_malicious"]
    # Informational only. Never used for authorization or ranking.
    self_reported_risk: str | None = Field(default=None, max_length=40)


class ExposureEstimate(Strict):
    """Trusted, registry-derived estimate for an unexecuted candidate. Not a measurement."""

    max_classification: Classification
    requested_fields: list[str]
    requested_classes: list[Classification]
    customer_rows_requested: int
    transaction_rows_requested: int
    aggregate_rows_expected: int
    personal_field_values_requested: int
    estimated_bytes: int
    tool_calls: int


class PlanEvaluation(Strict):
    candidate_id: str
    origin: str
    tools: list[str]
    valid: bool
    covers_task: bool
    decision: Decision
    reason_codes: list[str]
    exposure: ExposureEstimate | None
    selected: bool = False
    rank: int | None = None
    rationale: str = ""
    self_reported_risk: str | None = None


class PolicyDecision(Strict):
    decision: Decision
    reason_code: str
    tool_id: str
    approved_fields: list[str] = Field(default_factory=list)
    message: str = ""
