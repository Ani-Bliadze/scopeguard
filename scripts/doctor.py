"""Environment check. Prints versions and configuration PRESENCE booleans only, never values."""

from __future__ import annotations

import importlib.metadata as md
import platform
import shutil
import subprocess

from backend.settings import BACKEND_ENV_PATH, DB_PATH, FRONTEND_DIST, load_settings


def v(pkg: str) -> str:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return "MISSING"


def main() -> None:
    s = load_settings()
    print(f"python {platform.python_version()} ({platform.system()})")
    for pkg in ("mcp", "fastapi", "pydantic", "uvicorn", "httpx2", "httpx", "google-genai", "python-dotenv", "pytest"):
        print(f"  {pkg:15} {v(pkg)}")
    node = shutil.which("node")
    if node:
        print("node", subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip())
    print("config:")
    print(f"  SCOPEGUARD_MODE           {s.mode}")
    print(f"  OPENAI_API_KEY present    {bool(s.openai_api_key)}")
    print(f"  OPENAI_MODEL present      {bool(s.openai_model)}")
    print(f"  GEMINI_API_KEY present    {bool(s.gemini_api_key)}")
    print(f"  effective provider        {s.live_provider or 'deterministic'}")
    print(f"  fixture db present        {DB_PATH.exists()}")
    print(f"  backend credential file   {BACKEND_ENV_PATH.exists()} (value never printed)")
    print(f"  UI built                  {FRONTEND_DIST.exists()}")
    from mcp import Client  # noqa: F401  (v2 import check)
    from mcp.server import MCPServer, Server  # noqa: F401

    print("mcp v2 imports ok")


if __name__ == "__main__":
    main()
