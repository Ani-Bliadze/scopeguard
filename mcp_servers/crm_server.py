"""Private CRM MCP server (stdio only). Reachable only by the ScopeGuard gateway's upstream client.

It holds a synthetic backend credential in its own environment and uses it to verify a connection;
it has no tool that returns the credential."""

from __future__ import annotations

import os
from typing import Literal

from mcp.server import MCPServer

from backend.tool_schemas import ConnectionStatusOutput, CustomerContactOutput, GetCustomersOutput
from mcp_servers import queries
from mcp_servers.runtime import db_connect

server = MCPServer("scopeguard-private-crm", version="1.0.0")

CustomerField = Literal["id", "region", "display_name", "email", "synthetic_personal_id", "total_spend_cents"]


@server.tool(name="get_customers", description="Customer-level records (private).")
def get_customers(
    fields: list[CustomerField],
    limit: int,
    region: Literal["North", "South", "East", "West"] | None = None,
    month: Literal["2026-08", "2026-09"] | None = None,
) -> GetCustomersOutput:
    con = db_connect()
    try:
        rows = queries.get_customers(con, list(fields), limit, region, month)
    finally:
        con.close()
    return GetCustomersOutput.model_validate({"rows": rows, "row_count": len(rows)})


@server.tool(name="get_customer_contact", description="One customer's contact field (private).")
def get_customer_contact(customer_id: int, fields: list[Literal["email"]]) -> CustomerContactOutput:
    con = db_connect()
    try:
        email = queries.get_customer_email(con, customer_id)
    finally:
        con.close()
    return CustomerContactOutput(customer_id=customer_id, email=email)


@server.tool(name="get_connection_status", description="Verify the backend connector credential.")
def get_connection_status() -> ConnectionStatusOutput:
    # The credential is used here and never returned.
    provided = os.environ.get("SCOPEGUARD_CRM_CREDENTIAL")
    con = db_connect()
    try:
        ok = queries.verify_credential(con, "crm", provided)
    finally:
        con.close()
    return ConnectionStatusOutput(connector="crm", connected=ok, verification="synthetic_local_digest")


if __name__ == "__main__":
    server.run(transport="stdio")
