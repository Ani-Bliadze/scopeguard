"""Agent worker capability boundary and live-provider fallback behavior."""

import dataclasses
import json

import pytest
from pydantic import ValidationError

from backend.agent.protocol import WorkerRequest
from backend.app.orchestrator import worker_environment
from backend.planner import llm
from backend.planner.base import ProviderError

pytestmark = pytest.mark.security


def test_worker_environment_excludes_secrets(monkeypatch, canary):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-SHOULD-NOT-LEAK-0000000000")
    monkeypatch.setenv("SCOPEGUARD_CRM_CREDENTIAL", canary)
    monkeypatch.setenv("SCOPEGUARD_DB", "C:/secret/path.sqlite")
    env = worker_environment()
    blob = json.dumps(env)
    assert "OPENAI_API_KEY" not in env and "SCOPEGUARD_CRM_CREDENTIAL" not in env and "SCOPEGUARD_DB" not in env
    assert canary not in blob and "sk-proj-SHOULD-NOT-LEAK" not in blob


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/api/", "http://evil.example/mcp/", "https://127.0.0.1:8000/mcp/",
                                 "http://127.0.0.1:8000/mcp/../crm", "file:///mcp/"])
def test_worker_rejects_alternative_endpoints(url):
    with pytest.raises(ValidationError):
        WorkerRequest(gateway_url=url, token="t" * 32, run_id="r", steps=[{"step_id": "s1", "tool_id": "x", "arguments": {}}])


def test_worker_bootstrap_has_no_upstream_or_credentials():
    assert set(WorkerRequest.model_fields) == {"gateway_url", "token", "run_id", "steps"}


def test_provider_unavailable_uses_labeled_fallback(live_server, analyst, monkeypatch):
    orch = live_server.sg.orchestrator
    original = orch.settings
    orch.settings = dataclasses.replace(original, mode="live", openai_api_key="sk-test-not-a-real-key-000000",
                                        openai_model="test-model")

    async def unavailable(*a, **k):
        raise ProviderError("PROVIDER_UNREACHABLE")

    monkeypatch.setattr(llm, "_openai_chat", unavailable)
    try:
        t = analyst.run("Summarize September sales by region.")
    finally:
        orch.settings = original
    assert t["status"] == "COMPLETED"
    assert t["planner"]["mode"] == "deterministic" and t["planner"]["fallback_reason"] == "PROVIDER_UNREACHABLE"
    assert t["answer"]["mode"] == "deterministic" and t["answer"]["fallback_reason"] == "PROVIDER_UNREACHABLE"
    assert t["metrics"]["personal_field_values_returned_to_model"] == 0


def test_invalid_live_planner_json_never_executes(live_server, analyst, monkeypatch):
    orch = live_server.sg.orchestrator
    original = orch.settings
    orch.settings = dataclasses.replace(original, mode="live", openai_api_key="sk-test-not-a-real-key-000000",
                                        openai_model="test-model")

    async def garbage(settings, body, timeout):
        if "response_format" in body:
            return {"choices": [{"message": {"content": "{\"candidates\": \"DROP TABLE\"}"}}]}
        return {"choices": [{"message": {"content": "Revenue was $1.00 in North, South, East and West."}}]}

    monkeypatch.setattr(llm, "_openai_chat", garbage)
    try:
        t = analyst.run("Summarize September sales by region.")
    finally:
        orch.settings = original
    assert t["planner"]["fallback_reason"] == "PLANNER_CANDIDATE_COUNT"
    # live answer disagreed with authoritative totals -> discarded and labeled
    assert t["answer"]["verified"] is False and t["answer"]["live_answer_discarded"] is True
    assert "$1.00" not in t["result"]["answer_text"]


def test_persona_cannot_be_set_through_tool_or_task_parameters(live_server, analyst):
    r = analyst.http.post("/api/tasks", json={"request": "Summarize September sales by region.", "client_request_id": "1",
                                              "role": "customer_support"}, headers={"x-csrf-token": analyst.csrf})
    assert r.status_code == 422 and r.json() == {"error": "INVALID_REQUEST", "message": "Request did not match the API contract."}
    r = analyst.http.post("/api/tasks", json={"request": "Notify customer 105", "client_request_id": "2"},
                          headers={"x-csrf-token": analyst.csrf, "X-Role": "customer_support"})
    t = analyst.wait(r.json()["task_id"])
    assert t["block"]["code"] == "TASK_NOT_PERMITTED_FOR_ROLE"
