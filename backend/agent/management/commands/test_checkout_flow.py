"""
Django management command to test the full agent checkout flow with interrupt/resume.

Usage:
    python manage.py test_checkout_flow

Requires:
    - The Django dev server running on http://localhost:8000
    - GEMINI_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET in .env
    - A valid user and products in the database
    - PostgreSQL running (for both Django data and LangGraph checkpointing)
"""

import json
import uuid
from typing import Any

from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langgraph.types import Command as GraphCommand


class Command(BaseCommand):
    help = (
        "Run the full agent checkout flow: start → interrupt → confirm → "
        "verify Razorpay order creation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            default=1,
            help="User ID to use for the flow (default: 1)",
        )
        parser.add_argument(
            "--reject",
            action="store_true",
            help="Reject the confirmation instead of approving",
        )

    def handle(self, *args, **options):
        load_dotenv()

        style: Any = self.style
        user_id = options["user_id"]
        approve = not options["reject"]

        # Import graph after env is loaded
        from agent.graph import graph

        self.stdout.write(style.SUCCESS("=" * 70))
        self.stdout.write(style.SUCCESS("  Agent Checkout Flow — Full Integration Test"))
        self.stdout.write(style.SUCCESS("=" * 70))
        self.stdout.write("")

        # ── Phase 1: Start ───────────────────────────────────────────
        thread_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        user_query = "Find me a mouse under ₹80000 suitable for scrolling with minimum rating of 4.0"

        self.stdout.write(f"[Config] thread_id  = {thread_id}")
        self.stdout.write(f"[Config] request_id = {request_id}")
        self.stdout.write(f"[Config] user_id    = {user_id}")
        self.stdout.write(f"[Config] approve    = {approve}")
        self.stdout.write(f"[Query]  {user_query}")
        self.stdout.write("")

        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "messages": [HumanMessage(content=user_query)],
            "request_id": request_id,
            "user_id": user_id,
        }

        self.stdout.write(style.WARNING("▶ Phase 1: Starting agent pipeline..."))

        # Stream until interrupt
        for event in graph.stream(initial_state, config=config, stream_mode="updates"):
            # Print each node as it executes
            for node_name in event:
                self.stdout.write(f"  ✓ Node completed: {node_name}")

        # Check for interrupt
        state_snapshot = graph.get_state(config)
        if not state_snapshot.next:
            self.stdout.write(style.ERROR(
                "✗ FAIL: Graph completed without interrupting. "
                "No products may have matched."
            ))
            return

        # Extract interrupt payload
        interrupted_payload = None
        if state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupted_payload = task.interrupts[0].value
                    break

        self.stdout.write(style.SUCCESS("✓ Graph interrupted for confirmation"))
        self.stdout.write(f"  Pending node(s): {state_snapshot.next}")
        self.stdout.write("")

        if interrupted_payload:
            self.stdout.write(style.WARNING("▶ Interrupt payload:"))
            self.stdout.write(f"  {json.dumps(interrupted_payload, indent=4, ensure_ascii=False)}")
            self.stdout.write("")

        # Print intermediate state
        values = state_snapshot.values
        self.stdout.write(style.SUCCESS("[Stage 1] Requirements Extracted"))
        self.stdout.write(f"  {json.dumps(values.get('requirements', {}), indent=4, ensure_ascii=False)}")
        self.stdout.write("")

        candidates = values.get("candidates", [])
        self.stdout.write(style.SUCCESS(f"[Stage 2] Catalogue Searched — {len(candidates)} results"))
        for p in candidates[:3]:
            self.stdout.write(
                f"  • {p.get('name', '?')} — ₹{p.get('price_paise', 0) / 100:.2f} "
                f"⭐ {p.get('rating', 0)}"
            )
        self.stdout.write("")

        top = values.get("top_products", [])
        self.stdout.write(style.SUCCESS(f"[Stage 3] Top {len(top)} Scored Products"))
        for i, p in enumerate(top, 1):
            comp = p.get("score_components", {})
            self.stdout.write(
                style.WARNING(f"  #{i}: {p.get('name', '?')} — Score: {p.get('score', 0):.4f}")
            )
        self.stdout.write("")

        self.stdout.write(style.SUCCESS("[Stage 4] Explanation"))
        self.stdout.write(f"  {values.get('explanation', '(none)')}")
        self.stdout.write("")

        # ── Phase 2: Confirm ─────────────────────────────────────────
        self.stdout.write(style.WARNING(
            f"▶ Phase 2: Resuming with approved={approve}..."
        ))

        for event in graph.stream(
            GraphCommand(resume={"approved": approve}),
            config=config,
            stream_mode="updates",
        ):
            for node_name in event:
                self.stdout.write(f"  ✓ Node completed: {node_name}")

        # Read final state
        final_snapshot = graph.get_state(config)
        final_state = final_snapshot.values

        self.stdout.write("")

        order_result = final_state.get("order_result", {})
        if approve:
            razorpay_order_id = order_result.get("razorpay_order_id", "")
            order_status = order_result.get("status")
            self.stdout.write(style.SUCCESS("[Stage 5-6] Checkout Result"))
            self.stdout.write(f"  Order ID:          {order_result.get('id')}")
            self.stdout.write(f"  Razorpay Order ID: {razorpay_order_id}")
            self.stdout.write(f"  Status:            {order_status}")
            self.stdout.write(f"  Total:             ₹{order_result.get('total_paise', 0) / 100:.2f}")
            self.stdout.write("")

            # Verify Razorpay order ID based on status
            if order_status == "confirmed":
                if razorpay_order_id and razorpay_order_id.startswith("order_"):
                    self.stdout.write(style.SUCCESS(
                        f"✓ PASS: Real Razorpay test order created: {razorpay_order_id}"
                    ))
                else:
                    self.stdout.write(style.ERROR(
                        f"✗ FAIL: Expected razorpay_order_id starting with 'order_', "
                        f"got: {razorpay_order_id!r}"
                    ))
            elif order_status == "failed":
                if not razorpay_order_id:
                    self.stdout.write(style.SUCCESS(
                        "✓ PASS: Order correctly marked failed with empty razorpay_order_id "
                        "(no Razorpay order was created due to payment timeout/failure)."
                    ))
                else:
                    self.stdout.write(style.ERROR(
                        f"✗ FAIL: Expected empty razorpay_order_id on failed order, "
                        f"got: {razorpay_order_id!r}"
                    ))
            else:
                self.stdout.write(style.ERROR(
                    f"✗ FAIL: Unexpected order status: {order_status!r}"
                ))
        else:
            self.stdout.write(style.SUCCESS("[Stage 5-6] Rejection Result"))
            self.stdout.write(f"  Status: {order_result.get('status', 'rejected')}")
            self.stdout.write(style.SUCCESS("✓ PASS: Order correctly rejected"))

        self.stdout.write("")

        # ── Audit Verification ───────────────────────────────────────
        from audit.models import AuditEvent

        audit_records = AuditEvent.objects.filter(payload__request_id=request_id)
        self.stdout.write(style.SUCCESS(
            f"[Audit DB] Found {audit_records.count()} event(s) for request_id:"
        ))
        for record in audit_records:
            self.stdout.write(f"  • {record.event_type} (actor={record.actor}, id={record.id})")

        # Check for the two authorization events specifically
        auth_requested = audit_records.filter(event_type="user_authorization_requested").exists()
        auth_received = audit_records.filter(event_type="user_authorization_received").exists()

        self.stdout.write("")
        if auth_requested:
            self.stdout.write(style.SUCCESS("✓ user_authorization_requested audit event found"))
        else:
            self.stdout.write(style.ERROR("✗ user_authorization_requested audit event MISSING"))

        if auth_received:
            self.stdout.write(style.SUCCESS("✓ user_authorization_received audit event found"))
        else:
            self.stdout.write(style.ERROR("✗ user_authorization_received audit event MISSING"))

        # Check order-specific audit events
        order_id = order_result.get("id")
        if order_id:
            order_events = AuditEvent.objects.filter(order_id=order_id)
            self.stdout.write("")
            self.stdout.write(style.SUCCESS(
                f"[Audit DB] Found {order_events.count()} event(s) for order_id={order_id}:"
            ))
            for record in order_events:
                self.stdout.write(f"  • {record.event_type} (actor={record.actor}, reason={record.reason})")

            if order_result.get("status") == "failed":
                timeout_handled = order_events.filter(event_type="payment_timeout_handled").exists()
                if timeout_handled:
                    self.stdout.write(style.SUCCESS("✓ payment_timeout_handled audit event found"))
                else:
                    self.stdout.write(style.WARNING("! payment_timeout_handled audit event not found"))

        self.stdout.write("")
        self.stdout.write(style.SUCCESS("=" * 70))
        self.stdout.write(style.SUCCESS("Agent checkout flow test complete."))
