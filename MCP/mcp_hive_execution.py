"""
Disabled Hive MCP execution stub.

This server is intentionally not wired into the default agent. It exists so the
Hive path has a stable tool contract when connection details and dependencies
are ready.
"""

import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("hive-sql-server")


@mcp.tool()
def execute_sql(query: str) -> str:
    """
    Placeholder for future Hive SELECT execution.

    Returns a structured not-configured response unless HIVE_MCP_ENABLED=true.
    No active Hive dependencies are required for the local SQLite workflow.
    """
    if os.getenv("HIVE_MCP_ENABLED", "false").strip().lower() != "true":
        return json.dumps({
            "status": "error",
            "error_type": "not_configured",
            "error_msg": (
                "Hive MCP execution is prepared but disabled. Set "
                "HIVE_MCP_ENABLED=true and provide Hive connection settings "
                "before wiring this server into the agent."
            ),
            "query": query,
        })

    return json.dumps({
        "status": "error",
        "error_type": "not_implemented",
        "error_msg": "Hive execution wiring is not implemented in this local build.",
        "query": query,
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
