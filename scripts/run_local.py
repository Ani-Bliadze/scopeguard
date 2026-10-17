"""Start ScopeGuard locally: one backend process (API + MCP gateway + built UI) on 127.0.0.1.

Usage: .venv\\Scripts\\python.exe -m scripts.run_local [--mode deterministic|live] [--port 8000]
Never kills other processes; exits with a clear message if the port is taken."""

from __future__ import annotations

import argparse
import os
import socket
import sys

import uvicorn


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["deterministic", "live"], default=None)
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if a.mode:
        os.environ["SCOPEGUARD_MODE"] = a.mode
    if not port_free(a.port):
        sys.exit(f"Port {a.port} is already in use. Stop the other process or pass --port N.")

    from backend.app.main import create_app
    from backend.settings import DB_PATH, FRONTEND_DIST, load_settings

    if not DB_PATH.exists():
        sys.exit("Synthetic fixture missing. Run: .venv\\Scripts\\python.exe -m scripts.reset_demo")
    settings = load_settings(port=a.port)
    app = create_app(settings)
    mode = settings.live_provider or "deterministic"
    print(f"ScopeGuard on http://127.0.0.1:{a.port}  | planner/answer mode: {mode}"
          f"{'' if FRONTEND_DIST.exists() else '  | UI not built (npm run build)'}")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning", access_log=False, reload=False, workers=1)


if __name__ == "__main__":
    main()
