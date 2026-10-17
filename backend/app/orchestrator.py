"""Typed task orchestrator for the trusted control plane.

Flow: input screening -> candidate planning (LLM or labeled deterministic fallback) -> deterministic
evaluation/ranking -> (optional scoped approval) -> server-owned execution grant -> separate agent
worker making real MCP calls to the gateway -> parent re-validation -> model boundary -> answer.
No raw prompt text is persisted; only the canonical supported task."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from mcp.client.stdio import get_default_environment
from pydantic import ValidationError

from backend.agent.protocol import WorkerRequest, WorkerResponse
from backend.app.input_check import check_input
from backend.app.sessions import DemoSession
from backend.contracts import (
    TERMINAL_STATUSES,
    Classification,
    Decision,
    EventType,
    Intent,
    PlanCandidate,
    TaskStatus,
)
from backend.gateway.output_filter import measure
from backend.gateway.server import Gateway
from backend.observability.audit import AuditEvent, pseudonym
from backend.observability.model_boundary import ModelBoundary, ModelBoundaryViolation
from backend.observability.sensitive import PATTERNS, SECRET_CATEGORIES, find_categories
from backend.planner import deterministic as det
from backend.planner.base import (
    ANSWER_SYSTEM,
    ProviderError,
    personal_allowance,
    planner_messages,
    tool_name_for_llm,
)
from backend.planner.evaluate import FixtureMeta, evaluate_candidates
from backend.planner.llm import GeminiAnswerer, GeminiPlanner, OpenAIAnswerer, OpenAIPlanner
from backend.settings import PROJECT_ROOT, PYTHON, Settings
from backend.tool_schemas import SCHEMAS, input_json_schema

BLOCK_MESSAGES = {
    "UNSUPPORTED_TASK": "This request is not one of the supported demo tasks, so no model or tool was invoked.",
    "EMPTY_INPUT": "Please enter a request.",
    "INPUT_TOO_LONG": "The request is too long.",
    "HARD_DENY_SECRET_DISCLOSURE": (
        "Secret values (API keys, passwords, tokens) are never disclosed to the AI model. "
        "No planner, model or backend secret read was invoked. Backend connectors may still use "
        "credentials internally; try 'Check the CRM connection'."
    ),
    "TASK_NOT_PERMITTED_FOR_ROLE": "Your current persona is not permitted to run this task.",
    "BLOCKED_NO_SAFE_PLAN": "No candidate plan is both authorized and sufficient for this task. Permissions were not widened.",
    "APPROVAL_DENIED": "The scoped approval was denied. No customer data was read.",
    "APPROVAL_EXPIRED": "The scoped approval expired before a decision. No customer data was read.",
    "SESSION_ACCESS_PAUSED": "Data access is paused for this session.",
}

PROBES: dict[str, dict[str, Any]] = {
    "broad_export": {
        "label": "Compromised agent: broad CRM export with a sales-task grant",
        "steps": [{"step_id": "s1", "tool_id": "crm.get_customers",
                   "arguments": {"fields": ["id", "region", "display_name", "email", "synthetic_personal_id"], "limit": 5000}}],
    },
    "secret_tool": {
        "label": "Compromised agent: call a private secret tool by name",
        "steps": [{"step_id": "s1", "tool_id": "crm.get_internal_secret", "arguments": {}}],
    },
    "extra_fields": {
        "label": "Compromised agent: smuggle extra fields into an allowed tool",
        "steps": [{"step_id": "s1", "tool_id": "analytics.get_sales_summary",
                   "arguments": {"month": "2026-09", "group_by": "region", "metric": "total_revenue",
                                 "personal_id": "TEST-PID-00001"}}],
    },
    "replay": {
        "label": "Compromised agent: replay an approved step",
        "steps": [
            {"step_id": "s1", "tool_id": "analytics.get_sales_summary",
             "arguments": {"month": "2026-09", "group_by": "region", "metric": "total_revenue"}},
            {"step_id": "s2", "tool_id": "analytics.get_sales_summary",
             "arguments": {"month": "2026-09", "group_by": "region", "metric": "total_revenue"}},
        ],
    },
}

EMAIL_RE = PATTERNS["EMAIL"]


def mask_emails(obj: Any) -> Any:
    """Browser-facing masking of authorized synthetic emails (screenshots never show full addresses)."""

    def m(s: str) -> str:
        return EMAIL_RE.sub(lambda mt: mt.group(0)[0] + "•••" + mt.group(0)[mt.group(0).index("@") - 3:], s)

    if isinstance(obj, str):
        return m(obj)
    if isinstance(obj, dict):
        return {k: mask_emails(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_emails(v) for v in obj]
    return obj


@dataclass
class TaskRecord:
    task_id: str
    session_id: str
    principal_id: str
    role: str
    status: TaskStatus = TaskStatus.CHECKING_INPUT
    intent: str | None = None
    canonical_request: str | None = None
    kind: str = "task"  # task | probe
    probe: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    block: dict[str, str] | None = None
    planner: dict[str, Any] = field(default_factory=dict)
    answer_info: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_candidate_id: str | None = None
    approval: dict[str, Any] | None = None
    execution: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    boundary: list[dict[str, Any]] = field(default_factory=list)
    approval_event: asyncio.Event | None = None
    approval_id: str | None = None

    def public(self) -> dict[str, Any]:
        d = {
            "task_id": self.task_id,
            "kind": self.kind,
            "probe": self.probe,
            "status": self.status.value,
            "intent": self.intent,
            "canonical_request": self.canonical_request,
            "persona": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "duration_ms": int(((self.finished_at or time.time()) - self.created_at) * 1000),
            "block": self.block,
            "planner": self.planner,
            "answer": self.answer_info,
            "candidates": self.candidates,
            "selected_candidate_id": self.selected_candidate_id,
            "approval": self.approval,
            "execution": self.execution,
            "result": self.result,
            "metrics": self.metrics,
            "boundary": self.boundary,
            "terminal": self.status in TERMINAL_STATUSES,
        }
        return mask_emails(d)


def worker_environment() -> dict[str, str]:
    """Allowlisted environment for the agent worker: no inherited secrets, DB paths or provider keys."""
    return get_default_environment() | {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}


class BusyError(Exception):
    pass


class Orchestrator:
    def __init__(self, *, settings: Settings, gateway: Gateway, boundary: ModelBoundary, fixture: FixtureMeta) -> None:
        self.settings = settings
        self.gateway = gateway
        self.config = gateway.config
        self.boundary = boundary
        self.fixture = fixture
        self.tasks: dict[str, TaskRecord] = {}
        self._active: str | None = None
        self._bg: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ helpers
    @property
    def active_task_id(self) -> str | None:
        if self._active and self.tasks.get(self._active) and self.tasks[self._active].status not in TERMINAL_STATUSES:
            return self._active
        return None

    def _event(self, rec: TaskRecord, stage: EventType, **kw) -> None:
        self.gateway.audit.record(AuditEvent(task_id=rec.task_id, principal=pseudonym(rec.principal_id), stage=stage, **kw))

    def _set(self, rec: TaskRecord, status: TaskStatus) -> None:
        rec.status = status
        rec.updated_at = time.time()
        if status in TERMINAL_STATUSES:
            rec.finished_at = time.time()

    def _block(self, rec: TaskRecord, code: str, status: TaskStatus = TaskStatus.BLOCKED, message: str | None = None) -> None:
        rec.block = {"code": code, "message": message or BLOCK_MESSAGES.get(code, "Blocked by policy.")}
        rec.metrics.setdefault("task_completed", False)
        self._set(rec, status)

    def _planner_mode(self) -> str:
        return self.settings.live_provider or "deterministic"

    def get(self, task_id: str, session_id: str) -> TaskRecord | None:
        rec = self.tasks.get(task_id)
        if rec is None or rec.session_id != session_id:
            return None
        return rec

    # ------------------------------------------------------------------ public entry points
    def start(self, session: DemoSession, request: str) -> TaskRecord:
        if self.active_task_id:
            raise BusyError()
        rec = TaskRecord(task_id=uuid.uuid4().hex[:12], session_id=session.session_id,
                         principal_id=session.principal.principal_id, role=session.principal.role.value)
        self.tasks[rec.task_id] = rec
        self._active = rec.task_id
        self._spawn(self._run(rec, session, request))
        return rec

    def start_probe(self, session: DemoSession, probe: str) -> TaskRecord:
        if self.active_task_id:
            raise BusyError()
        rec = TaskRecord(task_id=uuid.uuid4().hex[:12], session_id=session.session_id,
                         principal_id=session.principal.principal_id, role=session.principal.role.value,
                         kind="probe", probe=probe)
        self.tasks[rec.task_id] = rec
        self._active = rec.task_id
        self._spawn(self._run_probe(rec, session, probe))
        return rec

    def _spawn(self, coro) -> None:
        t = asyncio.get_running_loop().create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    async def wait(self, task_id: str, timeout: float = 60.0) -> TaskRecord:
        end = time.time() + timeout
        while time.time() < end:
            rec = self.tasks[task_id]
            if rec.status in TERMINAL_STATUSES or rec.status == TaskStatus.AWAITING_APPROVAL:
                return rec
            await asyncio.sleep(0.05)
        return self.tasks[task_id]

    def notify_approval(self, task_id: str) -> None:
        rec = self.tasks.get(task_id)
        if rec and rec.approval_event:
            rec.approval_event.set()

    # ------------------------------------------------------------------ main flow
    async def _run(self, rec: TaskRecord, session: DemoSession, request: str) -> None:
        try:
            await asyncio.wait_for(self._flow(rec, session, request), timeout=self.settings.task_timeout_s + 130)
        except TimeoutError:
            self._block(rec, "TASK_TIMEOUT", TaskStatus.FAILED, "The task exceeded its time limit and failed closed.")
            self._event(rec, EventType.TASK_FAILED, reason_code="TASK_TIMEOUT")
        except Exception:
            self._block(rec, "INTERNAL_ERROR", TaskStatus.FAILED, "The task failed closed. No partial data was released.")
            self._event(rec, EventType.TASK_FAILED, reason_code="INTERNAL_ERROR")

    async def _flow(self, rec: TaskRecord, session: DemoSession, request: str) -> None:
        self._event(rec, EventType.TASK_CREATED, message=f"persona={rec.role}", counts={"input_chars": len(request or "")})
        if session.access_paused:
            self._event(rec, EventType.INPUT_DENIED, decision="DENY", reason_code="SESSION_ACCESS_PAUSED")
            return self._block(rec, "SESSION_ACCESS_PAUSED")

        verdict = check_input(self.config, request)
        rec.intent = verdict.intent.value if verdict.intent else None
        rec.canonical_request = verdict.canonical_request
        if verdict.code != "ACCEPTED":
            self._event(rec, EventType.INPUT_DENIED, decision="DENY", reason_code=verdict.code,
                        message="Request terminated before any planner, model or tool invocation.")
            rec.metrics = {"task_completed": False, "external_model_requests": 0, "upstream_dispatches": 0,
                           "model_calls": 0, "secret_values_returned_to_model": 0}
            return self._block(rec, verdict.code)
        intent = verdict.intent
        role_tasks = self.config.policy.roles[session.principal.role].tasks
        if intent not in role_tasks:
            self._event(rec, EventType.INPUT_DENIED, decision="DENY", reason_code="TASK_NOT_PERMITTED_FOR_ROLE")
            rec.metrics = {"task_completed": False, "external_model_requests": 0, "upstream_dispatches": 0}
            return self._block(rec, "TASK_NOT_PERMITTED_FOR_ROLE")
        self._event(rec, EventType.INPUT_ACCEPTED, reason_code="SUPPORTED_TASK", message=intent.value)

        # ---------------- planning
        self._set(rec, TaskStatus.PLANNING)
        candidates = await self._plan(rec, intent)

        # ---------------- evaluation
        self._set(rec, TaskStatus.EVALUATING)
        evaluations, selected, canon = evaluate_candidates(self.config, rec.role, intent, candidates, self.fixture)
        rec.candidates = [e.model_dump(mode="json") for e in evaluations]
        for e in evaluations:
            self._event(rec, EventType.CANDIDATE_EVALUATED, candidate_id=e.candidate_id, tool_id=",".join(e.tools)[:64],
                        decision=e.decision.value, reason_code=(e.reason_codes or ["-"])[0],
                        classes=[c.value for c in e.exposure.requested_classes] if e.exposure else [],
                        counts={"customer_rows_requested": e.exposure.customer_rows_requested if e.exposure else 0,
                                "transaction_rows_requested": e.exposure.transaction_rows_requested if e.exposure else 0,
                                "personal_values_requested": e.exposure.personal_field_values_requested if e.exposure else 0},
                        message=("selected" if e.selected else "not executed"))
        rejected = [e for e in evaluations if not e.selected]
        rec.metrics.update({
            "candidates_proposed": len(evaluations),
            "candidates_rejected": len(rejected),
            "risky_candidate_customer_rows_requested": max(
                [e.exposure.customer_rows_requested for e in rejected if e.exposure] or [0]),
            "risky_candidate_personal_values_requested": max(
                [e.exposure.personal_field_values_requested for e in rejected if e.exposure] or [0]),
        })
        if selected is None:
            self._event(rec, EventType.NO_SAFE_PLAN, decision="DENY", reason_code="BLOCKED_NO_SAFE_PLAN")
            rec.metrics.update({"task_completed": False, "upstream_dispatches": 0})
            return self._block(rec, "BLOCKED_NO_SAFE_PLAN")
        rec.selected_candidate_id = selected.candidate_id
        self._event(rec, EventType.PLAN_SELECTED, candidate_id=selected.candidate_id, tool_id=",".join(selected.tools)[:64],
                    decision=selected.decision.value, reason_code="LOWEST_EXPOSURE_AUTHORIZED_SUFFICIENT_PLAN")
        steps = canon[selected.candidate_id]

        approval_id = None
        if selected.decision == Decision.APPROVAL_REQUIRED:
            approval_id = await self._await_approval(rec, session, intent, steps)
            if approval_id is None:
                return
        await self._execute(rec, session, intent, steps, approval_id)

    async def _plan(self, rec: TaskRecord, intent: Intent) -> list[PlanCandidate]:
        spec = self.config.tasks.intents[intent]
        messages = planner_messages(spec.canonical_request, spec.coverage, self.config)
        provider_name = self._planner_mode()
        rec.planner = {"mode": provider_name, "model": self._model_name(provider_name), "fallback_reason": None}
        self._event(rec, EventType.PLANNER_STARTED, model_mode=provider_name,
                    message="Planner receives canonical task + approved catalog only")
        planner = {"openai": lambda: OpenAIPlanner(self.settings), "gemini": lambda: GeminiPlanner(self.settings)}.get(
            provider_name, lambda: det.DeterministicPlanner(intent))()
        try:
            cands, m = await self.boundary.dispatch(
                phase="planner", provider=provider_name, messages=messages, tool_result=None, tool_counts=None,
                allow_personal=set(), call=planner.propose)
            rec.boundary.append(ModelBoundary.as_dict(m))
            if len(cands) < 2 and provider_name != "deterministic":
                raise ProviderError("PLANNER_TOO_FEW_CANDIDATES")
            return cands
        except (ProviderError, ModelBoundaryViolation) as exc:
            if provider_name == "deterministic":
                raise
            failed = getattr(exc, "measurement", None)
            if failed is not None:
                rec.boundary.append(ModelBoundary.as_dict(failed))
            code = getattr(exc, "code", "PROVIDER_ERROR")
            rec.planner = {"mode": "deterministic", "model": None, "fallback_reason": code, "attempted": provider_name}
            self._event(rec, EventType.PLANNER_FALLBACK, reason_code=code, model_mode="deterministic",
                        message="Live planner unavailable or invalid; labeled deterministic fallback used")
            fallback = det.DeterministicPlanner(intent)
            cands, m = await self.boundary.dispatch(
                phase="planner", provider="deterministic", messages=messages, tool_result=None, tool_counts=None,
                allow_personal=set(), call=fallback.propose)
            rec.boundary.append(ModelBoundary.as_dict(m))
            return cands

    def _model_name(self, provider: str) -> str | None:
        return {"openai": self.settings.openai_model, "gemini": self.settings.gemini_model}.get(provider)

    async def _await_approval(self, rec: TaskRecord, session: DemoSession, intent: Intent, steps) -> str | None:
        tool_id, args = steps[0]
        rule = self.config.policy.tasks[intent].tools[tool_id]
        if not self.settings.enable_approvals:
            self._block(rec, "APPROVALS_DISABLED", message="Scoped approvals are disabled in this configuration.")
            return None
        req = self.gateway.approvals.create(
            session_id=session.session_id, principal_id=rec.principal_id, task_id=rec.task_id, intent=intent.value,
            tool_id=tool_id, resource={"customer_id": args["customer_id"]}, fields=list(args["fields"]),
            purpose=self.config.policy.tasks[intent].purpose, single_use=rule.single_use,
            ttl_s=rule.approval_ttl_seconds or 120)
        rec.approval_id = req.approval_id
        rec.approval = req.public()
        rec.approval_event = asyncio.Event()
        self._set(rec, TaskStatus.AWAITING_APPROVAL)
        self._event(rec, EventType.APPROVAL_REQUESTED, tool_id=tool_id, decision="APPROVAL_REQUIRED",
                    reason_code="APPROVAL_REQUIRED", fields=list(args["fields"]), classes=["PERSONAL"],
                    message=f"resource=customer:{args['customer_id']} ttl={int(req.expires_at - req.created_at)}s single_use")
        try:
            await asyncio.wait_for(rec.approval_event.wait(), timeout=max(0.0, req.expires_at - time.time()))
        except TimeoutError:
            pass
        current = self.gateway.approvals.get(req.approval_id)
        rec.approval = current.public() if current else None
        status = current.status if current else "EXPIRED"
        self._event(rec, EventType.APPROVAL_DECIDED, tool_id=tool_id, decision=status, reason_code=f"APPROVAL_{status}")
        if status == "APPROVED":
            return req.approval_id
        rec.metrics.update({"task_completed": False, "upstream_dispatches": 0})
        if status == "DENIED":
            self._block(rec, "APPROVAL_DENIED")
        else:
            self._block(rec, "APPROVAL_EXPIRED", TaskStatus.EXPIRED)
        return None

    async def _run_worker(self, token: str, run_id: str, steps: list[dict[str, Any]]) -> WorkerResponse:
        req = WorkerRequest(gateway_url=f"http://127.0.0.1:{self.settings.port}/mcp/", token=token, run_id=run_id,
                            steps=steps)
        env = worker_environment()
        proc = await asyncio.create_subprocess_exec(
            PYTHON, "-m", "backend.agent.worker", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, cwd=str(PROJECT_ROOT), env=env)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(req.model_dump_json().encode()), timeout=self.settings.task_timeout_s)
        except TimeoutError:
            proc.kill()
            return WorkerResponse(run_id=run_id, error_code="WORKER_TIMEOUT")
        try:
            return WorkerResponse.model_validate_json(out[: 64 * 1024])
        except ValidationError:
            return WorkerResponse(run_id=run_id, error_code="WORKER_OUTPUT_INVALID")

    async def _execute(self, rec: TaskRecord, session: DemoSession, intent: Intent, steps, approval_id: str | None) -> None:
        self._set(rec, TaskStatus.EXECUTING)
        token, grant = self.gateway.grants.mint(
            session_id=session.session_id, principal_id=rec.principal_id, role=rec.role, task_id=rec.task_id,
            intent=intent.value, config_digest=self.config.combined_digest, steps=steps,
            ttl_s=self.settings.task_timeout_s, approval_id=approval_id)
        self._event(rec, EventType.GRANT_MINTED, run_id=grant.run_id, counts={"steps": len(steps)},
                    message="Execution grant bound to session, task, config digest and exact selected steps")
        dispatch_before = self.gateway.upstream.dispatch_count(task_id=rec.task_id)
        worker = await self._run_worker(token, grant.run_id, [
            {"step_id": f"s{i + 1}", "tool_id": t, "arguments": a} for i, (t, a) in enumerate(steps)])
        del token
        self.gateway.grants.complete(grant)
        gm = self.gateway.run_metrics.get(grant.run_id)
        rec.execution = {
            "transport": "MCP Streamable HTTP (agent worker -> ScopeGuard gateway) + stdio (gateway -> private upstream)",
            "protocol_version": worker.protocol_version,
            "listed_tools": worker.listed_tools,
            "steps": [{"tool_id": r.tool_id, "ok": r.ok, "error_code": r.error_code} for r in worker.results],
            "worker_error": worker.error_code,
            "verified_mcp_round_trip": bool(worker.results) and all(r.ok for r in worker.results),
        }
        upstream_dispatches = self.gateway.upstream.dispatch_count(task_id=rec.task_id) - dispatch_before
        rec.metrics.update({
            "mcp_calls": gm.mcp_calls if gm else 0,
            "gateway_calls_denied": gm.gateway_calls_denied if gm else 0,
            "upstream_dispatches": upstream_dispatches,
        })
        if worker.error_code or not rec.execution["verified_mcp_round_trip"]:
            code = worker.error_code or (worker.results[-1].error_code if worker.results else "NO_RESULT")
            rec.metrics.update(self._zero_exposure())
            self._event(rec, EventType.TASK_FAILED, reason_code=code)
            return self._block(rec, code or "EXECUTION_FAILED", TaskStatus.FAILED,
                               "Execution failed closed at the gateway; nothing was delivered to the model.")

        # ---------------- parent re-validation (defense in depth)
        self._set(rec, TaskStatus.FILTERING)
        tool_id, args = steps[0]
        entry = self.config.tool(tool_id)
        structured = worker.results[0].structured or {}
        try:
            safe = SCHEMAS[tool_id][1].model_validate(structured).model_dump(mode="json", exclude_none=True)
        except ValidationError:
            return self._block(rec, "WORKER_RESULT_INVALID", TaskStatus.FAILED, "Agent result failed re-validation.")
        if find_categories(safe) & SECRET_CATEGORIES:
            return self._block(rec, "SECRET_PATTERN_IN_RESULT", TaskStatus.FAILED, "Result blocked by secret scanner.")
        counts = measure(entry, safe)

        # ---------------- model boundary + answer
        self._set(rec, TaskStatus.ANSWERING)
        task_policy = self.config.policy.tasks[intent]
        approved_fields = list(args.get("fields", [])) if tool_id == "crm.get_customer_contact" else []
        allow_personal = personal_allowance(task_policy.model_visible_classes, approved_fields)
        call_id = "call_s1"
        messages = [
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": self.config.tasks.intents[intent].canonical_request},
            {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {
                "name": tool_name_for_llm(tool_id), "arguments": json.dumps(args, separators=(",", ":"))}}]},
            {"role": "tool", "tool_call_id": call_id, "content": json.dumps(safe, separators=(",", ":"))},
        ]
        answer_text, m = await self._answer(rec, intent, messages, safe, counts, allow_personal, tool_id)
        if answer_text is None:
            return
        if m is not None:
            rec.boundary.append(ModelBoundary.as_dict(m))
            self._event(rec, EventType.MODEL_BOUND, model_mode=m.provider,
                        counts={"tool_result_bytes": m.tool_result_bytes, "total_bytes": m.total_bytes,
                                "customer_rows": m.customer_rows, "aggregate_rows": m.aggregate_rows,
                                "personal_field_values": m.personal_field_values, "canary_hits": m.canary_hits},
                        message="Exact model-bound content scanned and measured")
        kind = {"analytics.get_sales_summary": "sales_summary", "crm.get_connection_status": "connection_status",
                "crm.get_customer_contact": "customer_contact"}[tool_id]
        rec.result = {"kind": kind, "data": safe, "answer_text": answer_text}
        rec.metrics.update({
            "customer_rows_returned_to_model": counts["customer_rows"],
            "transaction_rows_returned_to_model": counts["transaction_rows"],
            "aggregate_rows_returned_to_model": counts["aggregate_rows"],
            "personal_field_values_returned_to_model": counts["personal_field_values"],
            "secret_values_returned_to_model": 0 if (m is None or m.canary_hits == 0) else m.canary_hits,
            "tool_result_bytes_model_bound": m.tool_result_bytes if m else 0,
            "total_model_bound_bytes": sum(b["total_bytes"] for b in rec.boundary if b["dispatched"]),
            "model_calls": sum(1 for b in rec.boundary if b["dispatched"]),
            "external_model_requests": sum(1 for b in rec.boundary if b["external_request"] and b["dispatched"]),
            "task_completed": True,
        })
        self._set(rec, TaskStatus.COMPLETED)
        self._event(rec, EventType.TASK_COMPLETED, reason_code="ANSWER_DELIVERED",
                    counts={k: v for k, v in rec.metrics.items() if isinstance(v, int) and not isinstance(v, bool)})

    @staticmethod
    def _zero_exposure() -> dict[str, Any]:
        return {"customer_rows_returned_to_model": 0, "transaction_rows_returned_to_model": 0,
                "aggregate_rows_returned_to_model": 0, "personal_field_values_returned_to_model": 0,
                "secret_values_returned_to_model": 0, "tool_result_bytes_model_bound": 0, "task_completed": False}

    async def _answer(self, rec, intent, messages, safe, counts, allow_personal, tool_id):
        provider_name = self._planner_mode()
        rec.answer_info = {"mode": provider_name, "model": self._model_name(provider_name), "verified": None,
                           "fallback_reason": None}
        tools = [{"type": "function", "function": {"name": tool_name_for_llm(tool_id), "description": "ScopeGuard tool",
                                                   "parameters": input_json_schema(tool_id)}}]
        answerer = {"openai": lambda: OpenAIAnswerer(self.settings, tools),
                    "gemini": lambda: GeminiAnswerer(self.settings)}.get(provider_name, lambda: det.DeterministicAnswerer(intent))()
        try:
            text, m = await self.boundary.dispatch(phase="answer", provider=provider_name, messages=messages,
                                                  tool_result=safe, tool_counts=counts, allow_personal=allow_personal,
                                                  call=answerer.summarize)
        except ModelBoundaryViolation as exc:
            rec.metrics.update(self._zero_exposure())
            self._event(rec, EventType.TASK_FAILED, reason_code=exc.code)
            self._block(rec, exc.code, TaskStatus.FAILED, "The model boundary blocked prohibited content. Nothing was sent.")
            return None, None
        except ProviderError as exc:
            failed = getattr(exc, "measurement", None)
            if failed is not None:
                rec.boundary.append(ModelBoundary.as_dict(failed))  # the live attempt still received content
            rec.answer_info.update({"mode": "deterministic", "model": None, "fallback_reason": exc.code,
                                    "attempted": provider_name})
            fallback = det.DeterministicAnswerer(intent)
            text, m = await self.boundary.dispatch(phase="answer", provider="deterministic", messages=messages,
                                                  tool_result=safe, tool_counts=counts, allow_personal=allow_personal,
                                                  call=fallback.summarize)
            return text, m
        verified, reason = verify_answer(intent, text, safe, allow_personal)
        rec.answer_info["verified"] = verified
        if not verified:
            rec.answer_info["fallback_reason"] = reason
            rec.answer_info["live_answer_discarded"] = True
            text = det.deterministic_answer(intent, safe)
            rec.answer_info["display"] = "deterministic_rendering"
        return text, m

    # ------------------------------------------------------------------ security probe (compromised agent)
    async def _run_probe(self, rec: TaskRecord, session: DemoSession, probe: str) -> None:
        try:
            spec = PROBES[probe]
            intent = Intent.SALES_BY_REGION_2026_09
            rec.intent = intent.value
            rec.canonical_request = spec["label"]
            self._event(rec, EventType.TASK_CREATED, message=f"security probe: {probe} (scripted, not an LLM decision)")
            if intent not in self.config.policy.roles[session.principal.role].tasks:
                return self._block(rec, "TASK_NOT_PERMITTED_FOR_ROLE")
            approved = [("analytics.get_sales_summary", {"month": "2026-09", "group_by": "region", "metric": "total_revenue"})]
            rec.planner = {"mode": "scripted_probe", "model": None, "fallback_reason": None}
            rec.selected_candidate_id = "C"
            self._set(rec, TaskStatus.EXECUTING)
            token, grant = self.gateway.grants.mint(
                session_id=session.session_id, principal_id=rec.principal_id, role=rec.role, task_id=rec.task_id,
                intent=intent.value, config_digest=self.config.combined_digest, steps=approved,
                ttl_s=self.settings.task_timeout_s)
            self._event(rec, EventType.GRANT_MINTED, run_id=grant.run_id, counts={"steps": 1},
                        message="Grant covers only the approved aggregate step; the agent sends tampered calls")
            before = self.gateway.upstream.dispatch_count(task_id=rec.task_id)
            worker = await self._run_worker(token, grant.run_id, spec["steps"])
            self.gateway.grants.complete(grant)
            gm = self.gateway.run_metrics.get(grant.run_id)
            rec.execution = {
                "transport": "MCP Streamable HTTP (agent worker -> ScopeGuard gateway)",
                "protocol_version": worker.protocol_version,
                "listed_tools": worker.listed_tools,
                "steps": [{"tool_id": r.tool_id, "ok": r.ok, "error_code": r.error_code} for r in worker.results],
                "worker_error": worker.error_code,
                "attempted_calls": [s["tool_id"] for s in spec["steps"]],
            }
            if probe == "replay" and worker.results and worker.results[0].ok:
                # Continue the replay: the worker stops at first error, so results reflect s1 ok then s2 denied.
                pass
            dispatched = self.gateway.upstream.dispatch_count(task_id=rec.task_id) - before
            prohibited_dispatches = dispatched - (1 if probe == "replay" and worker.results and worker.results[0].ok else 0)
            rec.metrics = {
                "mcp_calls": gm.mcp_calls if gm else 0,
                "gateway_calls_denied": gm.gateway_calls_denied if gm else 0,
                "deny_reasons": gm.deny_reasons if gm else [],
                "upstream_dispatches": dispatched,
                "prohibited_upstream_dispatches": prohibited_dispatches,
                "customer_rows_returned_to_model": 0,
                "personal_field_values_returned_to_model": 0,
                "secret_values_returned_to_model": 0,
                "model_calls": 0,
                "external_model_requests": 0,
                "task_completed": False,
            }
            denied = (gm.gateway_calls_denied if gm else 0) > 0
            self._block(rec, "PROBE_BLOCKED" if denied else "PROBE_NOT_BLOCKED",
                        message=("ScopeGuard denied the tampered call at the gateway; the private upstream was not "
                                 "called for it." if denied else "Probe was not blocked."))
        except Exception:
            self._block(rec, "INTERNAL_ERROR", TaskStatus.FAILED, "Probe failed closed.")


_MONEY = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m|thousand|million)?", re.IGNORECASE)


def verify_answer(intent: Intent, text: str, safe: dict[str, Any], allow_personal: set[str]) -> tuple[bool, str | None]:
    """Live answers must not introduce secrets/unapproved personal data and must agree with authoritative totals."""
    cats = find_categories(text)
    if cats & SECRET_CATEGORIES:
        return False, "ANSWER_CONTAINS_SECRET_PATTERN"
    if (cats - SECRET_CATEGORIES) - allow_personal:
        return False, "ANSWER_CONTAINS_PERSONAL_PATTERN"
    if intent == Intent.SALES_BY_REGION_2026_09:
        values = [r["value_cents"] / 100 for r in safe["rows"]]
        values.append(sum(values))
        for mt in _MONEY.finditer(text):
            v = float(mt.group(1).replace(",", ""))
            suffix = (mt.group(2) or "").lower()
            v *= 1_000 if suffix in ("k", "thousand") else 1_000_000 if suffix in ("m", "million") else 1
            if not any(abs(v - x) <= max(1.0, 0.01 * x) for x in values):
                return False, "ANSWER_NUMBERS_DISAGREE_WITH_TOOL_RESULT"
        if not all(r["region"] in text for r in safe["rows"]):
            return False, "ANSWER_OMITS_REGIONS"
    return True, None


__all__ = ["Orchestrator", "BusyError", "TaskRecord", "PROBES", "Classification"]
