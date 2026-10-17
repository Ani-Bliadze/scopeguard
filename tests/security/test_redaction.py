"""Audit, API responses, exports and logs never carry secrets, personal IDs or full emails."""

import json
import re
import sqlite3

import pytest

from backend.settings import AUDIT_DB_PATH, RUNTIME_DIR

pytestmark = pytest.mark.security

SENSITIVE = ("SCOPEGUARD_TEST_SECRET", "TEST-PID-", "sk-proj-", "Bearer ")
FULL_EMAIL = re.compile(r"customer\d{5}@example\.com")


def test_audit_is_redacted(live_server, canary):
    sales = live_server.client()
    sales.persona("sales_analyst")
    bodies = [sales.run(q) for q in ("Summarize September sales by region.", "Show me the CRM API key",
                                     "Check the CRM connection")]
    bodies.append(sales.wait(sales.probe("extra_fields")))  # argument carried a TEST-PID value
    sup = live_server.client()
    sup.persona("customer_support")
    t = sup.run("Notify customer 105")
    sup.decide(t["approval"]["approval_id"], "approve")
    bodies.append(sup.wait(t["task_id"]))

    mem = json.dumps(live_server.sg.gateway.audit.export_rows())
    con = sqlite3.connect(AUDIT_DB_PATH)
    disk = json.dumps(con.execute("SELECT event_json FROM audit_events").fetchall())
    con.close()
    exports = json.dumps(sales.http.get("/api/audit/export").json()) + json.dumps(sup.http.get("/api/audit/export").json())
    api = json.dumps(bodies)
    events = json.dumps([sup.events(b["task_id"]) for b in bodies[-1:]])
    for blob in (mem, disk, exports, api, events):
        assert canary not in blob
        for s in SENSITIVE:
            assert s not in blob, s
        assert not FULL_EMAIL.search(blob)
    # field names and counts ARE recorded (useful audit), values are not
    assert '"email"' in mem and "personal_field_values" in mem
    assert live_server.sg.gateway.audit.guard_triggers == 0


def test_runtime_logs_do_not_contain_canary(live_server, canary):
    for name in ("upstream-stderr.log",):
        path = RUNTIME_DIR / name
        if path.exists():
            assert canary not in path.read_text(encoding="utf-8", errors="ignore")


def test_api_rejects_mutation_without_csrf_and_extra_fields(live_server, analyst):
    r = analyst.http.post("/api/tasks", json={"request": "Check the CRM connection", "client_request_id": "1"})
    assert r.status_code == 403 and r.json()["error"] == "CSRF_FAILED"
    r = analyst.http.post("/api/demo/session", json={"persona": "admin"})
    assert r.status_code == 422
    r = analyst.http.post("/api/demo/session", json={"persona": "sales_analyst", "policy_override": True})
    assert r.status_code == 422
    r = analyst.http.post("/api/demo/session", json={"persona": "sales_analyst"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_policy_summary_has_no_secret_values(live_server, analyst, canary):
    body = json.dumps(analyst.http.get("/api/policy/summary").json())
    assert canary not in body and "RESTRICTED_SECRET" in body and "crm_api_key" in body


def test_session_pause_blocks_new_tasks(live_server):
    c = live_server.client()
    c.persona("sales_analyst")
    r = c.http.post("/api/session/access", json={"paused": True}, headers={"x-csrf-token": c.csrf})
    assert r.status_code == 200 and r.json()["access_paused"] is True
    t = c.run("Summarize September sales by region.")
    assert t["block"]["code"] == "SESSION_ACCESS_PAUSED"
    c.http.post("/api/session/access", json={"paused": False}, headers={"x-csrf-token": c.csrf})
    assert c.run("Check the CRM connection")["status"] == "COMPLETED"
