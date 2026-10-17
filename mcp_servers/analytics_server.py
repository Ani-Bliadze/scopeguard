"""Private Analytics MCP server (stdio only). Aggregates are computed in SQL."""

from __future__ import annotations

from typing import Literal

from mcp.server import MCPServer

from backend.tool_schemas import GetTransactionsOutput, SalesSummaryOutput
from mcp_servers import queries
from mcp_servers.runtime import db_connect

server = MCPServer("scopeguard-private-analytics", version="1.0.0")

TransactionField = Literal["id", "customer_id", "region", "amount_cents", "month"]


@server.tool(name="get_sales_summary", description="Aggregate sales by region (private).")
def get_sales_summary(
    month: Literal["2026-08", "2026-09"],
    group_by: Literal["region"] = "region",
    metric: Literal["total_revenue", "average_sales"] = "total_revenue",
) -> SalesSummaryOutput:
    con = db_connect()
    try:
        rows = queries.get_sales_summary(con, month, metric)
    finally:
        con.close()
    return SalesSummaryOutput.model_validate(
        {"month": month, "group_by": group_by, "metric": metric, "currency": "USD", "rows": rows}
    )


@server.tool(name="get_transactions", description="Transaction-level rows (private).")
def get_transactions(
    month: Literal["2026-08", "2026-09"], fields: list[TransactionField], limit: int
) -> GetTransactionsOutput:
    con = db_connect()
    try:
        rows = queries.get_transactions(con, month, list(fields), limit)
    finally:
        con.close()
    return GetTransactionsOutput.model_validate({"rows": rows, "row_count": len(rows)})


if __name__ == "__main__":
    server.run(transport="stdio")
