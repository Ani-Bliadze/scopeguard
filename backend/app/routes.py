"""HTTP API for the dashboard. Strict request models reject extra fields such as role/principal/
policy_override. Identity comes only from the server-side demo session cookie."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from backend.app.orchestrator import PROBES, BusyError, mask_emails
from backend.app.sessions import COOKIE_NAME, CSRF_HEADER, DemoSession
from backend.contracts import Role, TaskStatus
from backend.observability.sensitive import find_categories

router = APIRouter(prefix="/api")

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _sg(request: Request):
    return request.app.state.sg


def _require_loopback(request: Request) -> None:
    host = (request.headers.get("host") or "").split(":")[0]
    client = request.client.host if request.client else ""
    if client not in LOOPBACK or host not in {"127.0.0.1", "localhost", "testserver"}:
        raise HTTPException(403, {"error": "LOOPBACK_ONLY"})
    origin = request.headers.get("origin")
    if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise HTTPException(403, {"error": "ORIGIN_NOT_ALLOWED"})


def _session(request: Request) -> DemoSession:
    s = _sg(request).sessions.get(request.cookies.get(COOKIE_NAME))
    if s is None:
        raise HTTPException(401, {"error": "NO_SESSION", "message": "Choose a demo persona first."})
    return s


def _mutating(request: Request) -> DemoSession:
    _require_loopback(request)
    s = _session(request)
    if not _sg(request).sessions.csrf_ok(s, request.headers.get(CSRF_HEADER)):
        raise HTTPException(403, {"error": "CSRF_FAILED"})
    return s


def _ready(request: Request):
    sg = _sg(request)
    if sg.orchestrator is None or sg.gateway is None:
        raise HTTPException(503, {"error": "NOT_READY", "message": "Configuration or fixture invalid; run reset."})
    return sg


# ------------------------------------------------------------------ models
class ApiModel(BaseModel):
    # Unknown fields (role, principal, task_scope, policy_override, ...) are rejected outright.
    model_config = ConfigDict(extra="forbid", strict=False)


class SessionCreate(ApiModel):
    persona: Role


class TaskCreate(ApiModel):
    request: str = Field(max_length=4096)
    client_request_id: str = Field(min_length=1, max_length=64)


class AccessToggle(ApiModel):
    paused: StrictBool


class ApprovalDecision(ApiModel):
    decision: Literal["approve", "deny"]


class ProbeCreate(ApiModel):
    probe: Literal["broad_export", "secret_tool", "extra_fields", "replay"]


# ------------------------------------------------------------------ routes
@router.get("/health")
async def health(request: Request):
    sg = _sg(request)
    upstream = sg.gateway.upstream.status() if sg.gateway else {}
    return {
        "status": "ok" if sg.orchestrator and all(upstream.values()) else "degraded",
        "config_valid": sg.config is not None,
        "config_error": sg.config_error,
        "fixture_loaded": sg.fixture is not None,
        "fixture": {"customers": sg.fixture.customer_count, "sales": sg.fixture.sales_count} if sg.fixture else None,
        "upstreams": upstream,
        "upstream_transport": "stdio (private, no listening sockets)",
        "gateway_transport": "MCP Streamable HTTP at /mcp/ (grant-bound bearer required)",
        "planner_mode": sg.settings.live_provider or "deterministic",
        "answer_mode": sg.settings.live_provider or "deterministic",
        "live_model": sg.settings.openai_model if sg.settings.live_provider == "openai" else
        (sg.settings.gemini_model if sg.settings.live_provider == "gemini" else None),
        "approvals_enabled": sg.settings.enable_approvals,
        "config_digest": sg.config.combined_digest[:16] if sg.config else None,
    }


def _session_view(sg, s: DemoSession) -> dict:
    return {
        "persona": s.principal.role.value,
        "principal": s.principal.principal_id,
        "session_id": s.session_id,
        "csrf_token": s.csrf_token,
        "access_paused": s.access_paused,
        "features": {"approvals": sg.settings.enable_approvals, "probes": list(PROBES)},
        "mode": sg.settings.live_provider or "deterministic",
        "label": "Local demo session (not production authentication)",
    }


@router.post("/demo/session")
async def create_session(body: SessionCreate, request: Request, response: Response):
    _require_loopback(request)
    sg = _sg(request)
    old = sg.sessions.get(request.cookies.get(COOKIE_NAME))
    if old is not None:
        if sg.gateway:
            sg.gateway.grants.revoke_session(old.session_id)
        sg.sessions.drop(old)
    s = sg.sessions.create(body.persona)
    response.set_cookie(COOKIE_NAME, s.cookie_value, httponly=True, samesite="strict", path="/")
    return _session_view(sg, s)


@router.get("/session")
async def get_session(request: Request):
    sg = _sg(request)
    s = sg.sessions.get(request.cookies.get(COOKIE_NAME))
    if s is None:
        return {"active": False, "label": "No demo session yet: choose a persona."}
    return {"active": True, **_session_view(sg, s)}


@router.post("/session/access")
async def set_access(body: AccessToggle, request: Request):
    s = _mutating(request)
    sg = _sg(request)
    s.access_paused = body.paused
    revoked = sg.gateway.grants.revoke_session(s.session_id) if (body.paused and sg.gateway) else 0
    return {"access_paused": s.access_paused, "grants_revoked": revoked}


@router.post("/tasks", status_code=202)
async def create_task(body: TaskCreate, request: Request):
    s = _mutating(request)
    sg = _ready(request)
    try:
        rec = sg.orchestrator.start(s, body.request)
    except BusyError:
        raise HTTPException(409, {"error": "BUSY", "message": "Another task is running. Wait for it to finish."}) from None
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/demo/probe", status_code=202)
async def create_probe(body: ProbeCreate, request: Request):
    s = _mutating(request)
    sg = _ready(request)
    try:
        rec = sg.orchestrator.start_probe(s, body.probe)
    except BusyError:
        raise HTTPException(409, {"error": "BUSY", "message": "Another task is running."}) from None
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.get("/tasks")
async def list_tasks(request: Request):
    s = _session(request)
    sg = _ready(request)
    recs = [r for r in sg.orchestrator.tasks.values() if r.session_id == s.session_id]
    recs.sort(key=lambda r: r.created_at, reverse=True)
    return [{"task_id": r.task_id, "status": r.status.value, "intent": r.intent, "kind": r.kind,
             "probe": r.probe, "created_at": r.created_at} for r in recs[:20]]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    s = _session(request)
    sg = _ready(request)
    rec = sg.orchestrator.get(task_id, s.session_id)
    if rec is None:
        raise HTTPException(404, {"error": "NOT_FOUND"})
    return rec.public()


@router.get("/tasks/{task_id}/events")
async def get_events(task_id: str, request: Request, after: int = 0):
    s = _session(request)
    sg = _ready(request)
    if sg.orchestrator.get(task_id, s.session_id) is None:
        raise HTTPException(404, {"error": "NOT_FOUND"})
    events = [e.model_dump(mode="json") for e in sg.gateway.audit.for_task(task_id, after)]
    return {"events": events}


@router.get("/audit/export")
async def export_audit(request: Request):
    s = _session(request)
    sg = _ready(request)
    mine = {r.task_id for r in sg.orchestrator.tasks.values() if r.session_id == s.session_id}
    rows = [e.model_dump(mode="json") for e in sg.gateway.audit.all() if e.task_id in mine]
    payload = {"exported_at": time.time(), "note": "Redacted metadata only: no record values, secrets or prompts.",
               "events": rows}
    if find_categories(payload):
        raise HTTPException(500, {"error": "EXPORT_REDACTION_GUARD"})
    return payload


@router.get("/policy/summary")
async def policy_summary(request: Request):
    sg = _ready(request)
    cfg = sg.config
    return {
        "policy_version": cfg.policy.policy_version,
        "registry_version": cfg.registry.registry_version,
        "default_decision": cfg.policy.default_decision,
        "hard_rules": cfg.policy.hard_rules.description,
        "classes": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "PERSONAL", "RESTRICTED_SECRET"],
        "roles": {r.value: {"description": p.description, "tasks": [t.value for t in p.tasks]}
                  for r, p in cfg.policy.roles.items()},
        "tasks": {i.value: {"purpose": p.purpose, "model_visible_classes": [c.value for c in p.model_visible_classes],
                            "tools": {k: v.decision.value for k, v in p.tools.items()}}
                  for i, p in cfg.policy.tasks.items()},
        "tools": [{"tool_id": t.tool_id, "server": t.server_id, "description": t.description, "row_kind": t.row_kind,
                   "max_rows": t.max_rows, "approval_mode": t.approval_mode,
                   "fields": {f: s.class_.value for f, s in t.fields.items()},
                   "backend_secrets_used": {k: v.value for k, v in t.backend_secrets_used.items()}}
                  for t in cfg.registry.tools],
        "unsupported_surfaces": ["resources/*", "prompts/*", "sampling", "roots", "arbitrary HTTP/egress tools"],
    }


@router.get("/approvals")
async def list_approvals(request: Request):
    s = _session(request)
    sg = _ready(request)
    return [mask_emails(a.public()) for a in sg.gateway.approvals.for_session(s.session_id)]


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, body: ApprovalDecision, request: Request):
    s = _mutating(request)
    sg = _ready(request)
    if not sg.settings.enable_approvals:
        raise HTTPException(404, {"error": "APPROVALS_DISABLED"})
    req, code = sg.gateway.approvals.decide(approval_id, s.session_id, body.decision)
    if req is None:
        raise HTTPException(404, {"error": "NOT_FOUND"})
    if code != "OK":
        raise HTTPException(409, {"error": code})
    sg.orchestrator.notify_approval(req.task_id)
    return req.public()


@router.post("/demo/reset")
async def reset(request: Request):
    s = _mutating(request)
    sg = _ready(request)
    active = sg.orchestrator.active_task_id
    if active and sg.orchestrator.tasks[active].status != TaskStatus.AWAITING_APPROVAL:
        raise HTTPException(409, {"error": "TASK_RUNNING", "message": "Reset is unavailable while a task runs."})
    if active:
        rec = sg.orchestrator.tasks[active]
        sg.orchestrator._block(rec, "CANCELLED_BY_RESET", TaskStatus.CANCELLED, "Cancelled by demo reset.")
        sg.orchestrator.notify_approval(active)
    from backend.app.main import read_fixture_meta
    from scripts.reset_demo import reset as reset_fixture

    counts = reset_fixture()
    await sg.gateway.upstream.restart()
    sg.gateway.grants.clear()
    sg.gateway.approvals.clear()
    sg.gateway.audit.clear()
    sg.gateway.run_metrics.clear()
    sg.orchestrator.tasks.clear()
    sg.boundary.measurements.clear()
    sg.fixture = read_fixture_meta()
    persona = s.principal.role
    sg.sessions.clear()
    return {"reset": True, "customers": counts["customers"], "sales": counts["sales"],
            "previous_persona": persona.value, "message": "All sessions, grants, approvals, tasks and audit cleared."}
