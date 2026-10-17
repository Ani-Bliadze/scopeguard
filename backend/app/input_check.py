"""Maps a raw user request to a fixed supported intent. The LLM never chooses identity or intent.

Secret-disclosure requests are detected first and terminate with a hard deny. Anything not exactly a
known alias (after case/whitespace/punctuation normalization) is UNSUPPORTED_TASK."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.contracts import Intent
from backend.policy.registry import TrustedConfig


@dataclass(frozen=True)
class InputVerdict:
    intent: Intent | None
    code: str  # ACCEPTED | UNSUPPORTED_TASK | HARD_DENY_SECRET_DISCLOSURE | INPUT_TOO_LONG | EMPTY_INPUT
    canonical_request: str | None


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9#' ]+", " ", text)
    text = text.replace("#", " ")
    return re.sub(r"\s+", " ", text).strip()


def check_input(config: TrustedConfig, request: str) -> InputVerdict:
    if not request or not request.strip():
        return InputVerdict(None, "EMPTY_INPUT", None)
    if len(request) > config.tasks.max_input_chars:
        return InputVerdict(None, "INPUT_TOO_LONG", None)
    lowered = request.lower()
    for pat in config.tasks.secret_request_patterns:
        if re.search(pat, lowered):
            spec = config.tasks.intents[Intent.SECRET_DISCLOSURE_ATTEMPT]
            return InputVerdict(Intent.SECRET_DISCLOSURE_ATTEMPT, "HARD_DENY_SECRET_DISCLOSURE", spec.canonical_request)
    norm = normalize(request)
    for intent, spec in config.tasks.intents.items():
        if norm in {normalize(a) for a in spec.aliases}:
            if intent == Intent.SECRET_DISCLOSURE_ATTEMPT:
                return InputVerdict(intent, "HARD_DENY_SECRET_DISCLOSURE", spec.canonical_request)
            return InputVerdict(intent, "ACCEPTED", spec.canonical_request)
    return InputVerdict(None, "UNSUPPORTED_TASK", None)
