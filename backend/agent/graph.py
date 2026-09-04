"""
LangGraph state graph for the product catalogue agent.

Deterministic 6-node pipeline with human-in-the-loop checkout:
  extract_requirements → search_catalogue → score_and_rank → explain_selection
    → request_confirmation ──(interrupt)──> process_confirmation → END

The graph is compiled with a PostgresSaver checkpointer so that interrupt/resume
works across separate HTTP requests (POST /agent/start/ and POST /agent/<id>/confirm/).

Each node records an audit event with a shared request_id for correlation.
"""

import json
import os
import uuid
from typing import Annotated, Any

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from audit.models import AuditEvent
from audit.services import record_audit_event
from policy.engine import check_policy, Decision
from .scoring import score_product_detailed
from .tools import search_catalogue, add_to_cart, create_order


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State(TypedDict):
    messages: Annotated[list, add_messages]
    request_id: str
    user_id: int
    requirements: dict
    candidates: list[dict]
    top_products: list[dict]
    explanation: str
    pending_confirmation: dict
    order_result: dict


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

_extraction_model = ChatGoogleGenerativeAI(
    model=_MODEL_NAME,
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    response_mime_type="application/json",
)

_explanation_model = ChatGoogleGenerativeAI(
    model=_MODEL_NAME,
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
    """Use Gemini structured output to turn the user message into structured requirements.

    If the initial Gemini call returns a malformed/unparseable response, logs
    an audit event with event_type 'malformed_ai_response' and retries once
    with a corrective follow-up prompt. If the retry also fails, falls back
    to empty requirements.
    """
    user_msg = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break

    if not user_msg:
        user_msg = ""

    request_id = state.get("request_id", str(uuid.uuid4()))
    structured_llm = _extraction_model.with_structured_output(Requirements)

    _EMPTY_REQUIREMENTS = {
        "category": None,
        "max_price": None,
        "min_rating": None,
        "required_features": [],
    }

    requirements = None

    # --- First attempt ---
    try:
        response = structured_llm.invoke([
            SystemMessage(content=_EXTRACTION_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        requirements = response.model_dump() if hasattr(response, "model_dump") else response
    except Exception as first_error:
        # Log malformed response audit event
        record_audit_event(
            event_type="malformed_ai_response",
            actor="agent",
            payload={
                "request_id": request_id,
                "user_message": user_msg,
                "error": str(first_error),
                "attempt": 1,
            },
        )

        # --- Retry once with corrective prompt ---
        try:
            corrective_prompt = (
                "Your previous response was malformed and could not be parsed. "
                "Please return ONLY a valid JSON object with exactly these keys: "
                'category, max_price, min_rating, required_features. '
                f"Original user request: {user_msg}"
            )
            response = structured_llm.invoke([
                SystemMessage(content=_EXTRACTION_SYSTEM),
                HumanMessage(content=corrective_prompt),
            ])
            requirements = response.model_dump() if hasattr(response, "model_dump") else response
        except Exception as retry_error:
            record_audit_event(
                event_type="malformed_ai_response",
                actor="agent",
                payload={
                    "request_id": request_id,
                    "user_message": user_msg,
                    "error": str(retry_error),
                    "attempt": 2,
                    "fallback": True,
                },
            )
            requirements = _EMPTY_REQUIREMENTS

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

        response = None
        try:
            response = _explanation_model.invoke([
                SystemMessage(content=_EXPLANATION_SYSTEM),
                HumanMessage(content=f"Top-3 scored products:\n{summary_text}"),
            ])
        except Exception:
            for fallback_m in ["gemini-3.7-flash", "gemini-flash-latest"]:
                try:
                    fallback_llm = ChatGoogleGenerativeAI(
                        model=fallback_m,
                        google_api_key=os.environ.get("GEMINI_API_KEY"),
                    )
                    response = fallback_llm.invoke([
                        SystemMessage(content=_EXPLANATION_SYSTEM),
                        HumanMessage(content=f"Top-3 scored products:\n{summary_text}"),
                    ])
                    if response and response.content:
                        break
                except Exception:
                    continue

        if response and response.content:
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
        else:
            top = top_products[0]
            explanation = (
                f"Selected {top.get('name', 'Product')} with score {top.get('score', 0):.2f} "
                f"for optimal price fit (₹{top.get('price_paise', 0) / 100:.2f}) and rating ({top.get('rating', 0)}/5)."
            )

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
# Node 5: Request Confirmation (interrupt)
# ---------------------------------------------------------------------------


def request_confirmation(state: State) -> dict:
    """Build a confirmation payload and interrupt the graph for human approval."""
    top_products = state.get("top_products", [])

    if not top_products:
        # Nothing to confirm — skip ahead with a rejection
        return {
            "pending_confirmation": {"status": "no_products"},
            "order_result": {"status": "no_products"},
        }

    winner = top_products[0]
    confirmation_payload = {
        "product_id": winner.get("id"),
        "product_name": winner.get("name", "Unknown"),
        "price_paise": winner.get("price_paise", 0),
        "price_display": f"₹{winner.get('price_paise', 0) / 100:.2f}",
        "explanation": state.get("explanation", ""),
        "score": winner.get("score"),
    }

    # Audit: authorization requested — guarded so re-entry after interrupt resume
    # doesn't produce a duplicate event in the audit trail.
    request_id = state["request_id"]
    if not AuditEvent.objects.filter(
        event_type="user_authorization_requested",
        payload__request_id=request_id,
    ).exists():
        record_audit_event(
            event_type="user_authorization_requested",
            actor="agent",
            payload={
                "request_id": request_id,
                "product": confirmation_payload["product_name"],
                "price": confirmation_payload["price_display"],
                "explanation": confirmation_payload["explanation"],
            },
        )

    # Halt the graph — this returns the payload to the caller and suspends
    # execution. The graph can be resumed via Command(resume=...).
    approval = interrupt(confirmation_payload)

    # After resume, `approval` contains the value passed in Command(resume=...).
    # Record the decision.
    approved = approval.get("approved", False) if isinstance(approval, dict) else bool(approval)

    record_audit_event(
        event_type="user_authorization_received",
        actor="agent",
        payload={
            "request_id": state["request_id"],
            "approved": approved,
        },
    )

    return {
        "pending_confirmation": {
            **confirmation_payload,
            "approved": approved,
        },
    }


# ---------------------------------------------------------------------------
# Node 6: Process Confirmation (after resume)
# ---------------------------------------------------------------------------


def process_confirmation(state: State) -> dict:
    """If approved, add the winning product to cart and create an order.

    Uses a deterministic idempotency key derived from request_id + user_id
    so that graph re-entry (e.g. after a crash/resume) won't create duplicate orders.
    """
    confirmation = state.get("pending_confirmation", {})
    approved = confirmation.get("approved", False)

    if not approved:
        return {
            "order_result": {"status": "rejected"},
            "messages": [AIMessage(content="Order was not approved. No action taken.")],
        }

    user_id = state.get("user_id")
    product_id = confirmation.get("product_id")

    if not user_id or not product_id:
        return {
            "order_result": {"status": "error", "detail": "Missing user_id or product_id"},
            "messages": [AIMessage(content="Cannot create order: missing user or product information.")],
        }

    # --- Policy gate (before any cart / Razorpay call) ---
    proposed_order = {
        "total_paise": confirmation.get("price_paise", 0),
        "items": [
            {
                "category": confirmation.get("category", ""),
                "price_paise": confirmation.get("price_paise", 0),
            }
        ],
    }
    policy_result = check_policy(user_id, proposed_order)

    record_audit_event(
        event_type="policy_checked",
        actor="system",
        payload={
            "request_id": state["request_id"],
            "decision": policy_result.decision.value,
            "reason": policy_result.reason,
            "rule_type": policy_result.rule_type,
        },
    )

    if policy_result.decision == Decision.BLOCK:
        return {
            "order_result": {"status": "blocked", "reason": policy_result.reason},
            "messages": [AIMessage(content=(
                f"Order blocked by policy: {policy_result.reason}"
            ))],
        }

    # --- End policy gate ---

    # Deterministic idempotency key from request_id + user_id
    # Ensures graph re-entry after crash/resume won't create duplicates.
    idem_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{state['request_id']}:{user_id}"))

    # Add the winning product to the cart
    cart_result = add_to_cart.invoke({
        "user_id": user_id,
        "product_id": product_id,
        "quantity": 1,
    })

    # Create the order (this also creates the Razorpay order)
    # Pass the deterministic idempotency key for duplicate prevention.
    order_result = create_order.invoke({
        "user_id": user_id,
        "idempotency_key": idem_key,
        "request_id": state["request_id"],
    })

    order_status = order_result.get("status", "")
    oid = order_result.get("id")

    if oid:
        try:
            AuditEvent.objects.filter(payload__request_id=state["request_id"], order_id__isnull=True).update(order_id=oid)
        except Exception:
            pass

    if order_status == "confirmed":
        record_audit_event(
            event_type="checkout_completed",
            actor="agent",
            payload={
                "request_id": state["request_id"],
                "user_id": user_id,
                "product_id": product_id,
                "order_id": oid,
                "razorpay_order_id": order_result.get("razorpay_order_id"),
            },
            order_id=oid,
        )
    else:
        record_audit_event(
            event_type="checkout_failed",
            actor="agent",
            payload={
                "request_id": state["request_id"],
                "user_id": user_id,
                "product_id": product_id,
                "order_id": oid,
                "status": order_status,
                "detail": order_result.get("detail", ""),
            },
            reason=order_result.get("detail", "Order checkout failed"),
            order_id=oid,
        )

    return {
        "order_result": order_result,
        "messages": [AIMessage(content=(
            f"Order created successfully! "
            f"Order ID: {order_result.get('id')}, "
            f"Razorpay Order: {order_result.get('razorpay_order_id')}"
        ) if order_status == "confirmed" else (
            f"Order failed: {order_result.get('detail', order_status)}"
        ))],
    }


# ---------------------------------------------------------------------------
# Checkpointer
# ---------------------------------------------------------------------------


def _build_checkpointer():
    """Build a PostgresSaver from Django's DATABASES settings.

    Uses psycopg (v3) connection pool with autocommit and dict_row as
    required by langgraph-checkpoint-postgres.
    """
    from psycopg import Connection
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres import PostgresSaver

    db = {
        "dbname": os.environ.get("POSTGRES_DB", "agentic_commerce"),
        "user": os.environ.get("POSTGRES_USER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
    }
    conninfo = (
        f"postgresql://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['dbname']}"
    )

    pool: ConnectionPool[Connection[dict[str, Any]]] = ConnectionPool(
        conninfo=conninfo,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

    return checkpointer


checkpointer = _build_checkpointer()


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(State)  # type: ignore[type-var]

builder.add_node("extract_requirements", extract_requirements)
builder.add_node("search_catalogue", search_catalogue_node)
builder.add_node("score_and_rank", score_and_rank)
builder.add_node("explain_selection", explain_selection)
builder.add_node("request_confirmation", request_confirmation)
builder.add_node("process_confirmation", process_confirmation)

builder.set_entry_point("extract_requirements")
builder.add_edge("extract_requirements", "search_catalogue")
builder.add_edge("search_catalogue", "score_and_rank")
builder.add_edge("score_and_rank", "explain_selection")
builder.add_edge("explain_selection", "request_confirmation")
builder.add_edge("request_confirmation", "process_confirmation")
builder.add_edge("process_confirmation", END)

graph = builder.compile(checkpointer=checkpointer)
