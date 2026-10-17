"""Demo reset (runs last: it regenerates the synthetic credential and restarts private upstreams)."""

import pytest

pytestmark = pytest.mark.security


def test_reset_restores_known_state(live_server):
    c = live_server.client()
    c.persona("sales_analyst")
    assert c.run("Summarize September sales by region.")["status"] == "COMPLETED"
    body = c.reset()
    assert body["reset"] is True and body["customers"] == 5000 and body["sales"] == 10000
    assert c.http.get("/api/session").json()["active"] is False  # sessions invalidated
    assert live_server.sg.orchestrator.tasks == {} and live_server.sg.gateway.audit.all() == []
    c.persona("sales_analyst")
    t = c.run("Check the CRM connection")  # upstream restarted with the regenerated credential
    assert t["status"] == "COMPLETED" and t["result"]["data"]["connected"] is True
