"""
nodes.py
--------
LangGraph node functions for the SQL assistant.

The LLM decides whether to call schema RAG (`retrive_schema_rag`), SQL execution
(`execute_sql`), or answer directly. There is no deterministic retrieval node in
the graph.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import ToolNode

from my_agent.utils import tools as tool_registry
from my_agent.utils.state import AgentState

logger = logging.getLogger("agent.nodes")

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen3.5:9b")
_REASONING = os.getenv("OLLAMA_REASONING", "true").strip().lower() in ("true", "1", "yes")
print(f"ChatOllama model: {_CHAT_MODEL}  |  thinking={'on' if _REASONING else 'off'}")

_base_model = ChatOllama(
    model=_CHAT_MODEL,
    temperature=0,
    reasoning=_REASONING,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
    num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "512")),
)
_model_with_tools = None

_HIVE_ENABLED = os.getenv("HIVE_MCP_ENABLED", "false").strip().lower() in ("true", "1", "yes")

if _HIVE_ENABLED:
    SYSTEM_PROMPT = """You are a SQL data assistant with a live Hive / Apache Spark SQL database for the curated_datamodels data model.

Available tools:
- retrive_schema_rag: retrieve curated table DDL and join relations when you need schema context.
- execute_sql: execute read-only Hive SQL SELECT queries against the database.

STRICT RULES — follow every rule without exception:
1. For ANY question about counts, totals, lists, averages, rates, trends, or data values — you MUST call execute_sql.
2. If you do not know the table name, call retrive_schema_rag first, then IMMEDIATELY call execute_sql with a SELECT query.
3. NEVER describe DDL or schema to the user — always run execute_sql and report the actual data.
4. NEVER answer without calling execute_sql for data questions.
5. After execute_sql returns rows, summarize the result in plain language.
6. Core tables: curated_datamodels.citizen_student (students), curated_datamodels.citizen_school (schools), curated_datamodels.school_student_attendance_fact (attendance), curated_datamodels.school_academic_performance_fact (performance), curated_datamodels.scheme_benefits_fact, curated_datamodels.mid_day_meal_serving_fact, curated_datamodels.school_infrastructure_progress_fact.
7. The database is Hive — use Hive/Spark-compatible SQL only. Use the correct database prefix (e.g. write `curated_datamodels.citizen_student`).
"""
else:
    SYSTEM_PROMPT = """You are a SQL data assistant with a live SQLite sample database for the curated_datamodels school data model.

Available tools:
- retrive_schema_rag: retrieve curated table DDL and join relations when you need schema context.
- execute_sql: execute read-only SQLite SELECT queries against the sample database.

