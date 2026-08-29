-- =============================================================================
-- Agentic Commerce Growth Engine — PostgreSQL Schema
-- =============================================================================
-- Conventions:
--   • UUID primary keys — safe for distributed ID generation and opaque in URLs.
--   • All monetary values stored as INTEGER cents (paise) to avoid float rounding.
--   • created_at / updated_at on every mutable table; updated_at auto-bumped
--     by a shared trigger.
--   • JSONB columns where the agent needs to persist open-ended structured data.
-- =============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";          -- gen_random_uuid()

-- ── Helper: auto-update updated_at ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ═════════════════════════════════════════════════════════════════════════════
-- 1. PRODUCTS — merchant catalogue
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE products (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT        NOT NULL,
  description   TEXT,                          -- natural-language blurb the AI agent searches against
  category      TEXT,                          -- free-form; used by Growth Agent for cross-sell grouping
  price_paise   INTEGER     NOT NULL CHECK (price_paise >= 0),  -- price in paise (₹1 = 100 paise)
  currency      TEXT        NOT NULL DEFAULT 'INR',
  image_url     TEXT,
  metadata      JSONB       NOT NULL DEFAULT '{}',  -- extensible attrs (colour, size, brand …)
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  stock_qty     INTEGER     NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Full-text search on name + description for the AI catalogue search step
CREATE INDEX idx_products_search
  ON products USING GIN (to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,'')));
