# Agentic Commerce Growth Engine

An AI-powered e-commerce platform where a LangGraph agent autonomously handles the full shopping workflow — understanding natural-language product queries, searching and scoring a catalogue, explaining its recommendation, obtaining explicit human approval, enforcing deterministic spending policies, processing Razorpay payments, and generating data-driven growth insights — all with a complete audit trail and automated failure alerting via n8n.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Next.js Frontend (:3000)                         │
│  Chat UI · Policy Controls · Audit Trail · Growth Dashboard                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │  REST (JSON)
┌────────────────────────────────▼────────────────────────────────────────────┐
│                        Django + DRF Backend (:8000)                         │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     LangGraph Agent Pipeline                        │   │
│  │                                                                     │   │
│  │  extract_requirements ──► search_catalogue ──► score_and_rank       │   │
│  │          │                                          │                │   │
│  │          ▼                                          ▼                │   │
│  │  explain_selection ──► request_confirmation ──► process_confirmation │   │
│  │                           (interrupt)               │                │   │
│  │                        Human approves               │                │   │
│  │                                                     ▼                │   │
│  │                                              Policy Engine           │   │
│  │                                           (ALLOW / BLOCK /           │   │
│  │                                            NEEDS_APPROVAL)           │   │
│  │                                                     │                │   │
│  │                                                     ▼                │   │
│  │                                            Razorpay Checkout         │   │
│  │                                          (+ timeout recovery)        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐    │
│  │  Catalogue   │  │  Audit Service  │  │  Growth Analytics (SQL +    │    │
│  │  (Products)  │  │  (every event)  │  │  Gemini insights)           │    │
│  └─────────────┘  └────────┬────────┘  └──────────────────────────────┘    │
│                             │                                               │
└─────────────────────────────┼───────────────────────────────────────────────┘
                              │ webhook (failure/block events)
                    ┌─────────▼──────────┐
                    │   n8n (:5678)       │
                    │  Failure Alerts     │
                    └────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  PostgreSQL (:5433) │
                    │  • Django models    │
                    │  • LangGraph state  │
                    └────────────────────┘
