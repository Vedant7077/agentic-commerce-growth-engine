"""
Pure-Python product scoring — no LLM calls, no langchain imports.

Scores a candidate product against extracted user requirements using
three weighted components:

    price_fit      (0.40) — Rewards being under budget with best value.
                            A bell-curve centered at ~75 % of max_price so
                            that mid-range products score highest; very cheap
                            products are penalised slightly (they may cut
                            corners on quality), and over-budget products
                            score 0.

    rating         (0.35) — product["rating"] / 5.0, normalised to [0, 1].

    feature_overlap(0.25) — Fraction of required_features keywords found
                            (case-insensitive) in the product's description.
                            Each feature is checked as a substring so
                            multi-word features like "hot swappable" work.
"""

import re

# ── weights ──────────────────────────────────────────────────────────
W_PRICE = 0.40
W_RATING = 0.35
W_FEATURES = 0.25


def _price_fit(price_paise: int, max_price_paise: int | None) -> float:
    """Return a [0, 1] score for how well *price_paise* fits the budget.

    Rewards being comfortably under budget. Products over budget score 0.
    If no budget was specified, every product scores 1.0.
    """
    if max_price_paise is None or max_price_paise <= 0:
        return 1.0

    if price_paise > max_price_paise:
        return 0.0

    ratio = price_paise / max_price_paise  # 0 … 1
    score = max(0.0, min(1.0, 1.0 - ratio))
    return score


def _rating_score(rating: float) -> float:
    """Normalise a 0-5 star rating to [0, 1]."""
    return max(0.0, min(rating / 5.0, 1.0))


def _feature_overlap(required_features: list[str], description: str) -> float:
    """Fraction of *required_features* found in *description* (case-insensitive).

    Each feature is matched as a substring so multi-word features work.
    Returns 0.0 when the feature list is empty (no penalty).
    """
    if not required_features:
        return 1.0  # no features required → full marks

    description_lower = description.lower()
    hits = sum(
        1
        for feat in required_features
        if feat.lower() in description_lower
    )
    return hits / len(required_features)


# ── public API ───────────────────────────────────────────────────────

def score_product(product: dict, requirements: dict) -> float:
    """Score a single product against user requirements.

    Parameters
    ----------
    product : dict
        Must contain at least ``price_paise`` (int), ``rating`` (float),
        and ``description`` (str).
    requirements : dict
        Must contain ``max_price`` (int | None), ``min_rating`` (float | None),
        and ``required_features`` (list[str]).

    Returns
    -------
    float
        Weighted score in [0, 1].
    """
    pf = _price_fit(product["price_paise"], requirements.get("max_price"))
    rt = _rating_score(product.get("rating", 0.0))
    fo = _feature_overlap(
        requirements.get("required_features", []),
        product.get("description", ""),
    )
    return W_PRICE * pf + W_RATING * rt + W_FEATURES * fo


def score_product_detailed(
    product: dict, requirements: dict
) -> tuple[float, dict]:
    """Like :func:`score_product` but also returns component breakdown.

    Returns
    -------
    tuple[float, dict]
        ``(total_score, {"price_fit": …, "rating": …, "feature_overlap": …})``
    """
    pf = _price_fit(product["price_paise"], requirements.get("max_price"))
    rt = _rating_score(product.get("rating", 0.0))
    fo = _feature_overlap(
        requirements.get("required_features", []),
        product.get("description", ""),
    )
    total = W_PRICE * pf + W_RATING * rt + W_FEATURES * fo
    components = {
        "price_fit": round(pf, 4),
        "rating": round(rt, 4),
        "feature_overlap": round(fo, 4),
    }
    return total, components