CREATE INDEX idx_products_category    ON products (category);
CREATE INDEX idx_products_is_active   ON products (is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_products_updated_at
  BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 2. USERS — buyers (extendable to merchants with a role column)
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT        UNIQUE NOT NULL,
  name          TEXT        NOT NULL,
  role          TEXT        NOT NULL DEFAULT 'buyer' CHECK (role IN ('buyer','merchant','admin')),
  -- spending_limit is the per-order hard cap evaluated by the policy engine
  spending_limit_paise  INTEGER   NOT NULL DEFAULT 1000000,  -- ₹10 000 default
  metadata      JSONB       NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_role  ON users (role);

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 3. CARTS — one active cart per user at a time
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE carts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status        TEXT        NOT NULL DEFAULT 'active' CHECK (status IN ('active','checked_out','abandoned')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enforce at most one active cart per user (partial unique index)
CREATE UNIQUE INDEX idx_carts_one_active_per_user
  ON carts (user_id) WHERE status = 'active';

CREATE TRIGGER trg_carts_updated_at
  BEFORE UPDATE ON carts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 4. CART_ITEMS
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE cart_items (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cart_id       UUID        NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
  product_id    UUID        NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  quantity      INTEGER     NOT NULL DEFAULT 1 CHECK (quantity > 0),
  -- Snapshot price at the moment the item was added; protects against catalogue price changes
  unit_price_paise INTEGER  NOT NULL CHECK (unit_price_paise >= 0),
  -- Agent recommendation reasoning stored per-item so the buyer sees *why* each item was suggested
  ai_reasoning  TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prevent duplicate product rows in the same cart; upsert quantity instead
CREATE UNIQUE INDEX idx_cart_items_cart_product ON cart_items (cart_id, product_id);

CREATE TRIGGER trg_cart_items_updated_at
  BEFORE UPDATE ON cart_items
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 5. ORDERS — created after policy engine approval
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  cart_id         UUID        REFERENCES carts(id) ON DELETE SET NULL,  -- link back to origin cart
  status          TEXT        NOT NULL DEFAULT 'pending_payment'
                    CHECK (status IN (
                      'pending_payment',   -- awaiting Razorpay checkout
                      'paid',              -- payment captured
                      'failed',            -- payment failed / policy rejected
                      'refunded',
                      'cancelled'
                    )),
  total_paise     INTEGER     NOT NULL CHECK (total_paise >= 0),
  currency        TEXT        NOT NULL DEFAULT 'INR',
  -- policy_verdict captures the deterministic engine's pass/fail + rule id
  policy_verdict  JSONB       NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id   ON orders (user_id);
CREATE INDEX idx_orders_status    ON orders (status);
CREATE INDEX idx_orders_created   ON orders (created_at DESC);

CREATE TRIGGER trg_orders_updated_at
  BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 6. ORDER_ITEMS — immutable snapshot of what was purchased
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE order_items (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id          UUID    NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id        UUID    NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  quantity          INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_paise  INTEGER NOT NULL CHECK (unit_price_paise >= 0),
  -- Redundant but useful: avoids a multiply on every read
  line_total_paise  INTEGER NOT NULL GENERATED ALWAYS AS (quantity * unit_price_paise) STORED,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
  -- No updated_at: order items are append-only
);

CREATE INDEX idx_order_items_order_id ON order_items (order_id);

-- ═════════════════════════════════════════════════════════════════════════════
-- 7. PAYMENTS — mirrors Razorpay payment objects
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE payments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id            UUID    NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
  -- Razorpay identifiers (TEST mode); nullable until the checkout session is created
  razorpay_order_id   TEXT,                      -- e.g. order_XXXXXXXXX
  razorpay_payment_id TEXT,                      -- e.g. pay_XXXXXXXXX
  razorpay_signature  TEXT,                      -- for server-side verification
  amount_paise        INTEGER NOT NULL CHECK (amount_paise >= 0),
  currency            TEXT    NOT NULL DEFAULT 'INR',
  status              TEXT    NOT NULL DEFAULT 'created'
                        CHECK (status IN ('created','authorized','captured','failed','refunded')),
  -- Raw webhook / API response kept for debugging & audit
  gateway_response    JSONB   NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_payments_rp_order   ON payments (razorpay_order_id)   WHERE razorpay_order_id   IS NOT NULL;
CREATE UNIQUE INDEX idx_payments_rp_payment ON payments (razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL;
CREATE INDEX idx_payments_order_id          ON payments (order_id);
CREATE INDEX idx_payments_status            ON payments (status);

CREATE TRIGGER trg_payments_updated_at
  BEFORE UPDATE ON payments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 8. AUDIT_EVENTS — append-only decision log for every agent action
-- ═════════════════════════════════════════════════════════════════════════════
-- Every meaningful step the AI agent takes (search, recommend, policy check,
-- payment initiation, growth suggestion) is recorded here. The JSONB payload
-- is schema-free so each event_type can carry its own structure without
-- requiring migrations.
CREATE TABLE audit_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID        REFERENCES users(id) ON DELETE SET NULL,
  session_id    UUID,                              -- groups events in a single agent conversation
  event_type    TEXT        NOT NULL,               -- e.g. 'search', 'recommend', 'policy_check',
                                                    --       'payment_initiated', 'upsell_suggested'
  entity_type   TEXT,                               -- e.g. 'order', 'cart', 'product'
  entity_id     UUID,                               -- FK kept loose; points to any entity
  payload       JSONB       NOT NULL DEFAULT '{}',  -- open-ended event data
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  -- No updated_at: audit rows are immutable
);

CREATE INDEX idx_audit_user_id      ON audit_events (user_id);
CREATE INDEX idx_audit_session      ON audit_events (session_id);
CREATE INDEX idx_audit_event_type   ON audit_events (event_type);
CREATE INDEX idx_audit_created      ON audit_events (created_at DESC);
-- GIN index on payload lets you query inside the JSONB (e.g. payload->>'rule_id')
CREATE INDEX idx_audit_payload      ON audit_events USING GIN (payload jsonb_path_ops);

-- ═════════════════════════════════════════════════════════════════════════════
-- 9. POLICY_RULES — deterministic guardrails evaluated before payment
-- ═════════════════════════════════════════════════════════════════════════════
-- The policy engine iterates active rules in priority order and short-circuits
-- on the first DENY.  Rules are evaluated in application code, not in SQL, so
-- the `condition` JSONB is an AST the engine interprets (keeps logic auditable).
--
-- Example condition:
--   { "field": "order.total_paise", "op": ">", "value": 5000000 }
--   → deny orders over ₹50 000
CREATE TABLE policy_rules (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT        NOT NULL,
  description   TEXT,
  -- Condition AST evaluated by the policy engine (see example above)
  condition     JSONB       NOT NULL,
  -- What happens when the condition matches
  action        TEXT        NOT NULL DEFAULT 'deny' CHECK (action IN ('deny','flag','allow')),
  priority      INTEGER     NOT NULL DEFAULT 100,  -- lower = evaluated first
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_rules_active ON policy_rules (priority) WHERE is_active = TRUE;

CREATE TRIGGER trg_policy_rules_updated_at
  BEFORE UPDATE ON policy_rules
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ═════════════════════════════════════════════════════════════════════════════
-- 10. GROWTH_INSIGHTS — upsell / cross-sell suggestions from the Growth Agent
-- ═════════════════════════════════════════════════════════════════════════════
CREATE TABLE growth_insights (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  order_id          UUID    REFERENCES orders(id) ON DELETE SET NULL,
  insight_type      TEXT    NOT NULL CHECK (insight_type IN ('upsell','cross_sell','bundle','reorder')),
  -- The products the Growth Agent is recommending
  recommended_product_ids UUID[] NOT NULL DEFAULT '{}',
  reasoning         TEXT,                          -- human-readable explanation from the LLM
  confidence_score  NUMERIC(4,3) CHECK (confidence_score BETWEEN 0 AND 1),
  status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','shown','accepted','dismissed')),
  metadata          JSONB   NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_growth_user_id   ON growth_insights (user_id);
CREATE INDEX idx_growth_order_id  ON growth_insights (order_id);
CREATE INDEX idx_growth_status    ON growth_insights (status);
-- GIN index on the UUID array so you can query "which insights recommend product X?"
CREATE INDEX idx_growth_products  ON growth_insights USING GIN (recommended_product_ids);

CREATE TRIGGER trg_growth_insights_updated_at
  BEFORE UPDATE ON growth_insights
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
