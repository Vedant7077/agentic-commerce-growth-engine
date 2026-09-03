"""
Django views for the LangGraph agent checkout flow.

POST /agent/start/          — Start the agent pipeline; returns interrupt payload
POST /agent/<thread_id>/confirm/ — Resume the agent with approval decision
"""

import uuid

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from langchain_core.messages import HumanMessage
from langgraph.types import Command


@api_view(["POST"])
def agent_start(request):
    """
    POST /agent/start/
    Body: { "message": str, "user_id": int }

    Starts the LangGraph agent pipeline. The graph runs until it hits
    the interrupt() call in request_confirmation, then returns the
    thread_id and the pending confirmation payload so the client can
    display it and ask the user to approve.
    """
    message = request.data.get("message")
    user_id = request.data.get("user_id")

    if not message:
        return Response(
            {"detail": "message is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    if user_id is None:
        return Response(
            {"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    # Import graph here to avoid circular imports and ensure env is loaded
    from agent.graph import graph

    thread_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=message)],
        "request_id": request_id,
        "user_id": int(user_id),
    }

    # Invoke the graph — it will run until interrupt() pauses it
    # When interrupt fires, invoke() returns the state so far.
    # We need to stream to capture the interrupt value.
    interrupted_payload = None

    for event in graph.stream(initial_state, config=config, stream_mode="updates"):
        # The interrupt payload is surfaced in the __interrupt__ key
        pass

    # After streaming completes (at the interrupt), read the graph state
    state_snapshot = graph.get_state(config)

    # Check if we're in an interrupted state
    if state_snapshot.next:
        # The graph is paused — extract the interrupt value
        if state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupted_payload = task.interrupts[0].value
                    break

    if interrupted_payload is not None:
        return Response({
            "status": "pending_confirmation",
            "thread_id": thread_id,
            "request_id": request_id,
            "pending_confirmation": interrupted_payload,
        })

    # If we didn't hit an interrupt (e.g. no products found), return the final state
    final_state = state_snapshot.values
    return Response({
        "status": "completed",
        "thread_id": thread_id,
        "request_id": request_id,
        "explanation": final_state.get("explanation", ""),
        "order_result": final_state.get("order_result"),
    })


@api_view(["POST"])
def agent_confirm(request, thread_id):
    """
    POST /agent/<thread_id>/confirm/
    Body: { "approved": bool }

    Resumes the interrupted graph with the user's approval decision.
    If approved, the graph continues to add_to_cart → create_order
    (which also creates a Razorpay order). Returns the final order result.
    """
    approved = request.data.get("approved")
    if approved is None:
        return Response(
            {"detail": "approved (bool) is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    from agent.graph import graph

    config = {"configurable": {"thread_id": thread_id}}

    # Verify the graph is actually paused for this thread
    state_snapshot = graph.get_state(config)
    if not state_snapshot.next:
        return Response(
            {"detail": "No pending confirmation for this thread_id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Resume the graph with the user's decision
    result_state = None
    for event in graph.stream(
        Command(resume={"approved": bool(approved)}),
        config=config,
        stream_mode="updates",
    ):
        # Capture the last state update
        result_state = event

    # Read the final state
    final_snapshot = graph.get_state(config)
    final_state = final_snapshot.values

    order_result = final_state.get("order_result", {})

    if bool(approved):
        return Response({
            "status": "order_created",
            "thread_id": thread_id,
            "order_result": order_result,
        })
    else:
        return Response({
            "status": "rejected",
            "thread_id": thread_id,
        })