```

### Key Components

| Layer | Tech | Role |
|---|---|---|
| **Agent** | LangGraph + Gemini | 6-node pipeline with human-in-the-loop interrupt/resume, PostgresSaver checkpointer |
| **Scoring** | Deterministic Python | Weighted composite score (price fit × rating × feature overlap) — zero LLM in scoring |
| **Policy Engine** | Deterministic Python | Rule-based spending limits, category blocks, approval thresholds — zero LLM |
| **Payments** | Razorpay Python SDK | Order creation, timeout detection, idempotent retry/recovery |
| **Audit** | Django ORM + n8n | Every agent action recorded; failure/block events trigger n8n webhooks |
| **Growth** | Raw SQL + Gemini | Frequently-bought-together pairs, underperforming categories → LLM-generated insights |
| **Frontend** | Next.js | Single-page chat UI with live policy controls and inline audit trail |

---

## Running Locally

### Prerequisites

- Docker & Docker Compose
- A [Razorpay test account](https://dashboard.razorpay.com/app/keys) (free)
- A [Google Gemini API key](https://aistudio.google.com/apikey)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/Vedant7077/agentic-commerce-growth-engine.git
cd agentic-commerce-growth-engine

# 2. Create your env file
cp .env.example .env
# → Fill in RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, GEMINI_API_KEY, and POSTGRES_PASSWORD

# 3. Start all services
docker compose up --build

# 4. (First run) Seed the product catalogue and demo orders
docker compose exec backend python manage.py seed_products
docker compose exec backend python manage.py seed_demo_orders

# 5. Start the frontend (separate terminal)
cd frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| n8n Dashboard | http://localhost:5678 (admin / changeme123) |

---

## Running the Demo

1. **Open** http://localhost:3000
2. **Type a query** like _"Find me a mechanical keyboard under ₹3,000"_ or click one of the sample queries.
3. **Watch the agent pipeline** — it extracts requirements, searches the catalogue, scores/ranks products, and generates an explanation.
4. **Approve or reject** the recommendation when the agent asks for confirmation.
5. **Observe the policy engine** — try adjusting the spending limit slider in the UI to see orders get blocked when the price exceeds the policy threshold.
6. **Check the audit trail** — expand the audit section to see every event the agent recorded.
7. **Trigger a failure** — set `FORCE_TIMEOUT=true` in `.env` and restart the backend to see timeout recovery + n8n alerting in action.
8. **View growth insights** — hit the growth tab to see frequently-bought-together analysis and Gemini-generated recommendations.

### Timeout / Recovery Demo

```bash
# Simulate a Razorpay timeout
docker compose exec backend bash -c "export FORCE_TIMEOUT=true && python manage.py shell"
# Or set FORCE_TIMEOUT=true in .env and docker compose up again
```

The agent will detect the timeout, attempt idempotent recovery, and record the full retry sequence in the audit trail. n8n receives a webhook alert.

---

## What We Deliberately Did NOT Build (and Why)

In the interest of shipping a focused, production-quality demonstration rather than a sprawling prototype, we explicitly scoped out the following:

| Excluded | Rationale |
|---|---|
| **Multi-user authentication / sessions** | The demo runs as a single user (user_id=1). Auth adds OAuth/JWT complexity without demonstrating the core agent → policy → payment pipeline. |
| **Real payment capture** | We create Razorpay orders in TEST mode only. Actual money movement is a Razorpay dashboard toggle, not a code change — proving it in test mode is sufficient. |
| **Multi-product cart checkout** | The agent recommends and checks out a single top product. Multi-item carts are an additive feature that don't change the underlying architecture. |
| **Admin dashboard for policy rules** | Policy rules are managed via Django Admin and seed scripts. A custom admin UI is polish, not architecture. |
| **Webhook-driven payment status updates** | We verify payment status synchronously. Webhook listeners are important for production but are a Razorpay infra concern, not an agent-architecture concern. |
| **Horizontal scaling / Celery workers** | The agent pipeline runs synchronously in the request cycle. For a buildathon demo, this is fine; in production you'd move the LangGraph execution to Celery. |
| **Internationalization / multi-currency** | All prices are in INR (paise). Multi-currency is a Razorpay config, not an architectural decision. |
| **Vector search / embeddings for catalogue** | We use deterministic keyword + feature matching. Vector search is a valid enhancement but would obscure the scoring pipeline's transparency. |

These are all **additive** features that layer on top of the architecture we built. Nothing in our design prevents adding them — we just chose to ship depth over breadth.

---

## Tech Stack

| | |
|---|---|
| **Backend** | Python 3.11, Django 6.1, Django REST Framework |
| **Agent** | LangGraph, LangChain, Google Gemini |
| **Payments** | Razorpay Python SDK (TEST mode) |
| **Database** | PostgreSQL 16 |
| **Alerting** | n8n (self-hosted) |
| **Frontend** | Next.js (React) |
| **Infra** | Docker Compose, Gunicorn, multi-stage Docker build |

---

## Project Structure

```
├── backend/
│   ├── agent/           # LangGraph pipeline, tools, scoring
│   ├── audit/           # Audit event model, service, n8n webhook
│   ├── accounts/        # User model, spending limit API
│   ├── catalogue/       # Product model, seed command
│   ├── config/          # Django settings, URLs, WSGI
│   ├── growth/          # SQL analytics + Gemini insight generation
│   ├── orders/          # Order/OrderItem models, views
│   ├── payments/        # Razorpay integration, timeout recovery
│   ├── policy/          # Deterministic policy engine
│   ├── Dockerfile       # Multi-stage production build
│   └── entrypoint.sh    # Migrate → collectstatic → gunicorn
├── frontend/
│   └── app/             # Next.js single-page chat UI
├── n8n_workflows/       # Failure alert workflow (importable JSON)
├── scripts/             # Razorpay test scripts
├── docs/                # Integration notes, demo logs
├── docker-compose.yml
├── schema.sql           # Full PostgreSQL schema reference
└── .env.example
```

---

## License

Built for the Razorpay Buildathon.