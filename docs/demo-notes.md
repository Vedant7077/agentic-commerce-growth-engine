# Day 8 — Policy Engine Verification

```
======================================================================
  Agent Checkout Flow — Full Integration Test
======================================================================

[Config] thread_id  = 7e926512-fa1b-4d63-8003-a345da661a50
[Config] request_id = d4da8f71-678c-4774-bd7a-2773c41f31ce
[Config] user_id    = 1
[Config] approve    = True
[Query]  Find me a mouse under ₹80000 suitable for scrolling with minimum rating of 4.0

▶ Phase 1: Starting agent pipeline...
  ✓ Node completed: extract_requirements
  ✓ Node completed: search_catalogue
  ✓ Node completed: score_and_rank
  ✓ Node completed: explain_selection
  ✓ Node completed: __interrupt__
✓ Graph interrupted for confirmation
  Pending node(s): ('request_confirmation',)

▶ Interrupt payload:
  {
    "product_id": 48,
    "product_name": "ScrollMaster Pro Wireless Mouse",
    "price_paise": 655336,
    "price_display": "₹6553.36",
    "explanation": "The ScrollMaster Pro Wireless Mouse secured the top recommendation with a leading total score of 0.9392, anchored by a perfect feature_overlap score of 1.0 that fully aligns with your required specifications. It also earned strong marks across the remaining categories, achieving a high rating score of 0.92 and a competitive price_fit score of 0.9181. This well-rounded combination of full feature matching, stellar user feedback, and budget compatibility makes it the clear winner.",
    "score": 0.9392
}

[Stage 1] Requirements Extracted
  {
    "category": "mice",
    "max_price": 8000000,
    "min_rating": 4.0,
    "required_features": [
        "scrolling"
    ]
}

[Stage 2] Catalogue Searched — 6 results
  • BasicClick USB Wired Mouse — ₹592.28 ⭐ 2.9
  • ScrollMaster Pro Wireless Mouse — ₹6553.36 ⭐ 4.6
  • MegaClaw RGB Gaming Mouse — ₹2466.41 ⭐ 3.6

[Stage 3] Top 3 Scored Products
  #1: ScrollMaster Pro Wireless Mouse — Score: 0.9392
  #2: SwiftClick Ultra-Light Gaming Mouse — Score: 0.9224
  #3: PrecisionGlide Ergonomic Mouse — Score: 0.7082

[Stage 4] Explanation
  The ScrollMaster Pro Wireless Mouse secured the top recommendation with a leading total score of 0.9392, anchored by a perfect feature_overlap score of 1.0 that fully aligns with your required specifications. It also earned strong marks across the remaining categories, achieving a high rating score of 0.92 and a competitive price_fit score of 0.9181. This well-rounded combination of full feature matching, stellar user feedback, and budget compatibility makes it the clear winner.

▶ Phase 2: Resuming with approved=True...
  ✓ Node completed: request_confirmation
  ✓ Node completed: process_confirmation

[Stage 5-6] Checkout Result
  Order ID:          None
  Razorpay Order ID: 
  Status:            blocked
  Total:             ₹0.00

✗ FAIL: Expected razorpay_order_id starting with 'order_', got: ''

[Audit DB] Found 7 event(s) for request_id:
  • requirements_extracted (actor=agent, id=62)
  • catalogue_searched (actor=agent, id=63)
  • candidates_scored (actor=agent, id=64)
  • product_selected (actor=agent, id=65)
  • user_authorization_requested (actor=agent, id=66)
  • user_authorization_received (actor=agent, id=67)
  • policy_checked (actor=system, id=68)

✓ user_authorization_requested audit event found
✓ user_authorization_received audit event found

======================================================================
Agent checkout flow test complete.
```
