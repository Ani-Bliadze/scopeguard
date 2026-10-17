"""SQL owned by the private upstream services. Field names map through fixed fragments; values are
bound parameters. Aggregation happens in SQL so broad rows are never fetched for summary tasks."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3

CUSTOMER_FIELD_SQL = {
    "id": "c.id",
    "region": "c.region",
    "display_name": "c.display_name",
    "email": "c.email",
    "synthetic_personal_id": "c.synthetic_personal_id",
    "total_spend_cents": "COALESCE(SUM(s.amount_cents), 0)",
}
TRANSACTION_FIELD_SQL = {
    "id": "s.id",
    "customer_id": "s.customer_id",
    "region": "c.region",
    "amount_cents": "s.amount_cents",
    "month": "s.month",
}
MIN_GROUP_CUSTOMERS = 20


class QueryError(Exception):
    """Fixed-code error; never carries row data."""


def _check_fields(fields: list[str], allowed: dict[str, str]) -> None:
    if not fields or any(f not in allowed for f in fields) or len(set(fields)) != len(fields):
        raise QueryError("INVALID_FIELDS")


def get_customers(con: sqlite3.Connection, fields: list[str], limit: int, region: str | None, month: str | None):
    _check_fields(fields, CUSTOMER_FIELD_SQL)
    if not 1 <= limit <= 5000:
        raise QueryError("INVALID_LIMIT")
    cols = ", ".join(f"{CUSTOMER_FIELD_SQL[f]} AS {f}" for f in fields)
    params: list = []
    join = ""
    if "total_spend_cents" in fields:
        if month is None:
            raise QueryError("MONTH_REQUIRED")
        join = "LEFT JOIN sales s ON s.customer_id = c.id AND s.month = ?"
        params.append(month)
    where = ""
    if region is not None:
        where = "WHERE c.region = ?"
        params.append(region)
    sql = f"SELECT {cols} FROM customers c {join} {where} GROUP BY c.id ORDER BY c.id LIMIT ?"
    params.append(limit)
    return [dict(zip(fields, r, strict=True)) for r in con.execute(sql, params).fetchall()]


def get_transactions(con: sqlite3.Connection, month: str, fields: list[str], limit: int):
    _check_fields(fields, TRANSACTION_FIELD_SQL)
    if not 1 <= limit <= 5000:
        raise QueryError("INVALID_LIMIT")
    cols = ", ".join(f"{TRANSACTION_FIELD_SQL[f]} AS {f}" for f in fields)
    sql = (
        f"SELECT {cols} FROM sales s JOIN customers c ON c.id = s.customer_id "
        "WHERE s.month = ? ORDER BY s.id LIMIT ?"
    )
    return [dict(zip(fields, r, strict=True)) for r in con.execute(sql, (month, limit)).fetchall()]


def get_sales_summary(con: sqlite3.Connection, month: str, metric: str):
    agg = {"total_revenue": "SUM(s.amount_cents)", "average_sales": "CAST(ROUND(AVG(s.amount_cents)) AS INTEGER)"}
    if metric not in agg:
        raise QueryError("INVALID_METRIC")
    sql = (
        f"SELECT c.region, {agg[metric]}, COUNT(*), COUNT(DISTINCT s.customer_id) "
        "FROM sales s JOIN customers c ON c.id = s.customer_id WHERE s.month = ? "
        "GROUP BY c.region HAVING COUNT(DISTINCT s.customer_id) >= ? ORDER BY c.region"
    )
    rows = con.execute(sql, (month, MIN_GROUP_CUSTOMERS)).fetchall()
    return [{"region": r[0], "value_cents": int(r[1]), "transaction_count": int(r[2])} for r in rows]


def get_customer_email(con: sqlite3.Connection, customer_id: int) -> str:
    row = con.execute("SELECT email FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if row is None:
        raise QueryError("NOT_FOUND")
    return row[0]


def verify_credential(con: sqlite3.Connection, connector: str, provided: str | None) -> bool:
    row = con.execute("SELECT expected_sha256 FROM credential_digests WHERE connector = ?", (connector,)).fetchone()
    if row is None or not provided:
        return False
    return hmac.compare_digest(hashlib.sha256(provided.encode()).hexdigest(), row[0])
