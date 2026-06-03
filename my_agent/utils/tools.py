"""
tools.py
--------
Initialises both MCP clients and exposes:
  - rag_tool       : the single retrieve tool from the RAG server
  - execution_tools: SQL execution tools plus LLM-selectable RAG tools
  - all_tools      : same list, kept for compatibility
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from langchain_mcp_adapters.client import MultiServerMCPClient, load_mcp_tools

BASE_DIR = str(Path(__file__).resolve().parents[2])
load_dotenv(os.path.join(BASE_DIR, ".env"))

RAG_SERVER_PATH  = os.path.join(BASE_DIR, "MCP", "mcp_rag.py")
RAG_CONFIG_PATH  = os.path.join(BASE_DIR, "MCP", "mcp_rag.yaml")

HIVE_ENABLED = os.getenv("HIVE_MCP_ENABLED", "false").strip().lower() in ("true", "1", "yes")
if HIVE_ENABLED:
    TOOL_SERVER_PATH = os.path.join(BASE_DIR, "MCP", "mcp_hive_execution.py")
else:
    TOOL_SERVER_PATH = os.path.join(BASE_DIR, "MCP", "mcp_sql_execution.py")

SQLITE_DB_PATH   = os.path.join(BASE_DIR, "database", "schema.db")

RAG_SERVER_CONFIG = {
    "rag": {
        "command": sys.executable,
        "args": [RAG_SERVER_PATH],
        "transport": "stdio",
        "env": {
            **os.environ,
            "RETRIEVAL_CONFIG": RAG_CONFIG_PATH,
        },
    }
}

TOOL_SERVER_CONFIG = {
    "tools": {
        "command": sys.executable,
        "args": [TOOL_SERVER_PATH],
        "transport": "stdio",
        "env": {
            **os.environ,
            "SQLITE_DATABASE_PATH": SQLITE_DB_PATH,
            "RETRIEVAL_CONFIG": RAG_CONFIG_PATH,
        },
    }
}

# ── module-level tool lists (populated by init_tools) ─────────────────────────
rag_tool: object = None
execution_tools: list = []
all_tools: list = []

# ── keep session context managers alive for the app lifetime ──────────────────
_rag_session_ctx  = None
_tool_session_ctx = None


async def init_tools() -> None:
    global rag_tool, execution_tools, all_tools
    global _rag_session_ctx, _tool_session_ctx

    _rag_client  = MultiServerMCPClient(RAG_SERVER_CONFIG)
    _tool_client = MultiServerMCPClient(TOOL_SERVER_CONFIG)

    # Open sessions and hold them open — subprocesses stay alive
    _rag_session_ctx  = _rag_client.session("rag")
    _tool_session_ctx = _tool_client.session("tools")

    rag_session  = await _rag_session_ctx.__aenter__()
    tool_session = await _tool_session_ctx.__aenter__()

    rag_tools_list = await load_mcp_tools(rag_session)
    sql_tools_list = await load_mcp_tools(tool_session)

    if not rag_tools_list:
        raise RuntimeError("RAG MCP server returned no tools.")
    if not sql_tools_list:
        raise RuntimeError("Execution MCP server returned no tools.")

    rag_tool = rag_tools_list[0]
    execution_tools.clear()
    execution_tools.extend(rag_tools_list + sql_tools_list)
    all_tools.clear()
    all_tools.extend(execution_tools)

    print("RAG tool loaded :", rag_tool.name)
    print("LLM tools loaded:", [t.name for t in execution_tools])


async def cleanup_tools() -> None:
    """Call once on app shutdown to terminate subprocesses cleanly."""
    global _rag_session_ctx, _tool_session_ctx
    for ctx in (_rag_session_ctx, _tool_session_ctx):
        if not ctx:
            continue
        try:
            await ctx.__aexit__(None, None, None)
        except RuntimeError as exc:
            # The MCP stdio adapter can raise noisy cancel-scope errors on
            # Windows/Python 3.13 after subprocesses have already exited.
            print(f"MCP cleanup warning: {exc}")
    _rag_session_ctx = None
    _tool_session_ctx = None
