"""Full protected topology: MCP client --Streamable HTTP--> ScopeGuard gateway --stdio--> private upstream."""

import pytest

from tests.mcp_helpers import SUMMARY, mint, session

pytestmark = pytest.mark.integration


def test_real_mcp_round_trip(live_server):
    token, grant = mint(live_server)
    up = live_server.sg.gateway.upstream
    before = up.dispatch_count("get_sales_summary")

    async def fn(c):
        listing = await c.list_tools()
        res = await c.call_tool("analytics.get_sales_summary", SUMMARY)
        return c.protocol_version, listing, res

    proto, listing, res = session(live_server, token, fn)
    assert proto == "2026-07-28"
    names = {t.name for t in listing.tools}
    assert names == {"crm.get_customers", "analytics.get_transactions", "analytics.get_sales_summary",
                     "crm.get_connection_status", "crm.get_customer_contact"}
    assert "crm.get_internal_secret" not in names and "get_customers" not in names
    assert res.is_error is False and len(res.structured_content["rows"]) == 4
    assert set(res.structured_content) == {"month", "group_by", "metric", "currency", "rows"}
    assert up.dispatch_count("get_sales_summary") == before + 1
    assert live_server.sg.gateway.run_metrics[grant.run_id].outputs_accepted == 1


def test_gateway_tool_schemas_come_from_trusted_registry(live_server):
    token, _ = mint(live_server)
    listing = session(live_server, token, lambda c: c.list_tools())
    summary = next(t for t in listing.tools if t.name == "analytics.get_sales_summary")
    assert summary.input_schema["additionalProperties"] is False
    assert summary.description.startswith("Aggregated sales metric per region")


def test_unauthenticated_requests_never_reach_mcp(live_server):
    import httpx

    r = httpx.post(f"http://127.0.0.1:{live_server.port}/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401 and r.json() == {"error": "MISSING_TOKEN"}
    r = httpx.post(f"http://127.0.0.1:{live_server.port}/mcp/", headers={"Authorization": "Bearer forged-token-0000000000"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401 and r.json() == {"error": "INVALID_TOKEN"}
