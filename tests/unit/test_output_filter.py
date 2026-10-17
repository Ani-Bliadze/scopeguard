import json

import mcp.types as t
import pytest

from backend.contracts import Classification
from backend.gateway import output_filter
from backend.gateway.output_filter import filter_result
from backend.policy.registry import load_config

pytestmark = pytest.mark.unit

CANARY = "SCOPEGUARD_TEST_SECRET_NEVER_SEND_TO_MODEL_unit"
ARGS = {"month": "2026-09", "group_by": "region", "metric": "total_revenue"}
SAFE_CLASSES = {Classification.PUBLIC, Classification.INTERNAL}


def clean():
    return {"month": "2026-09", "group_by": "region", "metric": "total_revenue", "currency": "USD",
            "rows": [{"region": "East", "value_cents": 10, "transaction_count": 25}]}


def result(structured, text=None, extra_blocks=(), is_error=False, meta=None):
    content = [t.TextContent(type="text", text=text if text is not None else json.dumps(structured))]
    content += list(extra_blocks)
    return t.CallToolResult(content=content, structured_content=structured, is_error=is_error, _meta=meta)


@pytest.fixture(scope="module")
def entry():
    return load_config().tool("analytics.get_sales_summary")


def run(entry, res, args=ARGS):
    return filter_result(entry, args, res, SAFE_CLASSES, [])


def test_clean_result_is_rebuilt_and_measured(entry):
    out = run(entry, result(clean(), meta={"io.modelcontextprotocol/serverInfo": {"name": "x"}}))
    assert out.reason_code == "OUTPUT_ACCEPTED"
    assert out.accepted == clean() and out.counts["aggregate_rows"] == 1 and out.counts["personal_field_values"] == 0


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda d: d["rows"][0].__setitem__("email", "a@example.com"), "OUTPUT_SCHEMA_VIOLATION"),
        (lambda d: d.__setitem__("debug", 1), "OUTPUT_SCHEMA_VIOLATION"),
        (lambda d: d["rows"][0].__setitem__("nested", {"x": 1}), "OUTPUT_SCHEMA_VIOLATION"),
        (lambda d: d.__setitem__("month", "2026-08"), "OUTPUT_SCOPE_MISMATCH"),
        (lambda d: d.__setitem__("currency", CANARY), "SECRET_PATTERN_IN_OUTPUT"),
    ],
)
def test_structured_contamination_rejects_whole_result(entry, mutate, code):
    d = clean()
    mutate(d)
    out = run(entry, result(d))
    assert out.accepted is None and out.reason_code == code


def test_secret_in_text_channel_only_rejected(entry):
    out = run(entry, result(clean(), text=json.dumps(clean()) + CANARY))
    assert out.accepted is None and out.reason_code == "SECRET_PATTERN_IN_OUTPUT"


def test_channel_mismatch_rejected(entry):
    other = clean()
    other["rows"][0]["value_cents"] = 11
    assert run(entry, result(clean(), text=json.dumps(other))).reason_code == "CHANNEL_MISMATCH"


def test_image_block_rejected(entry):
    img = t.ImageContent(type="image", data="AAAA", mime_type="image/png")
    assert run(entry, result(clean(), extra_blocks=[img])).reason_code == "UNEXPECTED_CONTENT_BLOCKS"


def test_application_metadata_rejected(entry):
    assert run(entry, result(clean(), meta={"debug/raw": "x"})).reason_code == "UNEXPECTED_RESULT_METADATA"


def test_error_and_missing_structured_rejected(entry):
    assert run(entry, result(clean(), is_error=True)).reason_code == "UPSTREAM_ERROR_RESULT"
    res = t.CallToolResult(content=[t.TextContent(type="text", text="{}")])
    assert run(entry, res).reason_code == "MISSING_STRUCTURED_OUTPUT"


def test_oversize_rejected(entry):
    d = clean()
    d["rows"] = [{"region": "East", "value_cents": i, "transaction_count": 1} for i in range(3000)]
    out = run(entry, result(d))
    assert out.accepted is None and out.reason_code in {"OUTPUT_TOO_LARGE", "OUTPUT_SCHEMA_VIOLATION"}


def test_scanner_fault_fails_closed(entry, monkeypatch):
    def boom(_):
        raise RuntimeError("scanner crashed")

    monkeypatch.setattr(output_filter, "find_categories", boom)
    assert run(entry, result(clean())).reason_code == "OUTPUT_FILTER_FAULT"


def test_personal_field_needs_approval_even_when_class_allowed():
    cfg = load_config()
    contact = cfg.tool("crm.get_customer_contact")
    d = {"customer_id": 105, "email": "customer00105@example.com"}
    allowed = {Classification.INTERNAL, Classification.PERSONAL}
    args = {"customer_id": 105, "fields": ["email"]}
    assert filter_result(contact, args, result(d), allowed, []).reason_code == "PERSONAL_FIELD_NOT_APPROVED"
    ok = filter_result(contact, args, result(d), allowed, ["customer_id", "email"])
    assert ok.reason_code == "OUTPUT_ACCEPTED" and ok.counts["personal_field_values"] == 1
    wrong = filter_result(contact, {"customer_id": 106, "fields": ["email"]}, result(d), allowed, ["customer_id", "email"])
    assert wrong.reason_code == "OUTPUT_SCOPE_MISMATCH"


def test_unrequested_customer_fields_rejected():
    cfg = load_config()
    customers = cfg.tool("crm.get_customers")
    d = {"rows": [{"id": 1, "region": "North", "email": "customer00001@example.com"}], "row_count": 1}
    allowed = {Classification.INTERNAL, Classification.PERSONAL}
    out = filter_result(customers, {"fields": ["id", "region"], "limit": 1}, result(d), allowed, [])
    assert out.reason_code == "UNREQUESTED_FIELD_IN_OUTPUT"
