# Razorpay Integration Notes — Day 2

Reference material from hands-on integration testing. Useful for Days 7 (recovery flows) and 9 (timeout-recovery demo narrative).

---

## Order → Payment → Signature Lifecycle

The three-step relationship proved end-to-end today:

1. **Server creates an Order** via `client.order.create()` — this is just a record, no money moves yet. Status: `created`.
2. **Checkout collects a Payment** against that order — status starts `created`, becomes `authorized`, then `captured` on success, or `failed` on failure.
3. **Razorpay signs the (order_id + payment_id) pair** — `HMAC-SHA256("{order_id}|{payment_id}", key_secret)`. You verify this signature server-side before trusting the payment.

```
  Server                   Browser                    Razorpay
    │                         │                           │
    │── order.create() ──────>│                           │
    │<── order_id ────────────│                           │
    │                         │── Checkout(order_id) ────>│
    │                         │<── payment modal ─────────│
    │                         │── card + OTP ────────────>│
    │                         │<── payment_id, signature ─│
    │<── verify_signature() ──│                           │
    │── fulfil order ────────>│                           │
```

---

## Fields That Actually Matter

From the real payment object — what to store vs. ignore:

| Field | Why It Matters |
|---|---|
| `status` | Only `captured` means money is secured. `authorized` means you still need to capture. |
| `captured` | Boolean — the definitive "did we get the money" flag. |
| `amount` | Always in **paise** (49900 = ₹499). Everywhere in the API, no exceptions. |
| `error_code` / `error_description` | `null` on success, populated on failure — **store both** when failed for audit trail. |
| `method` | `card`, `upi`, `netbanking`, etc. — useful for analytics. |
| `order_id` | Links payment back to the order. |
| `fee` / `tax` | Razorpay's processing cut — appears even on test payments. **Don't surface this to users as part of order total.** |

---

## Test Cards Reference

### Domestic (Working — Use These)

| Network | Card Number | Notes |
|---|---|---|
| Mastercard | `5267 3181 8797 5449` | Domestic, works with our account |
| RuPay | `6527 6589 0000 1005` | Domestic, works with our account |

### Failure Simulation

| Network | Card Number | Failure Reason |
|---|---|---|
| Mastercard | `5305 6200 0006 0000` | `payment_timed_out` — useful for Day 9 timeout-recovery demo |

> **Easiest failure path:** Use any working domestic card, then click **Failure** on the mock bank page instead of Success.

### International (DO NOT USE)

| Network | Card Number | Problem |
|---|---|---|
| Visa | `4111 1111 1111 1111` | Rejected as "international" — our account is domestic-only |

---

## Surprises Worth Remembering

1. **Account is domestic-only** — International test cards (`4111 1111…`) get rejected *before* Razorpay even simulates a response. That's an account-config error, not a payment error. This matters for live too — will need to enable international payments in dashboard if we ever need them.

2. **Mock bank page Success/Failure buttons are the real mechanism** — The card number mostly picks the network/issuer shown, not the outcome, except for dedicated error-simulation cards.

3. **`fee` and `tax` fields appear even on test payments** — Don't accidentally surface Razorpay's processing fee as part of the order total in the UI.

4. **OTP in test mode** — Any 4+ digit number works for success, <4 digits triggers failure. Not documented prominently.

5. **`amount` in checkout options is cosmetic** — The actual charged amount comes from the server-side order. If they don't match, Razorpay uses the server-side amount. Always trust the order, not the frontend.

6. **Signature check ≠ captured payment** — A valid signature proves authenticity, but the payment could still be in `authorized` state. Always check `payment['status'] == 'captured'` before fulfilling.

## Failure Testing (Verified ✓)

Both failure paths tested successfully on `order_TVVPnwgfYStTC7`:

### Method 1: Mock Bank Page → Failure Button
- Use a working domestic card (`5267 3181 8797 5449`), enter a valid 4+ digit OTP
- The mock bank page ("Welcome to Razorpay Software Private Ltd Bank") appears with **Success** and **Failure** buttons
- Clicking **Failure** → Razorpay returns: _"Payment could not be completed — Payment failed"_
- The `payment.failed` handler fires with `error.code` and `error.description`

### Method 2: Short OTP (< 4 digits)
- Use a working domestic card, enter a short OTP like `12` (less than 4 digits)
- Razorpay returns: _"Payment could not be completed — You've entered an incorrect OTP. Please enter an OTP of length between 4-10 digits."_
- This bypasses the mock bank page entirely — fails at the OTP validation step

### Key Takeaway for Days 7 & 9
- **Method 1** simulates a real bank decline — use this for timeout/recovery demos
- **Method 2** simulates an input validation failure — different error category
- Both populate `error_code` and `error_description` in the payment object — store these for audit

> **Note:** The mock bank page only appears after entering a valid OTP (4+ digits). If you enter a short OTP, it fails before reaching the bank simulation.

---

## Verification Commands

```bash
# Create a new order
python scripts/create_and_pay.py

# After checkout completes, verify
python scripts/verify_payment.py \
    --order_id order_XXXXXXXXXXXXXX \
    --payment_id pay_XXXXXXXXXXXXXX \
    --signature XXXXXXXXXXXXXXXX
```

---

*Last updated: Day 2 of buildathon — success + failure flows both verified*
