"""Secondary-defense pattern scanner for synthetic canaries, credentials and personal identifiers.

This is NOT the primary control (schemas, field allowlists and policy are). It can have false
positives/negatives and is only claimed to detect the synthetic patterns used in this demo."""

from __future__ import annotations

import json
import re
from typing import Any

PATTERNS: dict[str, re.Pattern[str]] = {
    "CANARY": re.compile(r"SCOPEGUARD_TEST_SECRET", re.IGNORECASE),
    "API_KEY_LIKE": re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    "PRIVATE_KEY": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "SYNTHETIC_PERSONAL_ID": re.compile(r"TEST-PID-\d+"),
}
SECRET_CATEGORIES = {"CANARY", "API_KEY_LIKE", "BEARER_TOKEN", "PRIVATE_KEY"}
PERSONAL_CATEGORIES = {"EMAIL", "SYNTHETIC_PERSONAL_ID"}


def iter_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_strings(v)


def find_categories(obj: Any) -> set[str]:
    found: set[str] = set()
    for s in iter_strings(obj):
        for name, pat in PATTERNS.items():
            if name not in found and pat.search(s):
                found.add(name)
    return found


def count_matches(obj: Any, category: str) -> int:
    pat = PATTERNS[category]
    return sum(len(pat.findall(s)) for s in iter_strings(obj))


def contains_value(obj: Any, needle: str) -> bool:
    if not needle:
        return False
    return needle in json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else needle in obj