STRICT RULES — follow every rule without exception:
1. For ANY question about counts, totals, lists, averages, rates, trends, or data values — you MUST call execute_sql.
2. If you do not know the table name, call retrive_schema_rag first, then IMMEDIATELY call execute_sql with a SELECT query.
3. NEVER describe DDL or schema to the user — always run execute_sql and report the actual data.
4. NEVER answer without calling execute_sql for data questions.
5. After execute_sql returns rows, summarize the result in plain language.
6. Core tables: citizen_student (students), citizen_school (schools), school_student_attendance_fact (attendance), school_academic_performance_fact (performance), scheme_benefits_fact, mid_day_meal_serving_fact, school_infrastructure_progress_fact.
7. The database is SQLite — use SQLite-compatible SQL only. All tables are in the main schema with no prefix (e.g. write `citizen_student` instead of `curated_datamodels.citizen_student`).
"""


def _get_model():
    global _model_with_tools
    if _model_with_tools is None:
        if not tool_registry.execution_tools:
            raise RuntimeError(
                "Tools not loaded. Make sure init_tools() was awaited before compiling the graph."
            )
        _model_with_tools = _base_model.bind_tools(tool_registry.execution_tools)
    return _model_with_tools


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower().replace("data base", "database"))


def _needs_data_tool(query: str) -> bool:
    q = _normalize_query(query)
    triggers = (
        "how many", "count", "number of", "total", "list", "show", "what is",
        "average", "avg", "percent", "rate", "trend", "chart", "pie", "bar",
        "heatmap", "student", "teacher", "gender", "district", "school",
        "attendance", "absent", "absence", "marks", "score", "risk", "scheme",
        "meal", "infrastructure", "database", "table",
    )
    return any(trigger in q for trigger in triggers)


def _tool_messages(messages: list, name: str | None = None) -> list[ToolMessage]:
    out = [m for m in messages if isinstance(m, ToolMessage)]
    if name:
        out = [m for m in out if getattr(m, "name", None) == name]
    return out


def _summarize_sql_result(user_query: str, tool_content: str) -> str | None:
    try:
        payload = json.loads(tool_content) if isinstance(tool_content, str) else tool_content
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return None

    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if not rows:
        return "The query ran successfully but returned no rows."

    q = _normalize_query(user_query)
    if len(rows) == 1 and len(columns) == 1:
        val = rows[0].get(columns[0])
        if re.search(r"how many|count|number of|total|average|avg", q):
            label = columns[0].replace("_", " ")
            return f"**{val:,}** ({label})." if isinstance(val, (int, float)) else f"**{val}** ({label})."

    if len(rows) <= 15 and columns:
        header = " | ".join(columns)
        body = "\n".join(
            " | ".join(str(row.get(column, "")) for column in columns)
            for row in rows[:15]
        )
        extra = ""
        if len(rows) < payload.get("row_count", len(rows)):
            extra = f"\n\n_Showing {len(rows)} of {payload.get('row_count', len(rows))} rows._"
        return f"**Query results:**\n\n{header}\n{body}{extra}"

    return (
        f"Query returned **{payload.get('row_count', len(rows))}** rows "
        f"({', '.join(columns[:6])}{'...' if len(columns) > 6 else ''})."
    )


def llm_node(state: AgentState) -> dict:
    """
    Invoke the LLM. The LLM may call schema retrieval, execute SQL, or answer.
    A one-retry guard nudges data questions back to tools if the model answers
    without a tool call on its first attempt.
    """
    t0 = time.perf_counter()
    history = state.get("messages", [])
    if not history:
        history = [HumanMessage(content=state["user_query"])]

    sql_results = _tool_messages(history, "execute_sql")
    if sql_results:
        summary = _summarize_sql_result(state["user_query"], sql_results[-1].content)
        if summary:
            logger.info("llm_node: summarized SQL result in %.2fs", time.perf_counter() - t0)
            return {
                "messages": [AIMessage(content=summary)],
                "llm_calls": state.get("llm_calls", 0),
            }

    system_message = SystemMessage(content=SYSTEM_PROMPT)
    messages_for_llm = [system_message] + history
    response = _get_model().invoke(messages_for_llm)
    llm_steps = 1

    # Retry 1: model answered without calling any tool at all
    if (
        _needs_data_tool(state["user_query"])
        and not getattr(response, "tool_calls", None)
        and not _tool_messages(history)
    ):
        retry_hint = HumanMessage(
            content=(
                "This is a database question. You MUST call retrive_schema_rag first "
                "if you don't know the table, then call execute_sql. "
                "Do NOT answer without running SQL."
            )
        )
        response = _get_model().invoke(messages_for_llm + [retry_hint])
        llm_steps += 1

    # Retry 2: model called RAG but did not follow up with execute_sql
    rag_results = _tool_messages(history, "retrive_schema_rag")
    sql_called = _tool_messages(history, "execute_sql")
    if (
        rag_results
        and not sql_called
        and not getattr(response, "tool_calls", None)
        and _needs_data_tool(state["user_query"])
    ):
        db_type = "Hive" if _HIVE_ENABLED else "SQLite"
        sql_nudge = HumanMessage(
            content=(
                f'The user asked: "{state["user_query"]}"\n\n'
                "You have already retrieved the schema context above. "
                f"Now call execute_sql with a valid {db_type} SELECT query to answer that question. "
                "Do NOT describe the schema — call execute_sql right now."
            )
        )
        response = _get_model().invoke(messages_for_llm + [sql_nudge])
        llm_steps += 1

    logger.info("llm_node: completed in %.2fs", time.perf_counter() - t0)
    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + llm_steps,
    }


def build_tool_node() -> ToolNode:
    """Returns a ToolNode bound to SQL and RAG MCP tools."""
    if not tool_registry.execution_tools:
        raise RuntimeError("Tools not loaded before building tool node.")
    return ToolNode(tool_registry.execution_tools)
