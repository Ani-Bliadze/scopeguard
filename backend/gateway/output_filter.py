"""Complete-result acceptance for upstream MCP results before anything can reach the agent/model.

Both MCP channels are inspected. The whole result is rejected on any doubt; nothing is salvaged.
On acceptance, a NEW object is built from the validated model -- the upstream envelope is discarded."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from backend.contracts import Classification
from backend.observability.sensitive import PERSONAL_CATEGORIES, SECRET_CATEGORIES, find_categories
from backend.tool_schemas import SCHEMAS

PROTOCOL_META_PREFIX = "io.modelcontextprotocol/"

@dataclass
class FilterOutcome:
    accepted: dict[str, Any] | None
    reason_code: str
    counts: dict[str, int] = field(default_factory=dict)
    fields: list[str] = field(default_factory=list)


def _reject(code: str) -> FilterOutcome:
    return FilterOutcome(accepted=None, reason_code=code)


def measure(entry, obj: dict[str, Any]) -> dict[str, int]:
    """Count rows and personal field-values in a validated, accepted object."""
    personal = {f for f, s in entry.fields.items() if s.class_ == Classification.PERSONAL}
    counts = {
        "customer_rows": 0,
        "transaction_rows": 0,
        "aggregate_rows": 0,
        "personal_field_values": 0,
        "bytes": len(json.dumps(obj, separators=(",", ":")).encode()),
    }
    rows = obj.get("rows") if entry.output_shape in ("rows", "aggregate") else [obj]
    if entry.row_kind == "customer":
        counts["customer_rows"] = len(rows)
    elif entry.row_kind == "transaction":
        counts["transaction_rows"] = len(rows)
    elif entry.row_kind == "aggregate":
        counts["aggregate_rows"] = len(rows)
    for row in rows:
        counts["personal_field_values"] += sum(1 for k, v in row.items() if k in personal and v is not None)
    return counts


def filter_result(
    entry,
    args: dict[str, Any],
    result: Any,
    allowed_classes: set[Classification],
    approved_fields: list[str],
) -> FilterOutcome:
    try:
        return _filter(entry, args, result, allowed_classes, approved_fields)
    except Exception:
        # Scanner/filter fault: fail closed with a fixed code.
        return _reject("OUTPUT_FILTER_FAULT")


def _filter(entry, args, result, allowed_classes, approved_fields) -> FilterOutcome:
    # 1. Upstream error results never pass through.
    if getattr(result, "is_error", True):
        return _reject("UPSTREAM_ERROR_RESULT")
    # 4. Only plain text content blocks; no images/resources/links; no annotations or app metadata.
    content = list(getattr(result, "content", None) or [])
    if len(content) != 1:
        return _reject("UNEXPECTED_CONTENT_BLOCKS")
    block = content[0]
    if getattr(block, "type", None) != "text" or getattr(block, "annotations", None) or getattr(block, "meta", None):
        return _reject("UNEXPECTED_CONTENT_TYPE")
    # SDK protocol metadata (e.g. io.modelcontextprotocol/serverInfo) is tolerated but never forwarded;
    # any application-defined metadata key fails closed.
    meta = getattr(result, "meta", None) or {}
    if any(not str(k).startswith(PROTOCOL_META_PREFIX) for k in meta):
        return _reject("UNEXPECTED_RESULT_METADATA")
    # 2. Trusted structured output is required.
    structured = getattr(result, "structured_content", None)
    if not isinstance(structured, dict):
        return _reject("MISSING_STRUCTURED_OUTPUT")
    # Byte cap before parsing anything further.
    text = block.text
    raw_bytes = len(text.encode()) + len(json.dumps(structured).encode())
    if raw_bytes > 2 * entry.max_bytes:
        return _reject("OUTPUT_TOO_LARGE")
    # 6. Secret patterns in EITHER channel block the whole result, regardless of task or approval.
    cats = find_categories(structured) | find_categories(text)
    if cats & SECRET_CATEGORIES:
        return _reject("SECRET_PATTERN_IN_OUTPUT")
    # 3. Recursive validation against the registered schema (unknown/nested fields -> reject).
    out_model = SCHEMAS[entry.tool_id][1]
    try:
        validated = out_model.model_validate(structured)
    except ValidationError:
        return _reject("OUTPUT_SCHEMA_VIOLATION")
    # 5. Text channel must be semantically identical to the structured channel.
    try:
        if json.loads(text) != structured:
            return _reject("CHANNEL_MISMATCH")
    except (json.JSONDecodeError, TypeError):
        return _reject("CHANNEL_MISMATCH")

    # Field projection must match what was requested and classified.
    if entry.output_shape == "rows":
        requested = set(args.get("fields", []))
        for row in structured.get("rows", []):
            if set(row) - requested:
                return _reject("UNREQUESTED_FIELD_IN_OUTPUT")
        if len(structured["rows"]) > min(entry.max_rows, args.get("limit", entry.max_rows)):
            return _reject("ROW_LIMIT_EXCEEDED")
        if structured.get("row_count") != len(structured["rows"]):
            return _reject("INCOMPLETE_OR_INCONSISTENT_OUTPUT")
    if entry.output_shape == "aggregate":
        rows = structured["rows"]
        if len(rows) > entry.max_rows or len({r["region"] for r in rows}) != len(rows):
            return _reject("ROW_LIMIT_EXCEEDED")
        if structured.get("month") != args.get("month") or structured.get("metric") != args.get("metric"):
            return _reject("OUTPUT_SCOPE_MISMATCH")
    if entry.output_shape == "single" and "customer_id" in args and structured.get("customer_id") != args["customer_id"]:
        return _reject("OUTPUT_SCOPE_MISMATCH")

    # Classification check on every returned field.
    present: set[str] = set()
    rows = structured.get("rows") if entry.output_shape in ("rows", "aggregate") else [structured]
    for row in rows:
        present.update(k for k, v in row.items() if v is not None)
    if entry.output_shape == "status":
        present = set(structured)
    for f in present:
        spec = entry.fields.get(f)
        if spec is None:
            return _reject("UNCLASSIFIED_FIELD_IN_OUTPUT")
        if spec.class_ not in allowed_classes:
            return _reject("FIELD_CLASS_NOT_PERMITTED_IN_OUTPUT")
        if spec.class_ == Classification.PERSONAL and f not in approved_fields:
            return _reject("PERSONAL_FIELD_NOT_APPROVED")

    # Personal-pattern scan: only an explicitly approved PERSONAL email field may carry an email.
    personal_hits = cats & PERSONAL_CATEGORIES
    if personal_hits:
        if personal_hits != {"EMAIL"} or "email" not in approved_fields or Classification.PERSONAL not in allowed_classes:
            return _reject("PERSONAL_PATTERN_IN_OUTPUT")

    accepted = validated.model_dump(mode="json", exclude_none=True)
    if entry.output_shape == "rows":
        accepted["rows"] = [{k: v for k, v in r.items() if v is not None} for r in accepted["rows"]]
    size = len(json.dumps(accepted, separators=(",", ":")).encode())
    if size > entry.max_bytes:
        return _reject("OUTPUT_TOO_LARGE")
    return FilterOutcome(accepted=accepted, reason_code="OUTPUT_ACCEPTED", counts=measure(entry, accepted), fields=sorted(present))
