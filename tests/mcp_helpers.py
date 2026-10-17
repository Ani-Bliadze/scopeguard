"""Helpers that speak real MCP to the gateway over Streamable HTTP (same transport as the agent worker)."""

from __future__ import annotations

import asyncio

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

SUMMARY = {"month": "2026-09", "group_by": "region", "metric": "total_revenue"}


def mint(ls, *, role="sales_analyst", intent="SALES_BY_REGION_2026_09", steps=None, ttl=30.0, approval_id=None,
         task_id="test-task"):
    gw = ls.sg.gateway
    steps = steps if steps is not None else [("analytics.get_sales_summary", SUMMARY)]
    return gw.grants.mint(session_id="test-session", principal_id=f"test-{role}", role=role, task_id=task_id,
                          intent=intent, config_digest=gw.config.combined_digest, steps=steps, ttl_s=ttl,
                          approval_id=approval_id)


async def _session(ls, token, fn):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx2.AsyncClient(headers=headers, timeout=20) as http:
        async with Client(streamable_http_client(f"http://127.0.0.1:{ls.port}/mcp/", http_client=http)) as c:
            return await fn(c)


def call(ls, token, tool, args):
    async def fn(c):
        return await c.call_tool(tool, args)

    return asyncio.run(_session(ls, token, fn))


def calls(ls, token, seq):
    async def fn(c):
        return [await c.call_tool(t, a) for t, a in seq]

    return asyncio.run(_session(ls, token, fn))


def session(ls, token, fn):
    return asyncio.run(_session(ls, token, fn))
