import asyncio
import copy

import pytest

from backend.contracts import Classification, Decision, Intent, PlanCandidate
from backend.planner.base import ProviderError, parse_planner_output
from backend.planner.deterministic import TEMPLATES, DeterministicPlanner
from backend.planner.evaluate import FixtureMeta, evaluate_candidates
from backend.policy.registry import load_config

pytestmark = pytest.mark.unit
CFG = load_config()
META = FixtureMeta(customer_count=5000, sales_count=10000)
SALES = Intent.SALES_BY_REGION_2026_09


def cand(cid, tool, args, reducer=None, risk=None, origin="openai"):
    return PlanCandidate.model_validate(
        {"candidate_id": cid, "steps": [{"step_id": "s1", "tool_id": tool, "arguments": args}], "reducer": reducer,
         "rationale": "r", "origin": origin, "self_reported_risk": risk}, strict=False)


def test_deterministic_sales_plan_selects_aggregate():
    cands = asyncio.run(DeterministicPlanner(SALES).propose([]))
    evals, selected, _ = evaluate_candidates(CFG, "sales_analyst", SALES, cands, META)
    assert len(evals) == 3 and selected.tools == ["analytics.get_sales_summary"]
    risky = next(e for e in evals if e.tools == ["crm.get_customers"])
    assert risky.decision == Decision.DENY and risky.covers_task
    assert risky.exposure.customer_rows_requested == 5000
    assert risky.exposure.personal_field_values_requested == 10000  # 5,000 rows x email + synthetic id
    assert selected.exposure.personal_field_values_requested == 0 and selected.exposure.aggregate_rows_expected == 4


@pytest.mark.parametrize(
    "args,code",
    [
        ({"month": "2026-08", "group_by": "region", "metric": "total_revenue"}, "WRONG_MONTH"),
        ({"month": "2026-09", "group_by": "region", "metric": "average_sales"}, "WRONG_METRIC"),
    ],
)
def test_wrong_scope_aggregate_not_sufficient(args, code):
    evals, selected, _ = evaluate_candidates(CFG, "sales_analyst", SALES, [cand("X", "analytics.get_sales_summary", args)], META)
    assert selected is None and code in evals[0].reason_codes


def test_omitted_regions_and_truncating_limits_not_sufficient():
    a = cand("A", "crm.get_customers", {"fields": ["region", "total_spend_cents"], "limit": 100, "month": "2026-09", "region": "North"}, "SUM_BY_REGION")
    b = cand("B", "analytics.get_transactions", {"month": "2026-09", "fields": ["region", "amount_cents"], "limit": 10}, "SUM_BY_REGION")
    evals, selected, _ = evaluate_candidates(CFG, "sales_analyst", SALES, [a, b], META)
    assert selected is None
    assert {"OMITS_REGIONS", "LIMIT_TRUNCATES_DATA"} <= set(evals[0].reason_codes)
    assert "LIMIT_TRUNCATES_DATA" in evals[1].reason_codes


def test_hallucinated_tools_and_extra_fields_rejected_not_executed():
    bad = [cand("A", "crm.export_everything", {}), cand("B", "analytics.get_sales_summary",
           {"month": "2026-09", "group_by": "region", "metric": "total_revenue", "personal_id": "x"})]
    evals, selected, canon = evaluate_candidates(CFG, "sales_analyst", SALES, bad, META)
    assert selected is None and canon == {}
    assert [e.reason_codes[0] for e in evals] == ["UNKNOWN_TOOL", "INVALID_ARGUMENTS"]


def test_llm_self_reported_risk_cannot_change_selection():
    good = cand("Z", "analytics.get_sales_summary", {"month": "2026-09", "group_by": "region", "metric": "total_revenue"}, risk="high")
    risky = cand("A", "crm.get_customers", {"fields": ["region", "total_spend_cents", "email"], "limit": 5000, "month": "2026-09"}, "SUM_BY_REGION", risk="low")
    _, selected, _ = evaluate_candidates(CFG, "sales_analyst", SALES, [risky, good], META)
    assert selected.candidate_id == "Z"


def test_ranking_prefers_lower_exposure_among_multiple_authorized():
    # Test-only policy variant that ALSO authorizes transaction rows (CONFIDENTIAL) for the sales task.
    cfg = copy.deepcopy(CFG)
    tp = cfg.policy.tasks[SALES]
    tp.model_visible_classes = [*tp.model_visible_classes, Classification.CONFIDENTIAL]
    tp.tools["analytics.get_transactions"] = copy.deepcopy(tp.tools["analytics.get_sales_summary"])
    tp.tools["analytics.get_transactions"].constraints = {"month": "2026-09"}
    agg = cand("Q", "analytics.get_sales_summary", {"month": "2026-09", "group_by": "region", "metric": "total_revenue"})
    txn = cand("A", "analytics.get_transactions", {"month": "2026-09", "fields": ["region", "amount_cents"], "limit": 5000},
               "SUM_BY_REGION", risk="low")
    evals, selected, _ = evaluate_candidates(cfg, "sales_analyst", SALES, [txn, agg], META)
    ranks = {e.candidate_id: (e.decision, e.covers_task, e.rank) for e in evals}
    assert ranks == {"A": (Decision.ALLOW, True, 2), "Q": (Decision.ALLOW, True, 1)}
    assert selected.candidate_id == "Q"  # lower max class, fewer rows/bytes -- despite stable-id ordering favoring "A"
    # The real policy still denies the transaction route outright.
    evals_real, _, _ = evaluate_candidates(CFG, "sales_analyst", SALES, [txn, agg], META)
    assert next(e for e in evals_real if e.candidate_id == "A").decision == Decision.DENY


def test_no_safe_plan_when_only_broad_candidates():
    evals, selected, _ = evaluate_candidates(CFG, "sales_analyst", SALES, asyncio.run(DeterministicPlanner(SALES).propose([]))[:2], META)
    assert selected is None and all(e.decision == Decision.DENY for e in evals)


def test_contact_plan_requires_approval_and_directory_denied():
    cands = asyncio.run(DeterministicPlanner(Intent.NOTIFY_CUSTOMER_105).propose([]))
    evals, selected, _ = evaluate_candidates(CFG, "customer_support", Intent.NOTIFY_CUSTOMER_105, cands, META)
    assert selected.tools == ["crm.get_customer_contact"] and selected.decision == Decision.APPROVAL_REQUIRED
    assert next(e for e in evals if e.tools == ["crm.get_customers"]).decision == Decision.DENY


def test_planner_output_parser_is_strict():
    with pytest.raises(ProviderError):
        parse_planner_output({"candidates": []}, "openai")
    with pytest.raises(ProviderError):
        parse_planner_output({"candidates": [{"steps": [{"tool_id": "x", "arguments_json": "[1,2]"}]}]}, "openai")
    ok = parse_planner_output({"candidates": [{"candidate_id": "z", "steps": [{"tool_id": "crm.get_connection_status", "arguments_json": "{}"}],
                                               "reducer": None, "rationale": "r", "self_reported_risk": "low"}]}, "openai")
    assert ok[0].candidate_id == "L1" and ok[0].origin == "openai"


def test_templates_cover_all_planned_intents():
    assert set(TEMPLATES) == {Intent.SALES_BY_REGION_2026_09, Intent.CRM_CONNECTION_STATUS, Intent.NOTIFY_CUSTOMER_105}
