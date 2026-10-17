"""Runtime enforcement at the real MCP gateway, independent of the planner."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from mcp.shared.exceptions import MCPError

from backend.settings import RUNTIME_DIR
from tests.mcp_helpers import SUMMARY, call, calls, mint, session

pytestmark = pytest.mark.security


def err(res):
    assert res.is_error is True
    return json.loads(res.content[0].text)["error"]


def test_broad_crm_tool_denied_for_sales_task(live_server):
    up = live_server.sg.gateway.upstream
    before = up.dispatch_count()
    token, grant = mint(live_server)
    res = call(live_server, token, "crm.get_customers",
               {"fields": ["id", "region", "email", "synthetic_personal_id", "total_spend_cents"], "limit": 5000,
                "month": "2026-09"})
    assert err(res) == "TOOL_NOT_ALLOWED_FOR_TASK"
    assert up.dispatch_count() == before  # zero upstream dispatches: the 5,000-row request never reached CRM
    assert live_server.sg.gateway.run_metrics[grant.run_id].gateway_calls_denied == 1


def test_unknown_tool_default_deny(live_server):
    up = live_server.sg.gateway.upstream
    before = up.dispatch_count()
    token, _ = mint(live_server)
    for name in ["crm.get_internal_secret", "get_customers", "analytics.run_sql", "../crm.get_customers"]:
        assert err(call(live_server, token, name, {})) == "UNKNOWN_TOOL"
    assert up.dispatch_count() == before


def test_unsupported_mcp_methods_rejected(live_server):
    token, _ = mint(live_server)

    async def fn(c):
        out = []
        for factory in (lambda: c.read_resource("file:///etc/passwd"), c.list_prompts, c.list_resources):
            try:
                await factory()
                out.append("served")
            except MCPError:
                out.append("rejected")
        return out

    assert session(live_server, token, fn) == ["rejected", "rejected", "rejected"]


@pytest.mark.parametrize("args", [
    {**SUMMARY, "personal_id": "TEST-PID-00001"},
    {**SUMMARY, "fields": ["email"]},
    {**SUMMARY, "group_by": "customer_id"},
    {**SUMMARY, "month": 202609},
    {**SUMMARY, "nested": {"role": "admin"}},
])
def test_extra_fields_denied(live_server, args):
    up = live_server.sg.gateway.upstream
    before = up.dispatch_count()
    token, _ = mint(live_server)
    assert err(call(live_server, token, "analytics.get_sales_summary", args)) == "INVALID_ARGUMENTS"
    assert up.dispatch_count() == before


def test_secret_value_hard_deny(live_server, canary):
    token, _ = mint(live_server, intent="SECRET_DISCLOSURE_ATTEMPT", steps=[])
    res = call(live_server, token, "crm.get_connection_status", {})
    assert err(res) == "HARD_DENY_SECRET_DISCLOSURE"
    res2 = call(live_server, token, "crm.get_internal_secret", {})
    assert err(res2) == "UNKNOWN_TOOL"
    assert canary not in res.content[0].text + res2.content[0].text


def test_backend_secret_used_without_exposure(live_server, canary):
    token, _ = mint(live_server, intent="CRM_CONNECTION_STATUS", steps=[("crm.get_connection_status", {})])
    res = call(live_server, token, "crm.get_connection_status", {})
    assert res.structured_content == {"connector": "crm", "connected": True, "verification": "synthetic_local_digest"}
    assert canary not in json.dumps(res.model_dump(mode="json"))
    log = RUNTIME_DIR / "upstream-stderr.log"
    assert canary not in log.read_text(encoding="utf-8", errors="ignore")


def test_task_binding_prevents_scope_escapes(live_server):
    up = live_server.sg.gateway.upstream
    before = up.dispatch_count()
    token, _ = mint(live_server)
    # a sales grant cannot read a contact even with plausible args
    assert err(call(live_server, token, "crm.get_customer_contact", {"customer_id": 105, "fields": ["email"]})) == "TOOL_NOT_ALLOWED_FOR_TASK"
    # forged role/task in arguments are schema violations, never authority
    assert err(call(live_server, token, "analytics.get_sales_summary", {**SUMMARY, "role": "customer_support"})) == "INVALID_ARGUMENTS"
    # a support grant for customer 105 cannot be pointed at customer 106
    t2, _ = mint(live_server, role="customer_support", intent="NOTIFY_CUSTOMER_105",
                 steps=[("crm.get_customer_contact", {"customer_id": 105, "fields": ["email"]})])
    assert err(call(live_server, t2, "crm.get_customer_contact", {"customer_id": 106, "fields": ["email"]})) == "ARGUMENT_OUT_OF_SCOPE"
    # without an approval the support grant gets APPROVAL_REQUIRED, not data
    assert err(call(live_server, t2, "crm.get_customer_contact", {"customer_id": 105, "fields": ["email"]})) == "APPROVAL_REQUIRED"
    assert up.dispatch_count() == before


def test_step_binding_and_replay(live_server):
    token, _ = mint(live_server)
    first, second = calls(live_server, token, [("analytics.get_sales_summary", SUMMARY)] * 2)
    assert first.is_error is False and err(second) == "STEP_NOT_IN_GRANT"


def test_concurrent_consumption_dispatches_at_most_once(live_server):
    up = live_server.sg.gateway.upstream
    token, _ = mint(live_server)
    before = up.dispatch_count("get_sales_summary")
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda _: call(live_server, token, "analytics.get_sales_summary", SUMMARY), range(4)))
    assert sum(1 for r in results if not r.is_error) == 1
    assert up.dispatch_count("get_sales_summary") == before + 1


def test_expired_completed_and_policy_changed_grants(live_server):
    base = f"http://127.0.0.1:{live_server.port}/mcp/"
    token, _ = mint(live_server, ttl=0.3)
    time.sleep(0.6)
    r = httpx.post(base, headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 401 and r.json()["error"] == "GRANT_EXPIRED"
    token2, grant2 = mint(live_server)
    live_server.sg.gateway.grants.complete(grant2)
    r = httpx.post(base, headers={"Authorization": f"Bearer {token2}"}, json={})
    assert r.status_code == 401 and r.json()["error"] == "GRANT_NOT_ACTIVE"
    gw = live_server.sg.gateway
    token3, _ = gw.grants.mint(session_id="s", principal_id="p", role="sales_analyst", task_id="t",
                               intent="SALES_BY_REGION_2026_09", config_digest="stale-digest", steps=[])
    r = httpx.post(base, headers={"Authorization": f"Bearer {token3}"}, json={})
    assert r.status_code == 401 and r.json()["error"] == "POLICY_CHANGED_SINCE_GRANT"
    r = httpx.post(base, headers={"Authorization": "Bearer forged-token-forged-token-forged"}, json={})
    assert r.status_code == 401 and r.json()["error"] == "INVALID_TOKEN"


def test_host_origin_and_body_limits(live_server):
    token, _ = mint(live_server)
    base = f"http://127.0.0.1:{live_server.port}/mcp/"
    h = {"Authorization": f"Bearer {token}"}
    assert httpx.post(base, headers={**h, "Host": "evil.example"}, json={}).status_code == 421
    assert httpx.post(base, headers={**h, "Origin": "https://evil.example"}, json={}).status_code == 403
    big = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "x", "arguments": {"a": "x" * 40000}}}
    assert httpx.post(base, headers=h, json=big).status_code == 413


OUTPUT_CASES = [
    ("extra_field", "OUTPUT_SCHEMA_VIOLATION"), ("extra_top_level", "OUTPUT_SCHEMA_VIOLATION"),
    ("nested", "OUTPUT_SCHEMA_VIOLATION"), ("canary_text", "SECRET_PATTERN_IN_OUTPUT"),
    ("canary_structured", "SECRET_PATTERN_IN_OUTPUT"), ("image", "UNEXPECTED_CONTENT_BLOCKS"),
    ("mismatch", "CHANNEL_MISMATCH"), ("error", "UPSTREAM_ERROR_RESULT"),
    ("no_structured", "MISSING_STRUCTURED_OUTPUT"), ("wrong_month", "OUTPUT_SCOPE_MISMATCH"),
    ("oversize", None),
]


@pytest.mark.parametrize("mode,code", OUTPUT_CASES)
def test_unexpected_output_fails_closed(malicious_server, mode, code):
    ls = malicious_server
    ls.mode_file.write_text(mode, encoding="utf-8")
    try:
        token, _ = mint(ls)
        res = call(ls, token, "analytics.get_sales_summary", SUMMARY)
        got = err(res)
        assert code is None or got == code, (mode, got)
        assert "SCOPEGUARD_TEST_SECRET" not in res.content[0].text and "@example.com" not in res.content[0].text
    finally:
        ls.mode_file.write_text("clean", encoding="utf-8")


def test_upstream_timeout_fails_closed_without_retry(malicious_server):
    ls = malicious_server
    ls.mode_file.write_text("slow", encoding="utf-8")
    try:
        token, _ = mint(ls)
        before = ls.dispatch_log.read_text().count("get_sales_summary")
        res = call(ls, token, "analytics.get_sales_summary", SUMMARY)
        assert err(res) == "UPSTREAM_TIMEOUT"
        time.sleep(3.5)
        assert ls.dispatch_log.read_text().count("get_sales_summary") == before + 1  # no automatic retry
    finally:
        ls.mode_file.write_text("clean", encoding="utf-8")
        time.sleep(1)


def test_private_secret_tool_unreachable_through_facade(malicious_server):
    ls = malicious_server
    token, _ = mint(ls)
    before = ls.dispatch_log.read_text()
    assert err(call(ls, token, "crm.get_internal_secret", {})) == "UNKNOWN_TOOL"
    assert err(call(ls, token, "analytics.get_internal_secret", {})) == "UNKNOWN_TOOL"
    assert "get_internal_secret" not in ls.dispatch_log.read_text()[len(before):]


def test_contaminated_result_never_reaches_model(malicious_server):
    ls = malicious_server
    rec = ls.sg.boundary.enable_recording()
    ls.mode_file.write_text("canary_text", encoding="utf-8")
    try:
        c = ls.client()
        c.persona("sales_analyst")
        t = c.run("Summarize September sales by region.")
    finally:
        ls.mode_file.write_text("clean", encoding="utf-8")
    assert t["status"] == "FAILED" and t["metrics"]["task_completed"] is False
    assert not [r for r in rec if r["phase"] == "answer"]  # nothing dispatched to the answer model
    assert all("SCOPEGUARD_TEST_SECRET" not in r["payload"] for r in rec)
