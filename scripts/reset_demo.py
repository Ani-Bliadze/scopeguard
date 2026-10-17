"""Reset the synthetic database, runtime credential and audit log to a known state.

Only deletes files inside the verified project .runtime directory. Prints counts, never values.
"""

from __future__ import annotations

import sys

from backend.data.seed import build_database, fixture_digest, new_canary_credential
from backend.settings import AUDIT_DB_PATH, BACKEND_ENV_PATH, DB_PATH, PROJECT_ROOT, RUNTIME_DIR


def reset() -> dict:
    runtime = RUNTIME_DIR.resolve()
    if runtime.parent != PROJECT_ROOT.resolve() or runtime.name != ".runtime":
        raise SystemExit("refusing to reset: unexpected runtime directory")
    runtime.mkdir(exist_ok=True)
    credential = new_canary_credential()
    BACKEND_ENV_PATH.write_text(f"SCOPEGUARD_CRM_CREDENTIAL={credential}\n", encoding="utf-8")
    counts = build_database(DB_PATH, credential)
    if AUDIT_DB_PATH.exists():
        AUDIT_DB_PATH.unlink()
    counts["fixture_sha256"] = fixture_digest(DB_PATH)
    return counts


if __name__ == "__main__":
    c = reset()
    print(
        f"reset ok: customers={c['customers']} sales={c['sales']} regions={c['regions']} "
        f"fixture_sha256={c['fixture_sha256'][:16]}... (synthetic credential regenerated; value not shown)"
    )
    sys.exit(0)
