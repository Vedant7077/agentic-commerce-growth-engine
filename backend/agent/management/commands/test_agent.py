"""
Django management command to test the LangGraph product catalogue agent.

Usage:
    python manage.py test_agent

Requires:
    - The Django dev server running on http://localhost:8000
    - GEMINI_API_KEY set in the environment (or .env file)
"""

import json

from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


class Command(BaseCommand):
    help = "Run the LangGraph agent with a sample product query and print the full reasoning trace."

    def handle(self, *args, **options):
        # Load environment variables from .env (for GEMINI_API_KEY)
        load_dotenv()

        # Import graph here (after env is loaded) so the API key is available
        from agent.graph import graph

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("  LangGraph Agent — Product Catalogue"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write("")

        user_query = "Find me a mechanical keyboard under ₹80000 suitable for programming"

        self.stdout.write(self.style.HTTP_INFO(f"[User Query] {user_query}"))
        self.stdout.write("")

        # Invoke the graph
        result = graph.invoke({
            "messages": [HumanMessage(content=user_query)],
        })

        # Print every message in the reasoning trace
        for msg in result["messages"]:
            if isinstance(msg, HumanMessage):
                self.stdout.write(self.style.HTTP_INFO(f"[HumanMessage]"))
                self.stdout.write(f"  {msg.content}")
                self.stdout.write("")

            elif isinstance(msg, AIMessage):
                self.stdout.write(self.style.SUCCESS(f"[AIMessage]"))
                if msg.content:
                    self.stdout.write(f"  {msg.content}")

                # Print tool calls if present
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        self.stdout.write(
                            self.style.WARNING(f"  ↳ Tool Call: {tc['name']}")
                        )
                        self.stdout.write(
                            f"    Args: {json.dumps(tc['args'], indent=6, ensure_ascii=False)}"
                        )
                self.stdout.write("")

            elif isinstance(msg, ToolMessage):
                self.stdout.write(self.style.NOTICE(f"[ToolMessage] ({msg.name})"))
                # Pretty-print tool response (truncate if very long)
                try:
                    parsed = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    formatted = str(msg.content)

                # Show first 2000 chars to keep output readable
                if len(formatted) > 2000:
                    self.stdout.write(f"  {formatted[:2000]}")
                    self.stdout.write(f"  ... (truncated, {len(formatted)} chars total)")
                else:
                    self.stdout.write(f"  {formatted}")
                self.stdout.write("")

            else:
                self.stdout.write(f"[{type(msg).__name__}] {msg.content}")
                self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.SUCCESS("Agent run complete."))
