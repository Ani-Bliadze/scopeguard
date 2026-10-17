"""Private-upstream runtime helpers. Upstream servers read their DB path from their own environment,
which only the gateway's lifecycle owner sets. Diagnostics never go to stdout (that is the MCP channel)."""

from __future__ import annotations

import os
import sqlite3


def db_connect() -> sqlite3.Connection:
    path = os.environ.get("SCOPEGUARD_DB")
    if not path:
        raise RuntimeError("UPSTREAM_NOT_CONFIGURED")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
