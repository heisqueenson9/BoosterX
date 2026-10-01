# BoostX —  Social Media Panel 
BoostX is an account-based social media boosting panel built specifically for Ghana, supporting local Mobile Money payments in Ghana Cedi (GHS) only.

---

## Features

- **Account-based Access**: Customers sign up, sign in, fund their wallet, place orders, and track fulfillment under their own account. There is no guest access.
- **Mobile Money & AI Vision Verification**: Integrates Telecel Cash, MTN MoMo, and AirtelTigo Cash payments with OpenAI Vision verification for instant receipt verification.
- **Double-Entry Financial Ledger**: Single-transaction atomic balance locking (`posted`, `reserved`, `released`) preventing double-spend and negative balances under PostgreSQL row locks.
- **Defensive Provider Integration**: Wrapped SMM panel API integration (`boostcenter2.com/api/v2`) with zero-retry guarantees on state-changing actions (`add`, `cancel`, `refill`).
- **Comprehensive Admin Panel**: Full management dashboard for payment reviews, order fulfillment, catalog controls, exchange rates, audit logs, and system health.
- **Rate Limiting & Security Guards**: `Flask-Limiter` endpoint protection, generic login errors, 5-attempt lockout, and an admin-only guard on `/api/admin/*`.

---

## Project Structure

```
BoosterX/
├── backend/
│   ├── app/
│   │   ├── admin/          # Admin REST API & security guard
│   │   ├── ai/             # OpenAI Vision receipt extraction
│   │   ├── api/            # Catalog, order, and account endpoints
│   │   ├── auth/           # Sign-up/login, sessions, repository
│   │   ├── orders/         # 7-step order execution algorithm & refunds
│   │   ├── payments/       # Upload security & single-transaction decision engine
│   │   ├── pricing/        # Pricing engine (Decimal math, GHS conversion)
│   │   ├── providers/      # Defensive ProviderAdapter & FakeProvider
│   │   ├── services/       # Ledger balance calculator with row locking
│   │   └── workers/        # Background workers & scheduler
│   ├── migrations/         # Alembic database migrations
│   ├── tests/              # Pytest test suite (M1 to M6 + PostgreSQL concurrency tests)
│   ├── cli.py              # CLI seed command
│   ├── config.py           # System constants & operational limits
│   └── requirements.txt    # Python backend package dependencies
├── frontend/               # Frozen React 19 + Tailwind v4 frontend
│   ├── src/                # Typed REST API client, router, & screens
│   ├── package.json        # Frontend scripts & dependencies
│   └── vite.config.ts      # Vite config, outDir, & API proxy
├── backend/
│   ├── docs/               # Implementation plan, runbook, decisions & deviations
│   └── scripts/            # Provider smoke test CLI & secret scan script
├── Dockerfile              # Multi-stage production build (Node + Python + Gunicorn)
├── docker-compose.yml      # Container orchestration (Web, Worker, Postgres, Redis)
└── render.yaml             # Render deployment blueprint
```

---

## Quickstart & Local Setup

### 1. Requirements
- Python 3.12+
- Node.js 18+
- PostgreSQL 16+ (or SQLite for testing mode)

### 2. Environment Setup
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Backend Setup & Migrations
```bash
pip install -r backend/requirements.txt
flask --app backend.app:create_app db upgrade
flask --app backend.app:create_app seed
```

### Authentication
- An account is required to use BoostX: visitors can only see the **Sign in** and **Create account** pages. Every `/api/*` endpoint (other than login/register/me/logout) rejects unauthenticated requests with `401`, so protection does not depend on the frontend.
- **Customers** sign up with name, email and password, and are signed in automatically.
- **The administrator** signs in on the same login page using `ADMIN_EMAIL` and `ADMIN_PASSWORD` from the server environment. There is no admin sign-up and no admin password in the database; if either variable is unset, admin login is disabled. Set them as Render secret variables / in your gitignored `.env`.
- Sessions are signed, HttpOnly, SameSite=Lax cookies (Secure in production) that expire after `SESSION_LIFETIME_HOURS` (default 7 days). Signing out revokes the session on the server.

### 4. Frontend Build
```bash
cd frontend
npm ci
npm run build
cd ..
```

### 5. Run Application Server
```bash
python -m flask --app backend.app:create_app run --port 5000
```
Visit [http://localhost:5000/](http://localhost:5000/) in your browser.

---

## Testing & Verification

Run the full pytest suite (including PostgreSQL concurrency tests):
```bash
TESTING=true python -m pytest -v backend/tests
```

Run the provider smoke test CLI:
```bash
python backend/scripts/provider_smoke.py --mode fake
```

Run secret leak build-scan:
```bash
python backend/scripts/secret_scan.py
```

---

## Deployment

Deploy using Docker Compose with PostgreSQL & Redis:
```bash
docker-compose up --build -d
```

Or deploy to Render using `render.yaml`.
