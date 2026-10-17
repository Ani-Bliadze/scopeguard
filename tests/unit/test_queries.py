import sqlite3
from collections import defaultdict

import pytest

from backend.data.seed import CANARY_PREFIX, build_database
from mcp_servers import queries

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("q") / "q.sqlite"
    build_database(db, CANARY_PREFIX + "_unit")
    c = sqlite3.connect(db)
    yield c
    c.close()


def independent_totals(con, month):
    totals, counts = defaultdict(int), defaultdict(int)
    for region, amount in con.execute(
        "SELECT c.region, s.amount_cents FROM sales s, customers c WHERE c.id=s.customer_id AND s.month=?", (month,)
    ):
        totals[region] += amount
        counts[region] += 1
    return totals, counts


def test_sql_aggregate_matches_independent_totals(con):
    rows = queries.get_sales_summary(con, "2026-09", "total_revenue")
    totals, counts = independent_totals(con, "2026-09")
    assert len(rows) == 4
    for r in rows:
        assert r["value_cents"] == totals[r["region"]]
        assert r["transaction_count"] == counts[r["region"]]


def test_min_group_size_threshold_suppresses_small_groups(con, monkeypatch):
    monkeypatch.setattr(queries, "MIN_GROUP_CUSTOMERS", 1251)  # each region has exactly 1,250 customers
    assert queries.get_sales_summary(con, "2026-09", "total_revenue") == []


def test_projection_returns_only_requested_fields(con):
    rows = queries.get_customers(con, ["id", "region"], 3, None, None)
    assert rows and all(set(r) == {"id", "region"} for r in rows)


@pytest.mark.parametrize("fields", [["password"], ["id; DROP TABLE customers"], ["email", "email"], []])
def test_unknown_or_injected_fields_rejected(con, fields):
    with pytest.raises(queries.QueryError):
        queries.get_customers(con, fields, 1, None, None)


def test_region_value_is_parameterized(con):
    assert queries.get_customers(con, ["id"], 5, "North' OR '1'='1", None) == []


def test_backend_credential_verification(con):
    assert queries.verify_credential(con, "crm", CANARY_PREFIX + "_unit") is True
    assert queries.verify_credential(con, "crm", CANARY_PREFIX + "_wrong") is False
    assert queries.verify_credential(con, "crm", None) is False
