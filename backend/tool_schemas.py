"""Trusted input/output schemas for every gateway tool.

These models (not upstream MCP tool descriptions or annotations) are authoritative. The registry
pins a SHA-256 fingerprint of each schema; a change without an administrator updating the registry
fails readiness closed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from backend.contracts import Strict

Region = Literal["North", "South", "East", "West"]
Month = Literal["2026-08", "2026-09"]
CustomerField = Literal["id", "region", "display_name", "email", "synthetic_personal_id", "total_spend_cents"]
TransactionField = Literal["id", "customer_id", "region", "amount_cents", "month"]


def _unique(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate field")
    return values


# ---------------------------------------------------------------- crm.get_customers
class GetCustomersInput(Strict):
    fields: list[CustomerField] = Field(min_length=1, max_length=6)
    region: Region | None = None
    limit: int = Field(ge=1, le=5000)
    month: Month | None = None

    @model_validator(mode="after")
    def _check(self) -> GetCustomersInput:
        _unique(list(self.fields))
        if "total_spend_cents" in self.fields and self.month is None:
            raise ValueError("total_spend_cents requires month")
        return self


class CustomerRow(Strict):
    id: int | None = None
    region: Region | None = None
    display_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    synthetic_personal_id: str | None = Field(default=None, max_length=32)
    total_spend_cents: int | None = None


class GetCustomersOutput(Strict):
    rows: list[CustomerRow] = Field(max_length=5000)
    row_count: int


# ---------------------------------------------------------------- analytics.get_transactions
class GetTransactionsInput(Strict):
    month: Month
    fields: list[TransactionField] = Field(min_length=1, max_length=5)
    limit: int = Field(ge=1, le=5000)

    @model_validator(mode="after")
    def _check(self) -> GetTransactionsInput:
        _unique(list(self.fields))
        return self


class TransactionRow(Strict):
    id: int | None = None
    customer_id: int | None = None
    region: Region | None = None
    amount_cents: int | None = None
    month: Month | None = None


class GetTransactionsOutput(Strict):
    rows: list[TransactionRow] = Field(max_length=5000)
    row_count: int


# ---------------------------------------------------------------- analytics.get_sales_summary
class SalesSummaryInput(Strict):
    month: Month
    group_by: Literal["region"] = "region"
    metric: Literal["total_revenue", "average_sales"] = "total_revenue"


class SalesSummaryRow(Strict):
    region: Region
    value_cents: int = Field(ge=0)
    transaction_count: int = Field(ge=0)


class SalesSummaryOutput(Strict):
    month: Month
    group_by: Literal["region"]
    metric: Literal["total_revenue", "average_sales"]
    currency: Literal["USD"]
    rows: list[SalesSummaryRow] = Field(max_length=4)


# ---------------------------------------------------------------- crm.get_connection_status
class ConnectionStatusInput(Strict):
    pass


class ConnectionStatusOutput(Strict):
    connector: Literal["crm"]
    connected: bool
    verification: Literal["synthetic_local_digest"]


# ---------------------------------------------------------------- crm.get_customer_contact (P1)
class CustomerContactInput(Strict):
    customer_id: int = Field(ge=1, le=5000)
    fields: list[Literal["email"]] = Field(min_length=1, max_length=1)


class CustomerContactOutput(Strict):
    customer_id: int
    email: str = Field(max_length=128, pattern=r"^[a-z0-9._-]+@example\.com$")


SCHEMAS: dict[str, tuple[type[Strict], type[Strict]]] = {
    "crm.get_customers": (GetCustomersInput, GetCustomersOutput),
    "analytics.get_transactions": (GetTransactionsInput, GetTransactionsOutput),
    "analytics.get_sales_summary": (SalesSummaryInput, SalesSummaryOutput),
    "crm.get_connection_status": (ConnectionStatusInput, ConnectionStatusOutput),
    "crm.get_customer_contact": (CustomerContactInput, CustomerContactOutput),
}


def input_json_schema(tool_id: str) -> dict:
    schema = SCHEMAS[tool_id][0].model_json_schema()
    schema["additionalProperties"] = False
    return schema


def output_json_schema(tool_id: str) -> dict:
    return SCHEMAS[tool_id][1].model_json_schema()


def schema_fingerprint(tool_id: str) -> str:
    material = json.dumps(
        {"input": input_json_schema(tool_id), "output": output_json_schema(tool_id)}, sort_keys=True
    )
    return hashlib.sha256(material.encode()).hexdigest()
