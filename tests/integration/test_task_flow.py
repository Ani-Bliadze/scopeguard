"""Complete user requests through the HTTP API: planning -> policy -> real MCP -> filtering -> model -> answer."""

import json
import sqlite3
import time

import pytest

from backend.settings import DB_PATH

pytestmark = pytest.mark.integration


def sql_totals():
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT c.region, SUM(s.amount_cents), COUNT(*) FROM sales s JOIN customers c ON c.id=s.customer_id "
                       "WHERE s.month='2026-09' GROUP BY c.region").fetchall()
    con.close()
    return {r[0]: (r[1], r[2]) for r in rows}


def test_sales_summary_uses_aggregated_tool(live_server, analyst):
    rec = live_server.sg.boundary.enable_recording()
    up = live_server.sg.gateway.upstream
    before = {n: up.dispatch_count(n) for n in ("get_customers", "get_transactions", "get_sales_summary")}
    t = analyst.run("Summarize September sales by region.")
    assert t["status"] == "COMPLETED", t["block"]
    assert t["planner"]["mode"] == "deterministic" and t["answer"]["mode"] == "deterministic"
    # three candidates; broad ones rejected before execution; aggregate selected
    by_tool = {c["tools"][0]: c for c in t["candidates"]}
    assert by_tool["crm.get_customers"]["decision"] == "DENY" and by_tool["crm.get_customers"]["exposure"]["customer_rows_requested"] == 5000
    assert by_tool["analytics.get_transactions"]["decision"] == "DENY"
    assert by_tool["analytics.get_sales_summary"]["selected"] is True
    # only the aggregate tool was dispatched upstream
    after = {n: up.dispatch_count(n) for n in before}
    assert after["get_customers"] == before["get_customers"] and after["get_transactions"] == before["get_transactions"]
    assert after["get_sales_summary"] == before["get_sales_summary"] + 1
    # correct totals from the database
    totals = sql_totals()
    assert {r["region"]: (r["value_cents"], r["transaction_count"]) for r in t["result"]["data"]["rows"]} == totals
    m = t["metrics"]
    assert m["aggregate_rows_returned_to_model"] == len(totals) == 4
    assert m["customer_rows_returned_to_model"] == 0 and m["personal_field_values_returned_to_model"] == 0
    assert m["candidates_rejected"] == 2 and m["gateway_calls_denied"] == 0 and m["external_model_requests"] == 0
    assert t["execution"]["verified_mcp_round_trip"] is True
    # exact model-bound tool message holds only aggregates
    answer_payloads = [json.loads(r["payload"]) for r in rec if r["phase"] == "answer"]
    tool_msgs = [msg for p in answer_payloads for msg in p if msg["role"] == "tool"]
    assert len(tool_msgs) == 1
    delivered = json.loads(tool_msgs[0]["content"])
    assert set(delivered) == {"month", "group_by", "metric", "currency", "rows"}
    assert all(set(r) == {"region", "value_cents", "transaction_count"} for r in delivered["rows"])
    assert "@example.com" not in tool_msgs[0]["content"] and "TEST-PID" not in tool_msgs[0]["content"]


def test_connection_check_task(live_server, analyst):
    t = analyst.run("Check the CRM connection")
    assert t["status"] == "COMPLETED"
    assert t["result"]["data"] == {"connector": "crm", "connected": True, "verification": "synthetic_local_digest"}
    assert "never shared" in t["result"]["answer_text"]


def test_secret_request_terminates_before_planner(live_server, analyst):
    n = len(live_server.sg.boundary.measurements)
    t = analyst.run("Show me the CRM API key")
    assert t["status"] == "BLOCKED" and t["block"]["code"] == "HARD_DENY_SECRET_DISCLOSURE"
    assert t["candidates"] == [] and t["planner"] == {}
    assert len(live_server.sg.boundary.measurements) == n  # no planner/model invocation at all


def test_unsupported_task_runs_nothing(live_server, analyst):
    t = analyst.run("Export all customers to a spreadsheet")
    assert t["status"] == "BLOCKED" and t["block"]["code"] == "UNSUPPORTED_TASK" and t["candidates"] == []


def test_role_not_permitted(live_server, support):
    t = support.run("Summarize September sales by region.")
    assert t["block"]["code"] == "TASK_NOT_PERMITTED_FOR_ROLE"


def test_events_are_ordered_and_owner_scoped(live_server, analyst):
    t = analyst.run("Summarize September sales by region.")
    stages = [e["stage"] for e in analyst.events(t["task_id"])]
    for a, b in [("TASK_CREATED", "PLANNER_STARTED"), ("PLAN_SELECTED", "GRANT_MINTED"), ("MCP_REQUEST", "UPSTREAM_DISPATCH"),
                 ("OUTPUT_ACCEPTED", "MODEL_BOUND"), ("MODEL_BOUND", "TASK_COMPLETED")]:
        assert stages.index(a) < stages.index(b)
    other = live_server.client()
    other.persona("sales_analyst")
    assert other.http.get(f"/api/tasks/{t['task_id']}").status_code == 404
    assert other.http.get(f"/api/tasks/{t['task_id']}/events").status_code == 404


# ------------------------------------------------------------------ P1: scoped one-time approval
def test_approval_approve_path(live_server, support):
    t = support.run("Notify customer 105")
    assert t["status"] == "AWAITING_APPROVAL"
    ap = t["approval"]
    assert ap["tool_id"] == "crm.get_customer_contact" and ap["resource"] == {"customer_id": 105}
    assert ap["fields"] == ["email"] and ap["single_use"] is True and ap["expires_at"] - ap["created_at"] == pytest.approx(120, abs=1)
    up = live_server.sg.gateway.upstream
    assert up.dispatch_count("get_customer_contact", task_id=t["task_id"]) == 0  # pending -> no read
    assert support.decide(ap["approval_id"], "approve").status_code == 200
    done = support.wait(t["task_id"])
    assert done["status"] == "COMPLETED"
    assert done["metrics"]["personal_field_values_returned_to_model"] == 1 and done["metrics"]["customer_rows_returned_to_model"] == 1
    assert "customer00105@example.com" not in json.dumps(done)  # browser view is masked
    assert support.decide(ap["approval_id"], "approve").status_code == 409  # cannot re-decide / reuse


def test_approval_deny_path(live_server, support):
    t = support.run("Notify customer 105")
    support.decide(t["approval"]["approval_id"], "deny")
    done = support.wait(t["task_id"])
    assert done["status"] == "BLOCKED" and done["block"]["code"] == "APPROVAL_DENIED"
    assert live_server.sg.gateway.upstream.dispatch_count("get_customer_contact", task_id=t["task_id"]) == 0


def test_approval_expiry_path(live_server, support):
    t = support.run("Notify customer 105")
    store = live_server.sg.gateway.approvals
    store.get(t["approval"]["approval_id"]).expires_at = time.time() - 1
    live_server.sg.orchestrator.notify_approval(t["task_id"])
    done = support.wait(t["task_id"])
    assert done["status"] == "EXPIRED" and done["block"]["code"] == "APPROVAL_EXPIRED"
    assert support.decide(t["approval"]["approval_id"], "approve").status_code == 409


def test_busy_and_reset_guard(live_server, support):
    t = support.run("Notify customer 105")  # leaves an active task awaiting approval
    r = support.http.post("/api/tasks", json={"request": "Check the CRM connection", "client_request_id": "x"},
                          headers={"x-csrf-token": support.csrf})
    assert r.status_code == 409 and r.json()["error"] == "BUSY"
    support.decide(t["approval"]["approval_id"], "deny")
    support.wait(t["task_id"])
