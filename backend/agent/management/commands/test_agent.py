"""
Django management command to test the LangGraph product catalogue agent.

Usage:
    python manage.py test_agent

Requires:
    - The Django dev server running on http://localhost:8000
    - GEMINI_API_KEY set in the environment (or .env file)
"""

import json
import uuid

from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage


class Command(BaseCommand):
    help = "Run the LangGraph agent pipeline with a sample product query and print the full trace."

    def handle(self, *args, **options):
        # Load environment variables from .env (for GEMINI_API_KEY)
        load_dotenv()

        # Import graph here (after env is loaded) so the API key is available
        from agent.graph import graph

        self.stdout.write(self.style.HTTP_INFO("=" * 70))  # type: ignore[attr-defined]
        self.stdout.write(self.style.HTTP_INFO("  LangGraph Agent — Product Catalogue Pipeline"))  # type: ignore[attr-defined]
        self.stdout.write(self.style.HTTP_INFO("=" * 70))  # type: ignore[attr-defined]
        self.stdout.write("")

        user_query = "Find me a mouse under ₹80000 suitable for scrolling with minimum rating of 4.0"
        request_id = str(uuid.uuid4())

        self.stdout.write(self.style.HTTP_INFO(f"[User Query] {user_query}"))  # type: ignore[attr-defined]
        self.stdout.write(self.style.HTTP_INFO(f"[Request ID] {request_id}"))  # type: ignore[attr-defined]
        self.stdout.write("")

        # Invoke the graph
        result = graph.invoke({
            "messages": [HumanMessage(content=user_query)],
            "request_id": request_id,
        })

        # ── Requirements ─────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("[Stage 1] Requirements Extracted"))  # type: ignore[attr-defined]
        reqs = result.get("requirements", {})
        self.stdout.write(f"  {json.dumps(reqs, indent=4, ensure_ascii=False)}")
        self.stdout.write("")

        # ── Candidates ───────────────────────────────────────────────
        candidates = result.get("candidates", [])
        self.stdout.write(self.style.SUCCESS(f"[Stage 2] Catalogue Searched — {len(candidates)} results"))  # type: ignore[attr-defined]
        for p in candidates[:5]:  # show first 5
            self.stdout.write(
                f"  • {p.get('name', '?')} — ₹{p.get('price_paise', 0) / 100:.2f} "
                f"⭐ {p.get('rating', 0)}"
            )
        if len(candidates) > 5:
            self.stdout.write(f"  ... and {len(candidates) - 5} more")
        self.stdout.write("")

        # ── Top 3 Scored ─────────────────────────────────────────────
        top = result.get("top_products", [])
        self.stdout.write(self.style.SUCCESS(f"[Stage 3] Top {len(top)} Scored Products"))  # type: ignore[attr-defined]
        for i, p in enumerate(top, 1):
            comp = p.get("score_components", {})
            self.stdout.write(
                self.style.WARNING(f"  #{i}: {p.get('name', '?')} — Score: {p.get('score', 0):.4f}")  # type: ignore[attr-defined]
            )
            self.stdout.write(
                f"       price_fit={comp.get('price_fit', 0):.4f}  "
                f"rating={comp.get('rating', 0):.4f}  "
                f"feature_overlap={comp.get('feature_overlap', 0):.4f}"
            )
            self.stdout.write(
                f"       ₹{p.get('price_paise', 0) / 100:.2f}  ⭐ {p.get('rating', 0)}"
            )
        self.stdout.write("")

        # ── Explanation ──────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("[Stage 4] Explanation"))  # type: ignore[attr-defined]
        self.stdout.write(f"  {result.get('explanation', '(none)')}")
        self.stdout.write("")

        # ── DB Audit Verification ────────────────────────────────────
        from audit.models import AuditEvent

        audit_records = AuditEvent.objects.filter(payload__request_id=request_id)  # type: ignore[attr-defined]
        self.stdout.write(self.style.SUCCESS(f"[Audit DB Check] Found {audit_records.count()} persisted audit event(s):"))  # type: ignore[attr-defined]
        for record in audit_records:
            self.stdout.write(f"  • {record.event_type} (actor={record.actor}, id={record.id})")
        self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("=" * 70))  # type: ignore[attr-defined]
        self.stdout.write(self.style.SUCCESS("Agent pipeline complete."))  # type: ignore[attr-defined]
