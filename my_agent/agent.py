"""
agent.py
--------
Constructs and compiles the LangGraph agent.
Graph flow: START -> llm_node <-> tool_node -> END
"""
import asyncio
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from my_agent.utils.nodes import build_tool_node, llm_node
from my_agent.utils.state import AgentState
from my_agent.utils.tools import cleanup_tools, init_tools


def should_continue(state: AgentState) -> Literal["tool_node", "__end__"]:
    """Route to tool_node if the LLM emitted tool calls, otherwise stop."""
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tool_node"
    return END


async def build_graph():
    """
    Initialises MCP tools, builds the graph, compiles, and returns it.
    Call once at application startup.
    """
    await init_tools()
    tool_node = build_tool_node()

    builder = StateGraph(AgentState)
    builder.add_node("llm_node", llm_node)
    builder.add_node("tool_node", tool_node)

    builder.add_edge(START, "llm_node")
    builder.add_conditional_edges(
        "llm_node",
        should_continue,
        ["tool_node", END],
    )
    builder.add_edge("tool_node", "llm_node")

    graph = builder.compile()
    print("Agent graph compiled successfully.")
    return graph


async def main():
    graph = await build_graph()
    user_query = "How many students are in the database?"
    result = await graph.ainvoke(
        {
            "user_query": user_query,
            "messages": [HumanMessage(content=user_query)],
            "retrieved_context": [],
            "llm_calls": 0,
        }
    )

    print("\n" + "=" * 60)
    print("CONVERSATION TRACE")
    print("=" * 60)
    for message in result["messages"]:
        message.pretty_print()
    print(f"\nLLM calls made: {result['llm_calls']}")

    await cleanup_tools()


if __name__ == "__main__":
    asyncio.run(main())
