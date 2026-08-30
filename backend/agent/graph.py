"""
LangGraph state graph for the product catalogue agent.

Defines a ReAct-style agent loop:
  agent (Gemini) ──▶ tools_condition ──▶ tools ──▶ agent ──▶ … ──▶ END
"""

import os
from typing import Annotated, TypedDict


from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from langchain_google_genai import ChatGoogleGenerativeAI

from .tools import search_catalogue, get_product_details, compare_products

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class State(TypedDict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Tools & Model
# ---------------------------------------------------------------------------

from langchain_core.messages import SystemMessage

SYSTEM_PROMPT = (
    "You are a helpful product catalogue assistant. "
    "When the user asks about products, use the available tools to search the catalogue, "
    "get product details, and compare products. "
    "Always respond with helpful information based on tool results. "
    "If no tools are needed, respond directly with text."
)

tools = [search_catalogue, get_product_details, compare_products]

model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
).bind_tools(tools)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def agent_node(state: State) -> dict:
    """Invoke the Gemini model with the current message history."""
    messages = state["messages"]
    # Inject system prompt if not already present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    response = model.invoke(messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(State)

builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))

builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile()
