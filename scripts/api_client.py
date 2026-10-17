"""Tiny HTTP client for the ScopeGuard API (used by demo runner and integration tests)."""

from __future__ import annotations

import time
import uuid

import httpx


class ScopeGuardClient:
    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=60.0)
        self.csrf: str | None = None

    def close(self) -> None:
        self.http.close()

    def persona(self, role: str) -> dict:
        r = self.http.post("/api/demo/session", json={"persona": role})
        r.raise_for_status()
        data = r.json()
        self.csrf = data["csrf_token"]
        return data

    def _h(self) -> dict:
        return {"x-csrf-token": self.csrf or ""}

    def start(self, request: str) -> str:
        r = self.http.post("/api/tasks", json={"request": request, "client_request_id": uuid.uuid4().hex}, headers=self._h())
        r.raise_for_status()
        return r.json()["task_id"]

    def probe(self, name: str) -> str:
        r = self.http.post("/api/demo/probe", json={"probe": name}, headers=self._h())
        r.raise_for_status()
        return r.json()["task_id"]

    def task(self, task_id: str) -> dict:
        r = self.http.get(f"/api/tasks/{task_id}")
        r.raise_for_status()
        return r.json()

    def wait(self, task_id: str, timeout: float = 90, until_approval: bool = True) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            t = self.task(task_id)
            if t["terminal"] or (until_approval and t["status"] == "AWAITING_APPROVAL"):
                return t
            time.sleep(0.25)
        raise TimeoutError("task did not finish")

    def run(self, request: str, timeout: float = 90) -> dict:
        return self.wait(self.start(request), timeout)

    def events(self, task_id: str) -> list[dict]:
        r = self.http.get(f"/api/tasks/{task_id}/events")
        r.raise_for_status()
        return r.json()["events"]

    def decide(self, approval_id: str, decision: str) -> httpx.Response:
        return self.http.post(f"/api/approvals/{approval_id}/decision", json={"decision": decision}, headers=self._h())

    def reset(self) -> dict:
        r = self.http.post("/api/demo/reset", headers=self._h())
        r.raise_for_status()
        return r.json()
