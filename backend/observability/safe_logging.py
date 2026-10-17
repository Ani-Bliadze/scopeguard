"""Quiet, sanitized logging for demo mode: no request bodies, headers, tool payloads or stack traces."""

from __future__ import annotations

import logging

from backend.observability.sensitive import find_categories


class _Redactor(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return False
        if find_categories(msg):
            record.msg = "[redacted log line: sensitive pattern detected]"
            record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


def configure() -> None:
    root = logging.getLogger()
    for h in root.handlers:
        h.addFilter(_Redactor())
    for name in ("mcp", "httpx", "httpx2", "httpcore", "uvicorn.access", "google_genai"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").addFilter(_Redactor())
