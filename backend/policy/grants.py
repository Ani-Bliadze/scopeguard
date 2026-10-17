"""Server-owned execution grants and one-time scoped approvals.

Bearer tokens are random and opaque; only their SHA-256 hashes are retained. A grant binds session,
principal, task, run, config digest and the exact canonical selected steps. Each step is consumed
atomically at dispatch and is never replenished on failure."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def step_hash(tool_id: str, args: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({"tool": tool_id, "args": args}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class ExecutionGrant:
    grant_id: str
    session_id: str
    principal_id: str
    role: str
    task_id: str
    run_id: str
    intent: str
    config_digest: str
    created_at: float
    expires_at: float
    pending_steps: list[str]
    consumed_steps: list[str] = field(default_factory=list)
    approval_id: str | None = None
    status: str = "ACTIVE"  # ACTIVE | COMPLETED | REVOKED


class GrantStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_token: dict[str, ExecutionGrant] = {}

    def mint(
        self,
        *,
        session_id: str,
        principal_id: str,
        role: str,
        task_id: str,
        intent: str,
        config_digest: str,
        steps: list[tuple[str, dict[str, Any]]],
        ttl_s: float = 45.0,
        approval_id: str | None = None,
    ) -> tuple[str, ExecutionGrant]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        grant = ExecutionGrant(
            grant_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            principal_id=principal_id,
            role=role,
            task_id=task_id,
            run_id=uuid.uuid4().hex[:12],
            intent=intent,
            config_digest=config_digest,
            created_at=now,
            expires_at=now + ttl_s,
            pending_steps=[step_hash(t, a) for t, a in steps],
            approval_id=approval_id,
        )
        with self._lock:
            self._by_token[_token_hash(token)] = grant
        return token, grant

    def resolve(self, token: str | None, config_digest: str) -> tuple[ExecutionGrant | None, str]:
        if not token:
            return None, "MISSING_TOKEN"
        with self._lock:
            grant = self._by_token.get(_token_hash(token))
            if grant is None:
                return None, "INVALID_TOKEN"
            if grant.status != "ACTIVE":
                return None, "GRANT_NOT_ACTIVE"
            if time.time() > grant.expires_at:
                grant.status = "REVOKED"
                return None, "GRANT_EXPIRED"
            if grant.config_digest != config_digest:
                grant.status = "REVOKED"
                return None, "POLICY_CHANGED_SINCE_GRANT"
            return grant, "OK"

    def consume_step(self, grant: ExecutionGrant, tool_id: str, args: dict[str, Any]) -> bool:
        h = step_hash(tool_id, args)
        with self._lock:
            if grant.status != "ACTIVE" or time.time() > grant.expires_at:
                return False
            if h not in grant.pending_steps:
                return False
            grant.pending_steps.remove(h)
            grant.consumed_steps.append(h)
            return True

    def complete(self, grant: ExecutionGrant) -> None:
        with self._lock:
            if grant.status == "ACTIVE":
                grant.status = "COMPLETED"

    def revoke_session(self, session_id: str) -> int:
        n = 0
        with self._lock:
            for g in self._by_token.values():
                if g.session_id == session_id and g.status == "ACTIVE":
                    g.status = "REVOKED"
                    n += 1
        return n

    def clear(self) -> None:
        with self._lock:
            for g in self._by_token.values():
                g.status = "REVOKED"
            self._by_token.clear()


@dataclass
class ApprovalRequest:
    approval_id: str
    session_id: str
    principal_id: str
    task_id: str
    intent: str
    tool_id: str
    resource: dict[str, Any]
    fields: list[str]
    purpose: str
    created_at: float
    expires_at: float
    single_use: bool = True
    status: str = "PENDING"  # PENDING | APPROVED | DENIED | EXPIRED | CONSUMED

    def public(self) -> dict[str, Any]:
        self._refresh()
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "tool_id": self.tool_id,
            "resource": self.resource,
            "fields": self.fields,
            "purpose": self.purpose,
            "single_use": self.single_use,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }

    def _refresh(self) -> None:
        if self.status in ("PENDING", "APPROVED") and time.time() > self.expires_at:
            self.status = "EXPIRED"


class ApprovalStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, ApprovalRequest] = {}

    def create(self, **kw) -> ApprovalRequest:
        ttl = kw.pop("ttl_s")
        now = time.time()
        req = ApprovalRequest(approval_id=uuid.uuid4().hex[:12], created_at=now, expires_at=now + ttl, **kw)
        with self._lock:
            self._items[req.approval_id] = req
        return req

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            req = self._items.get(approval_id)
            if req:
                req._refresh()
            return req

    def for_session(self, session_id: str) -> list[ApprovalRequest]:
        with self._lock:
            out = [r for r in self._items.values() if r.session_id == session_id]
            for r in out:
                r._refresh()
            return out

    def decide(self, approval_id: str, session_id: str, decision: str) -> tuple[ApprovalRequest | None, str]:
        with self._lock:
            req = self._items.get(approval_id)
            if req is None or req.session_id != session_id:
                return None, "NOT_FOUND"
            req._refresh()
            if req.status != "PENDING":
                return req, f"NOT_PENDING_{req.status}"
            req.status = "APPROVED" if decision == "approve" else "DENIED"
            return req, "OK"

    def consume(
        self, approval_id: str | None, *, principal_id: str, task_id: str, tool_id: str, args: dict[str, Any]
    ) -> tuple[bool, str]:
        """Atomically verify the binding and consume a single-use approval."""
        if not approval_id:
            return False, "APPROVAL_MISSING"
        with self._lock:
            req = self._items.get(approval_id)
            if req is None:
                return False, "APPROVAL_MISSING"
            req._refresh()
            if req.status == "EXPIRED":
                return False, "APPROVAL_EXPIRED"
            if req.status == "CONSUMED":
                return False, "APPROVAL_ALREADY_USED"
            if req.status != "APPROVED":
                return False, "APPROVAL_NOT_GRANTED"
            if req.principal_id != principal_id or req.task_id != task_id or req.tool_id != tool_id:
                return False, "APPROVAL_BINDING_MISMATCH"
            for k, v in req.resource.items():
                if args.get(k) != v:
                    return False, "APPROVAL_BINDING_MISMATCH"
            if list(args.get("fields", [])) != req.fields:
                return False, "APPROVAL_BINDING_MISMATCH"
            if req.single_use:
                req.status = "CONSUMED"
            return True, "OK"

    def peek_valid(self, approval_id: str | None) -> bool:
        if not approval_id:
            return False
        req = self.get(approval_id)
        return req is not None and req.status == "APPROVED"

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
