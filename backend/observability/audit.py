"""Redacted audit trail. Stores tool names, field names/classes, decisions, reason codes, counts and
byte sizes only -- never values. Every event is scanned before persistence; an event that matches a
sensitive pattern is replaced by a guard event rather than stored."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import Field

from backend.contracts import EventType, Strict
from backend.observability.sensitive import find_categories


class AuditEvent(Strict):
    seq: int = 0
    ts: float = 0.0
    task_id: str
    run_id: str | None = None
    principal: str  # pseudonymous hash
    stage: EventType
    tool_id: str | None = None
    decision: str | None = None
    reason_code: str | None = None
    fields: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    message: str = ""
    model_mode: str | None = None
    candidate_id: str | None = None


def pseudonym(principal_id: str) -> str:
    return "p_" + hashlib.sha256(("scopeguard-demo:" + principal_id).encode()).hexdigest()[:10]


class AuditLog:
    def __init__(self, path: Path | None) -> None:
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []
        self._path = path
        self._seq = 0
        self.guard_triggers = 0
        self.persist_errors = 0
        self._init_db()

    def _init_db(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(self._path, timeout=2)) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS audit_events (seq INTEGER PRIMARY KEY, ts REAL, task_id TEXT, "
                "stage TEXT, event_json TEXT)"
            )
            con.commit()
            self._seq = max(self._seq, con.execute("SELECT COALESCE(MAX(seq), 0) FROM audit_events").fetchone()[0])

    def record(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._seq += 1
            event.seq = self._seq
            event.ts = round(time.time(), 3)
            payload = event.model_dump(mode="json")
            if find_categories(payload):
                self.guard_triggers += 1
                event = AuditEvent(
                    seq=event.seq,
                    ts=event.ts,
                    task_id=event.task_id,
                    run_id=event.run_id,
                    principal=event.principal,
                    stage=event.stage,
                    tool_id=event.tool_id,
                    decision=event.decision,
                    reason_code="AUDIT_REDACTION_GUARD",
                    message="Event withheld: a sensitive pattern was detected in audit metadata.",
                )
                payload = event.model_dump(mode="json")
            self._events.append(event)
            if self._path is not None:
                try:
                    with closing(sqlite3.connect(self._path, timeout=2)) as con:
                        con.execute(
                            "INSERT INTO audit_events VALUES (?,?,?,?,?)",
                            (event.seq, event.ts, event.task_id, event.stage.value, json.dumps(payload)),
                        )
                        con.commit()
                except sqlite3.Error:
                    # In-memory trail stays authoritative for the demo; persistence failures are counted.
                    self.persist_errors += 1
            return event

    def for_task(self, task_id: str, after: int = 0) -> list[AuditEvent]:
        with self._lock:
            return [e for e in self._events if e.task_id == task_id and e.seq > after]

    def all(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._events)

    def export_rows(self) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in self.all()]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self.guard_triggers = 0
            if self._path is not None:
                self._init_db()
                with closing(sqlite3.connect(self._path, timeout=2)) as con:
                    con.execute("DELETE FROM audit_events")
                    con.commit()
