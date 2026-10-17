"""Final release gate: repo isolation, required deliverables, no secrets tracked, evidence and deck checks."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from backend.settings import PROJECT_ROOT, read_backend_credential

REQUIRED = [
    "README.md", ".env.example", "PLAN.md", "docs/CLAUDE_BUILD_PLAN.md", "docs/DECISIONS.md", "docs/DEMO_RESULTS.md",
    "docs/demo_results.json", "docs/SECURITY_LIMITATIONS.md", "docs/DEMO_SCRIPT.md", "docs/FINAL_STATUS.md",
    "config/policy.json", "config/tool_registry.json", "config/tasks.json", "requirements.lock", "requirements-dev.lock",
    "package-lock.json", "pitch/build_deck.js", "pitch/ScopeGuard_Pitch.pptx", "pitch/PITCH_SCRIPT.md", "pitch/README.md",
    "pitch/qa/montage.png", "pitch/qa/review.json", "pitch/qa/layout-report.json",
] + [f"pitch/qa/slide-{i:02d}.png" for i in range(1, 9)]

results: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    results.append((ok, msg))
    print(("ok  " if ok else "BAD ") + msg)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()


def main() -> None:
    top = Path(git("rev-parse", "--show-toplevel")).resolve()
    check(top == PROJECT_ROOT.resolve(), "dedicated project git root")
    for f in REQUIRED:
        check((PROJECT_ROOT / f).exists(), f"exists: {f}")
    tracked = git("ls-files").splitlines()
    check(".env" not in tracked and not any(t.startswith(".runtime/") for t in tracked), ".env and .runtime/ are not tracked")
    canary = read_backend_credential() or "SCOPEGUARD_TEST_SECRET_NEVER_SEND_TO_MODEL_"
    key_pat = re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{40,}")
    leaks = []
    for t in tracked:
        p = PROJECT_ROOT / t
        if p.suffix.lower() in {".png", ".pptx", ".pdf", ".ico"} or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if canary in text or key_pat.search(text):
            leaks.append(t)
    check(not leaks, f"no live credential or current canary in tracked files {leaks or ''}")
    ev = subprocess.run([sys.executable, "-m", "scripts.check_evidence"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    check(ev.returncode == 0, "scripts.check_evidence passed")
    deck = subprocess.run([sys.executable, "pitch/check_deck.py"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    check(deck.returncode == 0, "pitch/check_deck.py passed" + ("" if deck.returncode == 0 else ": " + deck.stdout[-400:]))
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} release checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
