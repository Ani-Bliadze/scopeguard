"""ScopeGuard's exposed MCP server: the only MCP endpoint the agent can reach.

Every tools/call is re-authorized here, independently of the planner: bearer -> server-owned grant,
trusted registry lookup, strict argument validation, pure policy evaluation, exact step binding,
scoped approval consumption, then a bounded upstream call and complete output filtering. Only a
freshly constructed safe result is returned. Resources, prompts and other surfaces are not served."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import mcp.types as t
from mcp.server import Server, ServerRequestContext
from pydantic import ValidationError

from backend.contracts import Decision, EventType
from backend.gateway.output_filter import filter_result
from backend.gateway.upstream import UpstreamError, UpstreamManager
from backend.observability.audit import AuditEvent, AuditLog, pseudonym
from backend.policy import engine
from backend.policy.grants import ApprovalStore, ExecutionGrant, GrantStore
from backend.policy.registry import TrustedConfig
from backend.tool_schemas import SCHEMAS, input_json_schema

MAX_ARGUMENT_BYTES = 8 * 1024


def bearer_from_headers(headers: Any) -> str | None:
    if headers is None:
        return None
    value = headers.get("authorization") or ""
    if not value.lower().startswith("bearer "):
        return None
    return value[7:].strip() or None


@dataclass
class RunMetrics:
    mcp_calls: int = 0
    gateway_calls_denied: int = 0
    upstream_dispatches: int = 0
    outputs_accepted: int = 0
    outputs_denied: int = 0
    deny_reasons: list[str] = field(default_factory=list)


@dataclass
class Gateway:
    config: TrustedConfig
    grants: GrantStore
    approvals: ApprovalStore
    audit: AuditLog
    upstream: UpstreamManager
    run_metrics: dict[str, RunMetrics] = field(default_factory=dict)
    server: Server | None = None

    def __post_init__(self) -> None:
        self.server = Server(
            "scopeguard-gateway",
            version="1.0.0",
            description="ScopeGuard enforcement facade (registered tools only).",
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
            get_tool_input_schema=self._input_schema,
        )

    # ---------------------------------------------------------------- discovery
    def _input_schema(self, name: str):
        return input_json_schema(name) if self.config.tool(name) else None

    def catalog(self) -> list[t.Tool]:
        return [
            t.Tool(name=e.tool_id, description=e.description, input_schema=input_json_schema(e.tool_id))
            for e in self.config.registry.tools
        ]

    async def _list_tools(self, ctx: ServerRequestContext, params) -> t.ListToolsResult:
        grant, _ = self.grants.resolve(bearer_from_headers(getattr(ctx.request, "headers", None)), self.config.combined_digest)
        if grant is None:
            return t.ListToolsResult(tools=[])
        return t.ListToolsResult(tools=self.catalog())

    # ---------------------------------------------------------------- enforcement
    def _event(self, grant: ExecutionGrant | None, stage: EventType, **kw) -> None:
        self.audit.record(
            AuditEvent(
                task_id=grant.task_id if grant else "unauthenticated",
                run_id=grant.run_id if grant else None,
                principal=pseudonym(grant.principal_id) if grant else "anonymous",
                stage=stage,
                **kw,
            )
        )

    def _deny(self, grant: ExecutionGrant | None, tool_id: str, code: str, message: str) -> t.CallToolResult:
        if grant is not None:
            m = self.run_metrics.setdefault(grant.run_id, RunMetrics())
            m.gateway_calls_denied += 1
            m.deny_reasons.append(code)
        self._event(grant, EventType.POLICY_DECISION, tool_id=tool_id[:64], decision="DENY", reason_code=code, message=message)
        payload = {"error": code, "message": message}
        return t.CallToolResult(content=[t.TextContent(type="text", text=json.dumps(payload))], is_error=True)

    async def _call_tool(self, ctx: ServerRequestContext, params: t.CallToolRequestParams) -> t.CallToolResult:
        grant: ExecutionGrant | None = None
        tool_id = str(params.name)[:64]
        try:
            grant, why = self.grants.resolve(
                bearer_from_headers(getattr(ctx.request, "headers", None)), self.config.combined_digest
            )
            if grant is None:
                return self._deny(None, tool_id, why, "Request is not bound to an active execution grant.")
            return await self.handle_call(grant, tool_id, dict(params.arguments or {}))
        except Exception:
            return self._deny(grant, tool_id, "GATEWAY_FAULT", "The gateway failed closed.")

    async def handle_call(self, grant: ExecutionGrant, tool_id: str, raw_args: dict[str, Any]) -> t.CallToolResult:
        metrics = self.run_metrics.setdefault(grant.run_id, RunMetrics())
        metrics.mcp_calls += 1
        self._event(
            grant,
            EventType.MCP_REQUEST,
            tool_id=tool_id,
            fields=sorted(str(k)[:40] for k in raw_args)[:12],
            message="tools/call received by ScopeGuard gateway",
        )
        entry = self.config.tool(tool_id)
        if entry is None or tool_id not in SCHEMAS:
            return self._deny(grant, tool_id, "UNKNOWN_TOOL", "Tool is not in the trusted registry.")
        if len(json.dumps(raw_args, default=str).encode()) > MAX_ARGUMENT_BYTES:
            return self._deny(grant, tool_id, "ARGUMENTS_TOO_LARGE", "Arguments exceed the size limit.")
        try:
            model = SCHEMAS[tool_id][0].model_validate(raw_args)
        except ValidationError:
            # Never echo validation details: they can contain rejected values.
            return self._deny(grant, tool_id, "INVALID_ARGUMENTS", "Arguments do not match the trusted schema.")
        args = model.model_dump(mode="json", exclude_none=True)

        approval_valid = self.approvals.peek_valid(grant.approval_id)
        decision = engine.evaluate(self.config, grant.role, grant.intent, tool_id, args, approval_valid=approval_valid)
        if decision.decision != Decision.ALLOW:
            return self._deny(grant, tool_id, decision.reason_code, decision.message)
        if not self.grants.consume_step(grant, tool_id, args):
            return self._deny(grant, tool_id, "STEP_NOT_IN_GRANT", "Call does not match an unconsumed approved plan step.")
        if entry.approval_mode == "single_use_scoped":
            ok, code = self.approvals.consume(
                grant.approval_id, principal_id=grant.principal_id, task_id=grant.task_id, tool_id=tool_id, args=args
            )
            if not ok:
                return self._deny(grant, tool_id, code, "Scoped approval is missing, expired, used or mismatched.")
        self._event(
            grant,
            EventType.POLICY_DECISION,
            tool_id=tool_id,
            decision="ALLOW",
            reason_code=decision.reason_code,
            fields=decision.approved_fields,
            classes=sorted({entry.fields[f].class_.value for f in decision.approved_fields if f in entry.fields}),
            message=decision.message,
        )

        try:
            result = await self.upstream.call(entry.server_id, entry.upstream_name, args, grant.task_id)
        except UpstreamError as exc:
            metrics.upstream_dispatches += 1
            return self._deny(grant, tool_id, str(exc), "Upstream failed; no partial data is returned.")
        metrics.upstream_dispatches += 1
        self._event(grant, EventType.UPSTREAM_DISPATCH, tool_id=tool_id, message=f"private {entry.server_id} MCP server (stdio)")

        task_policy = self.config.policy.tasks[grant.intent]
        outcome = filter_result(entry, args, result, set(task_policy.model_visible_classes), decision.approved_fields)
        del result  # the raw upstream envelope is never forwarded
        if outcome.accepted is None:
            metrics.outputs_denied += 1
            self._event(grant, EventType.OUTPUT_DENIED, tool_id=tool_id, decision="DENY", reason_code=outcome.reason_code,
                        message="Upstream output rejected before reaching the agent.")
            m = self.run_metrics[grant.run_id]
            m.gateway_calls_denied += 1
            m.deny_reasons.append(outcome.reason_code)
            payload = {"error": outcome.reason_code, "message": "Output rejected by ScopeGuard output filter."}
            return t.CallToolResult(content=[t.TextContent(type="text", text=json.dumps(payload))], is_error=True)
        metrics.outputs_accepted += 1
        self._event(
            grant,
            EventType.OUTPUT_ACCEPTED,
            tool_id=tool_id,
            decision="ALLOW",
            reason_code=outcome.reason_code,
            fields=outcome.fields,
            classes=sorted({entry.fields[f].class_.value for f in outcome.fields if f in entry.fields}),
            counts=outcome.counts,
            message="Validated, projected result constructed for the agent.",
        )
        safe = outcome.accepted
        return t.CallToolResult(
            content=[t.TextContent(type="text", text=json.dumps(safe, separators=(",", ":")))],
            structured_content=safe,
            is_error=False,
        )
