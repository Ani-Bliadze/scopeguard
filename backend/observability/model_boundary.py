"""Every provider invocation (planner or answer, live or deterministic) passes through here.

Immediately before dispatch the exact serialized content is scanned and measured. Secrets block the
dispatch unconditionally; personal patterns block unless the task's policy explicitly allows them.
Tests can enable an in-memory recorder of exact payloads; production keeps counts only."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.observability.sensitive import PERSONAL_CATEGORIES, SECRET_CATEGORIES, count_matches, find_categories


class ModelBoundaryViolation(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class BoundaryMeasurement:
    phase: str  # planner | answer
    provider: str  # deterministic | openai | gemini
    external_request: bool
    dispatched: bool
    total_bytes: int
    tool_result_bytes: int
    customer_rows: int = 0
    transaction_rows: int = 0
    aggregate_rows: int = 0
    personal_field_values: int = 0
    canary_hits: int = 0
    email_pattern_hits: int = 0
    personal_id_pattern_hits: int = 0
    blocked_reason: str | None = None
    ts: float = field(default_factory=time.time)


class ModelBoundary:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.recorder: list[dict[str, Any]] | None = None  # tests only; never persisted
        self.measurements: list[BoundaryMeasurement] = []

    def enable_recording(self) -> list[dict[str, Any]]:
        with self._lock:
            self.recorder = []
            return self.recorder

    async def dispatch(
        self,
        *,
        phase: str,
        provider: str,
        messages: list[dict[str, Any]],
        tool_result: dict[str, Any] | None,
        tool_counts: dict[str, int] | None,
        allow_personal: set[str],
        call: Callable[[list[dict[str, Any]]], Awaitable[Any]],
    ) -> tuple[Any, BoundaryMeasurement]:
        serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        cats = find_categories(serialized)
        counts = tool_counts or {}
        m = BoundaryMeasurement(
            phase=phase,
            provider=provider,
            external_request=provider != "deterministic",
            dispatched=False,
            total_bytes=len(serialized.encode()),
            tool_result_bytes=len(json.dumps(tool_result, separators=(",", ":")).encode()) if tool_result else 0,
            customer_rows=counts.get("customer_rows", 0),
            transaction_rows=counts.get("transaction_rows", 0),
            aggregate_rows=counts.get("aggregate_rows", 0),
            personal_field_values=counts.get("personal_field_values", 0),
            canary_hits=count_matches(serialized, "CANARY"),
            email_pattern_hits=count_matches(serialized, "EMAIL"),
            personal_id_pattern_hits=count_matches(serialized, "SYNTHETIC_PERSONAL_ID"),
        )
        blocked = None
        if cats & SECRET_CATEGORIES:
            blocked = "SECRET_AT_MODEL_BOUNDARY"
        elif (cats & PERSONAL_CATEGORIES) - allow_personal:
            blocked = "PERSONAL_DATA_AT_MODEL_BOUNDARY"
        with self._lock:
            if self.recorder is not None:
                self.recorder.append({"phase": phase, "provider": provider, "payload": serialized, "blocked": blocked})
        if blocked:
            m.blocked_reason = blocked
            m.external_request = False
            self.measurements.append(m)
            raise ModelBoundaryViolation(blocked)
        m.dispatched = True
        self.measurements.append(m)
        try:
            return await call(messages), m
        except Exception as exc:
            # The content still crossed the boundary; keep the measurement attached for honest accounting.
            exc.measurement = m  # type: ignore[attr-defined]
            raise

    @staticmethod
    def as_dict(m: BoundaryMeasurement) -> dict[str, Any]:
        d = asdict(m)
        d.pop("ts", None)
        return d
