"""
Growth analysis view.

GET /growth/analyze/ — runs raw SQL analytics, sends data to Gemini
for insight generation, persists the insights, and returns today's rows.
"""

import json
import os
from datetime import date

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from google import genai

from growth.models import GrowthInsight
from growth.services import (
    get_frequently_bought_together,
    get_underperforming_categories,
)


def _build_gemini_prompt(pairs, underperforming):
    """Build a grounded prompt that constrains Gemini to the supplied data."""
    return f"""You are a growth analyst for an e-commerce store.
Below is real order data. Generate exactly 2-3 short, concrete growth insights
in plain English. Each insight should be 1-2 sentences.

IMPORTANT RULES:
- Only reference facts present in the provided data below.
- Never invent numbers, product names, or categories not in the input.
- If a section has no data, skip insights for it.

=== Frequently Bought Together (product pairs & co-purchase count) ===
{json.dumps(pairs, indent=2)}

=== Underperforming Categories (categories with very few order-items) ===
{json.dumps(underperforming, indent=2)}

Return your answer as a JSON array of objects, each with:
- "insight_type": either "bundle_suggestion" or "underperforming_category"
- "description": the plain-English insight

Example format:
[
  {{"insight_type": "bundle_suggestion", "description": "..."}},
  {{"insight_type": "underperforming_category", "description": "..."}}
]

Return ONLY the JSON array, no markdown fences, no extra text."""


@api_view(["GET"])
def analyze_growth(request):
    """Run growth analysis: raw SQL → Gemini → persist insights → respond."""

    # Clear previous insights so each call represents a fresh clean analysis
    GrowthInsight.objects.all().delete()

    # 1. Gather raw data via SQL
    pairs = get_frequently_bought_together(limit=10)
    underperforming = get_underperforming_categories(threshold=3)

    # 2. Call Gemini with fallback across available models
    prompt = _build_gemini_prompt(pairs, underperforming)

    models_to_try = [
        os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        "gemini-3.7-flash",
        "gemini-flash-latest",
    ]

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = None
    last_err = None

    for m in models_to_try:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt,
            )
            if response and response.text:
                break
        except Exception as err:
            last_err = err
            continue

    if not response or not response.text:
        return Response(
            {"error": f"Gemini API error: {str(last_err)}"},
            status=503,
        )

    # 3. Parse Gemini response
    raw_text = response.text.strip()
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]  # remove opening fence line
        raw_text = raw_text.rsplit("```", 1)[0]  # remove closing fence
        raw_text = raw_text.strip()

    try:
        insights_data = json.loads(raw_text)
    except json.JSONDecodeError:
        return Response(
            {"error": "Failed to parse Gemini response", "raw": raw_text},
            status=502,
        )

    # 4. Persist each insight
    created = []
    for item in insights_data:
        insight = GrowthInsight.objects.create(
            insight_type=item.get("insight_type", "bundle_suggestion"),
            description=item.get("description", ""),
            supporting_data={
                "pairs": pairs,
                "underperforming": underperforming,
            },
        )
        created.append(insight.pk)

    # 5. Return the fresh insights (description strings only)
    insights = GrowthInsight.objects.order_by("-created_at")

    return Response({"insights": [insight.description for insight in insights]})
