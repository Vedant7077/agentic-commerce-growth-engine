"""
LangGraph state graph for the product catalogue agent.

Deterministic 4-node pipeline:
  extract_requirements → search_catalogue → score_and_rank → explain_selection → END

Each node records an audit event with a shared request_id for correlation.
"""

import json
import os
import uuid
from typing import Annotated, Any

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from audit.services import record_audit_event
from .scoring import score_product_detailed
from .tools import search_catalogue

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State(TypedDict):
    messages: Annotated[list, add_messages]
    request_id: str
    requirements: dict
    candidates: list[dict]
    top_products: list[dict]
    explanation: str


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_extraction_model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    response_mime_type="application/json",
)

_explanation_model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = (
    "You are a requirement-extraction assistant. "
    "Given a user message about a product they want, extract structured "
    "requirements as a JSON object with exactly these keys:\n"
    '  "category"  — product category string (e.g. "keyboards", "mice"), or null\n'
    '  "max_price" — maximum budget in paise (1 INR = 100 paise), integer, or null\n'
    '  "min_rating"— minimum acceptable star rating (0-5 float), or null\n'
    '  "required_features" — list of feature keywords (strings)\n'
    "\n"
    "Output ONLY the JSON object, no extra text."
)

_EXPLANATION_SYSTEM = (
    "You are a product recommendation explainer. "
    "You will receive the top-3 scored products with their score breakdowns. "
    "Write a 2-3 sentence explanation of why the #1 pick was chosen, "
    "explicitly referencing the provided score components (price_fit, rating, "
    "feature_overlap). Do NOT reference any original user message."
)


# ---------------------------------------------------------------------------
# Node 1: Extract Requirements
# ---------------------------------------------------------------------------


from pydantic import BaseModel, Field

class Requirements(BaseModel):
    category: str | None = Field(default=None, description="product category string (e.g. 'keyboards', 'mice'), or null")
    max_price: int | None = Field(default=None, description="maximum budget in paise (1 INR = 100 paise), integer, or null")
    min_rating: float | None = Field(default=None, description="minimum acceptable star rating (0-5 float), or null")
    required_features: list[str] = Field(default_factory=list, description="list of feature keywords (strings)")

def extract_requirements(state: State) -> dict:
    """Use Gemini structured output to turn the user message into structured requirements."""
    user_msg = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break

    if not user_msg:
        user_msg = ""

    structured_llm = _extraction_model.with_structured_output(Requirements)
    
    try:
        response = structured_llm.invoke([
            SystemMessage(content=_EXTRACTION_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        requirements = response.model_dump() if hasattr(response, "model_dump") else response
    except Exception:
        requirements = {
            "category": None,
            "max_price": None,
            "min_rating": None,
            "required_features": [],
        }

    request_id = state.get("request_id", str(uuid.uuid4()))

    record_audit_event(
        event_type="requirements_extracted",
        actor="agent",
        payload={
            "request_id": request_id,
            "user_message": user_msg,
            "requirements": requirements,
        },
    )

    return {"requirements": requirements, "request_id": request_id}


# ---------------------------------------------------------------------------
# Node 2: Search Catalogue
# ---------------------------------------------------------------------------


def search_catalogue_node(state: State) -> dict:
    """Call the search_catalogue tool directly with extracted requirements."""
    reqs = state["requirements"]

    # Build tool arguments from requirements
    tool_args = {"query": ""}
    if reqs.get("category"):
        tool_args["category"] = reqs["category"]

    if reqs.get("max_price") is not None:
        tool_args["max_price"] = reqs["max_price"]

    # Call the tool function directly
    candidates = search_catalogue.invoke(tool_args)

    # Ensure candidates is a list of dicts
    if isinstance(candidates, str):
        try:
            candidates = json.loads(candidates)
        except (json.JSONDecodeError, TypeError):
            candidates = []

    record_audit_event(
        event_type="catalogue_searched",
        actor="agent",
        payload={
            "request_id": state["request_id"],
            "search_args": tool_args,
            "result_count": len(candidates),
        },
    )

    return {"candidates": candidates}


# ---------------------------------------------------------------------------
# Node 3: Score & Rank
# ---------------------------------------------------------------------------


def score_and_rank(state: State) -> dict:
    """Score all candidates with the pure-Python formula and keep top 3."""
    reqs = state["requirements"]
    candidates = state.get("candidates", [])

    scored = []
    for product in candidates:
        total, components = score_product_detailed(product, reqs)
        scored.append({
            **product,
            "score": round(total, 4),
            "score_components": components,
        })

    # Sort descending by score
    scored.sort(key=lambda p: p["score"], reverse=True)
    top_products = scored[:3]

    record_audit_event(
        event_type="candidates_scored",
        actor="agent",
        payload={
            "request_id": state["request_id"],
            "total_candidates": len(candidates),
            "top_products": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "score": p["score"],
                    "score_components": p["score_components"],
                }
                for p in top_products
            ],
        },
    )

    return {"top_products": top_products}


# ---------------------------------------------------------------------------
# Node 4: Explain Selection
# ---------------------------------------------------------------------------


def explain_selection(state: State) -> dict:
    """Ask Gemini to explain why #1 was chosen, grounded in score breakdowns."""
    top_products = state.get("top_products", [])

    if not top_products:
        explanation = "No products matched your requirements."
    else:
        # Build a summary of top-3 for the LLM — scores only, no user message
        product_summaries = []
        for i, p in enumerate(top_products, 1):
            product_summaries.append(
                f"#{i}: {p.get('name', 'Unknown')} "
                f"(₹{p.get('price_paise', 0) / 100:.2f}) — "
                f"Total Score: {p['score']:.4f}, "
                f"Components: price_fit={p['score_components']['price_fit']}, "
                f"rating={p['score_components']['rating']}, "
                f"feature_overlap={p['score_components']['feature_overlap']}"
            )
        summary_text = "\n".join(product_summaries)

        response = _explanation_model.invoke([
            SystemMessage(content=_EXPLANATION_SYSTEM),
            HumanMessage(content=f"Top-3 scored products:\n{summary_text}"),
        ])
        if isinstance(response.content, str):
            explanation = response.content
        elif isinstance(response.content, list):
            text_blocks = []
            for item in response.content:
                if isinstance(item, dict) and "text" in item:
                    text_blocks.append(item["text"])
                elif isinstance(item, str):
                    text_blocks.append(item)
            explanation = "".join(text_blocks) if text_blocks else str(response.content)
        else:
            explanation = str(response.content)

    record_audit_event(
        event_type="product_selected",
        actor="agent",
        payload={
            "request_id": state["request_id"],
            "winner_id": top_products[0].get("id") if top_products else None,
            "winner_name": top_products[0].get("name") if top_products else None,
            "explanation": explanation,
        },
    )

    return {
        "explanation": explanation,
        "messages": [AIMessage(content=explanation)],
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(State)  # type: ignore[type-var]

builder.add_node("extract_requirements", extract_requirements)
builder.add_node("search_catalogue", search_catalogue_node)
builder.add_node("score_and_rank", score_and_rank)
builder.add_node("explain_selection", explain_selection)

builder.set_entry_point("extract_requirements")
builder.add_edge("extract_requirements", "search_catalogue")
builder.add_edge("search_catalogue", "score_and_rank")
builder.add_edge("score_and_rank", "explain_selection")
builder.add_edge("explain_selection", END)

graph = builder.compile()
