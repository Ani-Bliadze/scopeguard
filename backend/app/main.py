"""ScopeGuard FastAPI application: trusted control plane + mounted MCP gateway (one process)."""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.orchestrator import Orchestrator
from backend.app.sessions import SessionStore
from backend.gateway.server import Gateway
from backend.gateway.transport import MAX_BODY_BYTES, GatewayAuthGate
from backend.gateway.upstream import UpstreamManager
from backend.observability import safe_logging
from backend.observability.audit import AuditLog
from backend.observability.model_boundary import ModelBoundary
from backend.planner.evaluate import FixtureMeta
from backend.policy.grants import ApprovalStore, GrantStore
from backend.policy.registry import ConfigError, TrustedConfig, load_config
from backend.settings import AUDIT_DB_PATH, DB_PATH, FRONTEND_DIST, Settings, load_settings


@dataclass
class AppState:
    settings: Settings
    config: TrustedConfig | None
    config_error: str | None
    gateway: Gateway | None = None
    orchestrator: Orchestrator | None = None
    sessions: SessionStore = field(default_factory=SessionStore)
    boundary: ModelBoundary = field(default_factory=ModelBoundary)
    fixture: FixtureMeta | None = None


def read_fixture_meta() -> FixtureMeta | None:
    """Trusted fixture metadata only (counts), never business rows."""
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT customer_count, sales_count FROM fixture_meta").fetchone()
        return FixtureMeta(customer_count=row[0], sales_count=row[1]) if row else None
    finally:
        con.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    safe_logging.configure()
    try:
        config, config_error = load_config(), None
    except ConfigError as exc:
        config, config_error = None, str(exc)

    state = AppState(settings=settings, config=config, config_error=config_error, fixture=read_fixture_meta())
    mcp_app = None
    if config is not None:
        gateway = Gateway(
            config=config,
            grants=GrantStore(),
            approvals=ApprovalStore(),
            audit=AuditLog(AUDIT_DB_PATH),
            upstream=UpstreamManager(settings),
        )
        state.gateway = gateway
        mcp_app = gateway.server.streamable_http_app(
            streamable_http_path="/",
            json_response=True,
            stateless_http=True,
            max_request_body_size=MAX_BODY_BYTES,
            host="127.0.0.1",
        )
        if state.fixture is not None:
            state.orchestrator = Orchestrator(settings=settings, gateway=gateway, boundary=state.boundary,
                                              fixture=state.fixture)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if state.gateway is None:
            yield
            return
        await state.gateway.upstream.start()
        try:
            async with state.gateway.server.session_manager.run():
                yield
        finally:
            await state.gateway.upstream.stop()

    app = FastAPI(
        title="ScopeGuard API",
        version="1.0.0",
        description="Privacy-aware AI agent gateway (local hackathon demo). Demo sessions are not production auth.",
        lifespan=lifespan,
        debug=False,
    )
    app.state.sg = state

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, __: RequestValidationError):
        # Never echo validation details: they can include rejected input values.
        return JSONResponse({"error": "INVALID_REQUEST", "message": "Request did not match the API contract."}, 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(detail, exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception):
        return JSONResponse({"error": "INTERNAL_ERROR", "message": "The server failed closed."}, 500)

    from backend.app.routes import router

    app.include_router(router)
    if mcp_app is not None:
        app.mount("/mcp", GatewayAuthGate(mcp_app, state.gateway))
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
    return app
