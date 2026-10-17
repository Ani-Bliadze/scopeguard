import pytest
from pydantic import ValidationError

from backend.contracts import Principal, Role, ToolStep

pytestmark = pytest.mark.unit


def test_mcp_v2_imports():
    import mcp.types as t
    from mcp import Client, StdioServerParameters  # noqa: F401
    from mcp.client.streamable_http import streamable_http_client  # noqa: F401
    from mcp.server import MCPServer, Server, ServerRequestContext  # noqa: F401

    assert {"structured_content", "is_error", "content"} <= set(t.CallToolResult.model_fields)
    assert {"input_schema", "output_schema"} <= set(t.Tool.model_fields)


def test_strict_models_forbid_extra_fields():
    with pytest.raises(ValidationError):
        Principal(principal_id="x", role=Role.SALES_ANALYST, session_id="s", is_admin=True)
    with pytest.raises(ValidationError):
        ToolStep(step_id="s1", tool_id="t", arguments={}, role="admin")


def test_app_builds_and_reports_health_without_secrets(fixture_db):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.settings import load_settings

    app = create_app(load_settings(mode="deterministic"))
    with TestClient(app) as client:
        body = client.get("/api/health").json()
    assert body["config_valid"] is True
    assert body["fixture"] == {"customers": 5000, "sales": 10000}
    text = str(body)
    assert "SCOPEGUARD_TEST_SECRET" not in text and "sk-" not in text and ".runtime" not in text
