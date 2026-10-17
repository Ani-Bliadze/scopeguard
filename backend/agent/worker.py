"""Agent MCP execution worker (separate process).

Receives one bounded request on stdin: fixed gateway URL, opaque run token and the selected steps.
It holds no database path, upstream handles, backend or LLM credentials, cookies, shell or HTTP tools.
Its only network destination is the ScopeGuard gateway's MCP endpoint, via a real MCP client."""

from __future__ import annotations

import asyncio
import json
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from backend.agent.protocol import MAX_WORKER_OUTPUT_BYTES, WorkerRequest, WorkerResponse, WorkerStepResult


def _error_code(result) -> str:
    try:
        return str(json.loads(result.content[0].text).get("error", "TOOL_ERROR"))[:64]
    except Exception:
        return "TOOL_ERROR"


async def run(req: WorkerRequest) -> WorkerResponse:
    resp = WorkerResponse(run_id=req.run_id)
    headers = {"Authorization": f"Bearer {req.token}"}
    async with httpx2.AsyncClient(headers=headers, timeout=20.0, follow_redirects=False) as http:
        async with Client(streamable_http_client(req.gateway_url, http_client=http), read_timeout_seconds=20) as client:
            resp.protocol_version = client.protocol_version
            listing = await client.list_tools()
            resp.listed_tools = sorted(t.name for t in listing.tools)
            for step in req.steps:
                result = await client.call_tool(step.tool_id, step.arguments)
                if result.is_error:
                    resp.results.append(WorkerStepResult(step_id=step.step_id, tool_id=step.tool_id, ok=False,
                                                         error_code=_error_code(result)))
                    break
                resp.results.append(WorkerStepResult(step_id=step.step_id, tool_id=step.tool_id, ok=True,
                                                     structured=result.structured_content))
    return resp


def main() -> None:
    raw = sys.stdin.buffer.read(64 * 1024)
    try:
        req = WorkerRequest.model_validate_json(raw)
    except Exception:
        out = WorkerResponse(run_id="unknown", error_code="WORKER_BAD_REQUEST")
    else:
        try:
            out = asyncio.run(run(req))
        except Exception:
            out = WorkerResponse(run_id=req.run_id, error_code="WORKER_MCP_FAILURE")
    data = out.model_dump_json().encode()
    if len(data) > MAX_WORKER_OUTPUT_BYTES:
        data = WorkerResponse(run_id=out.run_id, error_code="WORKER_OUTPUT_TOO_LARGE").model_dump_json().encode()
    sys.stdout.buffer.write(data)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
