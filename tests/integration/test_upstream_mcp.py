"""Private upstream servers over REAL stdio MCP (protocol discovery, tools/list, tools/call)."""

import asyncio
import sqlite3
import sys

import pytest
from mcp import Client, StdioServerParameters

from backend.settings import DB_PATH, PROJECT_ROOT, read_backend_credential

pytestmark = pytest.mark.integration


def params(module, credential=None):
    env = {"SCOPEGUARD_DB": str(DB_PATH)}
    if credential is not None:
        env["SCOPEGUARD_CRM_CREDENTIAL"] = credential
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=env, cwd=str(PROJECT_ROOT))


async def _run(module, fn, credential=None):
    async with Client(params(module, credential)) as c:
        return await fn(c)


def test_both_upstreams_list_tools_over_stdio(fixture_db):
    crm = asyncio.run(_run("mcp_servers.crm_server", lambda c: c.list_tools()))
    ana = asyncio.run(_run("mcp_servers.analytics_server", lambda c: c.list_tools()))
    assert sorted(t.name for t in crm.tools) == ["get_connection_status", "get_customer_contact", "get_customers"]
    assert sorted(t.name for t in ana.tools) == ["get_sales_summary", "get_transactions"]
    assert "get_internal_secret" not in {t.name for t in crm.tools}


def test_aggregate_over_mcp_equals_independent_sql(fixture_db):
    res = asyncio.run(_run("mcp_servers.analytics_server", lambda c: c.call_tool(
        "get_sales_summary", {"month": "2026-09", "group_by": "region", "metric": "total_revenue"})))
    assert res.is_error is False
    con = sqlite3.connect(DB_PATH)
    expected = dict(con.execute("SELECT c.region, SUM(s.amount_cents) FROM sales s JOIN customers c ON c.id=s.customer_id "
                                "WHERE s.month='2026-09' GROUP BY c.region").fetchall())
    con.close()
    got = {r["region"]: r["value_cents"] for r in res.structured_content["rows"]}
    assert got == expected and len(got) == 4


def test_broad_private_crm_tool_works_only_in_private_fixture(fixture_db):
    # Values inspected in memory only; nothing printed.
    res = asyncio.run(_run("mcp_servers.crm_server", lambda c: c.call_tool(
        "get_customers", {"fields": ["id", "email"], "limit": 5000})))
    assert res.structured_content["row_count"] == 5000


@pytest.mark.parametrize("cred,expected", [("correct", True), ("wrong", False), (None, False)])
def test_connection_status_uses_backend_credential(fixture_db, cred, expected):
    value = {"correct": read_backend_credential(), "wrong": "SCOPEGUARD_TEST_SECRET_wrong", None: ""}[cred]
    res = asyncio.run(_run("mcp_servers.crm_server", lambda c: c.call_tool("get_connection_status", {}), value))
    assert res.structured_content == {"connector": "crm", "connected": expected, "verification": "synthetic_local_digest"}
    assert "SCOPEGUARD_TEST_SECRET" not in res.content[0].text
