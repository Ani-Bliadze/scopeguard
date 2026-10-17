"""Shared fixtures. Tests run offline in deterministic mode against REAL processes: an in-process uvicorn
server (API + MCP gateway over Streamable HTTP) whose gateway owns real stdio upstream MCP servers."""

from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

os.environ["SCOPEGUARD_MODE"] = "deterministic"  # offline and reproducible; live tests opt in explicitly
os.environ.pop("OPENAI_API_KEY", None)

import uvicorn  # noqa: E402

from backend.settings import load_settings  # noqa: E402
from scripts.api_client import ScopeGuardClient  # noqa: E402
from scripts.reset_demo import reset  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class LiveServer:
    base_url: str
    port: int
    app: object
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def sg(self):
        return self.app.state.sg

    def client(self) -> ScopeGuardClient:
        return ScopeGuardClient(self.base_url)


def start_server(**setting_overrides) -> LiveServer:
    from backend.app.main import create_app

    port = free_port()
    settings = load_settings(port=port, mode="deterministic", openai_api_key="", gemini_api_key="", **setting_overrides)
    app = create_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(base + "/api/health", timeout=2).json().get("status") == "ok":
                return LiveServer(base, port, app, server, thread)
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("server did not become healthy")


def stop_server(ls: LiveServer) -> None:
    ls.server.should_exit = True
    ls.thread.join(timeout=15)


@pytest.fixture(scope="session")
def fixture_db():
    return reset()


@pytest.fixture(scope="session")
def live_server(fixture_db):
    ls = start_server()
    yield ls
    stop_server(ls)


@pytest.fixture(scope="session")
def malicious_server(fixture_db, tmp_path_factory):
    d = tmp_path_factory.mktemp("malicious")
    mode_file = d / "mode.txt"
    mode_file.write_text("clean", encoding="utf-8")
    log = d / "dispatch.log"
    log.write_text("", encoding="utf-8")
    ls = start_server(
        upstream_overrides=(("analytics", "tests.fixtures.malicious_upstream"),),
        upstream_extra_env=(("MALICIOUS_MODE_FILE", str(mode_file)), ("MALICIOUS_DISPATCH_LOG", str(log))),
    )
    ls.mode_file = mode_file
    ls.dispatch_log = log
    yield ls
    stop_server(ls)


@pytest.fixture
def analyst(live_server):
    c = live_server.client()
    c.persona("sales_analyst")
    yield c
    c.close()


@pytest.fixture
def support(live_server):
    c = live_server.client()
    c.persona("customer_support")
    yield c
    c.close()


@pytest.fixture
def canary() -> str:
    from backend.settings import read_backend_credential

    value = read_backend_credential()
    assert value and value.startswith("SCOPEGUARD_TEST_SECRET")
    return value
