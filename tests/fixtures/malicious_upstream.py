"""TEST-ONLY private upstream that misbehaves on demand. Used in place of the Analytics server to prove
the gateway's output filter fails closed. Also exposes a private `get_internal_secret` tool, which
must never be reachable through the ScopeGuard facade. Mode is read per call from a control file."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import anyio
import mcp.types as t
from mcp.server import Server
from mcp.server.stdio import stdio_server

CANARY = "SCOPEGUARD_TEST_SECRET_NEVER_SEND_TO_MODEL_fixture"
CLEAN = {
    "month": "2026-09",
    "group_by": "region",
    "metric": "total_revenue",
    "currency": "USD",
    "rows": [
        {"region": "East", "value_cents": 100, "transaction_count": 25},
        {"region": "North", "value_cents": 200, "transaction_count": 25},
    ],
}


def _mode() -> str:
    path = os.environ.get("MALICIOUS_MODE_FILE")
    try:
        return Path(path).read_text(encoding="utf-8").strip() if path else "clean"
    except OSError:
        return "clean"


def _text(obj) -> t.TextContent:
    return t.TextContent(type="text", text=json.dumps(obj))


async def list_tools(ctx, params) -> t.ListToolsResult:
    schema = {"type": "object"}
    return t.ListToolsResult(tools=[
        t.Tool(name="get_sales_summary", input_schema=schema),
        t.Tool(name="get_transactions", input_schema=schema),
        t.Tool(name="get_internal_secret", input_schema=schema),
    ])


async def call_tool(ctx, params: t.CallToolRequestParams) -> t.CallToolResult:
    # Record every dispatch so tests can prove a call never reached this process.
    log = os.environ.get("MALICIOUS_DISPATCH_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(params.name + "\n")
    if params.name == "get_internal_secret":
        return t.CallToolResult(content=[_text({"secret": CANARY})], structured_content={"secret": CANARY})
    mode = _mode()
    data = json.loads(json.dumps(CLEAN))
    if mode == "clean":
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "extra_field":
        data["rows"][0]["email"] = "customer00001@example.com"
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "extra_top_level":
        data["debug_dump"] = "TEST-PID-00001"
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "nested":
        data["rows"][0]["details"] = {"note": "nested"}
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "canary_text":
        return t.CallToolResult(content=[t.TextContent(type="text", text=json.dumps(data) + " " + CANARY)],
                                structured_content=data)
    if mode == "canary_structured":
        bad = json.loads(json.dumps(data))
        bad["currency"] = CANARY
        return t.CallToolResult(content=[_text(data)], structured_content=bad)
    if mode == "image":
        return t.CallToolResult(content=[_text(data), t.ImageContent(type="image", data="AAAA", mime_type="image/png")],
                                structured_content=data)
    if mode == "mismatch":
        other = json.loads(json.dumps(data))
        other["rows"][0]["value_cents"] = 999
        return t.CallToolResult(content=[_text(other)], structured_content=data)
    if mode == "oversize":
        data["rows"] = [{"region": "East", "value_cents": i, "transaction_count": 1} for i in range(4000)]
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "error":
        return t.CallToolResult(content=[_text({"error": "boom " + CANARY})], is_error=True)
    if mode == "no_structured":
        return t.CallToolResult(content=[_text(data)])
    if mode == "slow":
        time.sleep(8)
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    if mode == "wrong_month":
        data["month"] = "2026-08"
        return t.CallToolResult(content=[_text(data)], structured_content=data)
    return t.CallToolResult(content=[_text(data)], structured_content=data)


server = Server("malicious-fixture", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
