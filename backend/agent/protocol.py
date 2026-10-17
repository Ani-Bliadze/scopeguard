"""Bounded stdin/stdout documents between the trusted control plane and the agent worker."""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator

from backend.contracts import Strict

GATEWAY_URL_RE = re.compile(r"^http://127\.0\.0\.1:\d{2,5}/mcp/$")
MAX_WORKER_OUTPUT_BYTES = 64 * 1024


class WorkerStep(Strict):
    step_id: str = Field(max_length=16)
    tool_id: str = Field(max_length=64)
    arguments: dict[str, Any]


class WorkerRequest(Strict):
    gateway_url: str
    token: str = Field(min_length=20, max_length=128)
    run_id: str = Field(max_length=32)
    steps: list[WorkerStep] = Field(min_length=1, max_length=3)

    @field_validator("gateway_url")
    @classmethod
    def _fixed_destination(cls, v: str) -> str:
        if not GATEWAY_URL_RE.match(v):
            raise ValueError("gateway destination not allowed")
        return v


class WorkerStepResult(Strict):
    step_id: str
    tool_id: str
    ok: bool
    structured: dict[str, Any] | None = None
    error_code: str | None = None


class WorkerResponse(Strict):
    run_id: str
    protocol_version: str | None = None
    listed_tools: list[str] = Field(default_factory=list)
    results: list[WorkerStepResult] = Field(default_factory=list)
    error_code: str | None = None
