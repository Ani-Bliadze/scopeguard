"""HTTP boundary in front of the gateway's Streamable HTTP app.

Rejects any request without a bearer token bound to an active server-owned grant before it reaches
MCP handling, enforces loopback Host and an explicit body-size limit. Handlers re-check the grant."""

from __future__ import annotations

import json

from backend.gateway.server import Gateway

MAX_BODY_BYTES = 32 * 1024
ALLOWED_HOST_PREFIXES = ("127.0.0.1:", "localhost:")


class GatewayAuthGate:
    def __init__(self, app, gateway: Gateway) -> None:
        self.app = app
        self.gateway = gateway

    async def _reject(self, send, status: int, code: str) -> None:
        body = json.dumps({"error": code}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        host = headers.get("host", "")
        if not host.startswith(ALLOWED_HOST_PREFIXES):
            return await self._reject(send, 421, "HOST_NOT_ALLOWED")
        origin = headers.get("origin")
        if origin is not None and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
            return await self._reject(send, 403, "ORIGIN_NOT_ALLOWED")
        try:
            if int(headers.get("content-length", "0")) > MAX_BODY_BYTES:
                return await self._reject(send, 413, "BODY_TOO_LARGE")
        except ValueError:
            return await self._reject(send, 400, "BAD_CONTENT_LENGTH")
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        grant, why = self.gateway.grants.resolve(token, self.gateway.config.combined_digest)
        if grant is None:
            return await self._reject(send, 401, why)
        return await self.app(scope, receive, send)
