"""Lifecycle owner for the private upstream MCP services.

CRM and Analytics run as stdio subprocesses owned by this module; they have no listening sockets.
Only this module knows their module paths and passes the synthetic backend credential, and only to
the CRM process environment. Calls are serialized per upstream and bounded by a timeout."""

from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import anyio
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.settings import DB_PATH, PROJECT_ROOT, PYTHON, RUNTIME_DIR, Settings, read_backend_credential

DEFAULT_MODULES = {
    "crm": "mcp_servers.crm_server",
    "analytics": "mcp_servers.analytics_server",
}


class UpstreamError(Exception):
    """Fixed-code upstream failure. Never carries upstream payloads or stderr."""


@dataclass
class DispatchRecord:
    server_id: str
    upstream_name: str
    ts: float
    task_id: str | None


@dataclass
class UpstreamManager:
    settings: Settings
    clients: dict[str, Client] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    upstream_tools: dict[str, list[str]] = field(default_factory=dict)
    dispatches: list[DispatchRecord] = field(default_factory=list)

    def _modules(self) -> dict[str, str]:
        modules = dict(DEFAULT_MODULES)
        modules.update(dict(self.settings.upstream_overrides))
        return modules

    _owner: asyncio.Task | None = None
    _ready: asyncio.Event | None = None
    _cycle: asyncio.Event | None = None
    _stopping: bool = False
    start_error: str | None = None

    async def _open(self, stack: AsyncExitStack) -> None:
        RUNTIME_DIR.mkdir(exist_ok=True)
        # Upstream stderr goes to an ignored runtime file, never to model/UI surfaces.
        errlog = open(RUNTIME_DIR / "upstream-stderr.log", "a", encoding="utf-8")  # noqa: SIM115
        stack.callback(errlog.close)
        credential = read_backend_credential() or ""
        for server_id, module in self._modules().items():
            env = {"SCOPEGUARD_DB": str(DB_PATH), "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
            if server_id == "crm":
                env["SCOPEGUARD_CRM_CREDENTIAL"] = credential
            if server_id in dict(self.settings.upstream_overrides):
                env.update(dict(self.settings.upstream_extra_env))
            params = StdioServerParameters(command=PYTHON, args=["-m", module], env=env, cwd=str(PROJECT_ROOT))
            client = Client(stdio_client(params, errlog=errlog), read_timeout_seconds=self.settings.upstream_timeout_s)
            await stack.enter_async_context(client)
            listing = await client.list_tools()
            self.clients[server_id] = client
            self.locks.setdefault(server_id, asyncio.Lock())
            self.upstream_tools[server_id] = sorted(t.name for t in listing.tools)

    async def _own(self) -> None:
        """Single owner task: enters and exits all upstream contexts (anyio scopes are task-bound)."""
        while not self._stopping:
            self._cycle = asyncio.Event()
            async with AsyncExitStack() as stack:
                try:
                    await self._open(stack)
                    self.start_error = None
                except Exception:
                    self.clients.clear()
                    self.start_error = "UPSTREAM_START_FAILED"
                self._ready.set()
                await self._cycle.wait()
                self.clients.clear()

    async def start(self) -> None:
        self._ready = asyncio.Event()
        self._stopping = False
        self._owner = asyncio.get_running_loop().create_task(self._own())
        await self._ready.wait()

    async def restart(self) -> None:
        self._ready = asyncio.Event()
        self._cycle.set()
        await self._ready.wait()

    async def stop(self) -> None:
        self._stopping = True
        if self._cycle is not None:
            self._cycle.set()
        if self._owner is not None:
            try:
                await asyncio.wait_for(self._owner, timeout=10)
            except Exception:
                pass

    def status(self) -> dict[str, bool]:
        return {sid: sid in self.clients for sid in self._modules()}

    async def call(self, server_id: str, upstream_name: str, args: dict[str, Any], task_id: str | None):
        client = self.clients.get(server_id)
        if client is None:
            raise UpstreamError("UPSTREAM_UNAVAILABLE")
        async with self.locks[server_id]:
            self.dispatches.append(DispatchRecord(server_id, upstream_name, time.time(), task_id))
            try:
                with anyio.fail_after(self.settings.upstream_timeout_s):
                    return await client.call_tool(upstream_name, args)
            except TimeoutError:
                raise UpstreamError("UPSTREAM_TIMEOUT") from None
            except Exception:
                raise UpstreamError("UPSTREAM_ERROR") from None

    def dispatch_count(self, upstream_name: str | None = None, task_id: str | None = None) -> int:
        return sum(
            1
            for d in self.dispatches
            if (upstream_name is None or d.upstream_name == upstream_name) and (task_id is None or d.task_id == task_id)
        )
