# BoostX Architecture & Design Decisions

This document logs all key architectural, security, and design decisions made during the development of BoostX to resolve specification ambiguities safely and maintain system integrity.

---

## Decisions Log

### DEC-001: Flask + SQLAlchemy + Redis + RQ Architecture
- **Context**: The backend required a resilient background worker system for service sync, payment verification retries, and order status polling.
- **Decision**: Implemented Flask 3, SQLAlchemy 2 (with Postgres transaction locks), Redis, and RQ for background workers/scheduler.
- **Rationale**: Standardized stack matching project requirements, ensuring ACID compliance for ledger transactions.

### DEC-002: Browser Session-Based Guest Claiming
- **Context**: Spec §16 and prompt audit identified a flaw in contact-based claiming where unverified email/phone could allow account takeover of guest funds.
- **Decision**: Guest funds and orders migrate to a newly registered or logged-in account based strictly on the possession of the signed HttpOnly guest session cookie (`CLAIM_BY_CONTACT_ENABLED=false` by default).
- **Rationale**: Unverified phone/email must never unlock money. Cookie possession proves the current user actually placed the guest orders.

### DEC-003: Provider Call Retry Hardening
- **Context**: Starter `ProviderAdapter` retried all requests including `add`. Transient network timeouts during `add`, `cancel`, or `refill` could result in duplicate orders or double actions at the SMM provider.
- **Decision**: `add`, `cancel`, and `refill` calls are NEVER retried automatically. Only idempotent read operations (`services`, `status`, `balance`) retry on network timeouts.
- **Rationale**: Prevents duplicate provider orders and balance loss on transient timeouts. Ambiguous errors set `needs_attention=True` on orders for manual admin inspection.

### DEC-004: Phone Number Normalization to E.164 Standard
- **Context**: Ghanaian phone numbers can be entered as `0244123456`, `+233244123456`, or `233244123456`.
- **Decision**: All phone numbers are normalized to E.164 standard (`+233XXXXXXXXX`) across user registration, login, payment processing, and guest checkout.
- **Rationale**: Guarantees consistent lookup and matching across databases and SMS/mobile money gateways.

### DEC-005: Ledger-Calculated Balances with Row-Level Locking
- **Context**: Balance drift and race conditions during simultaneous order placement.
- **Decision**: User balance is calculated dynamically from ledger entries (`posted_credits - posted_debits - reserved_debits`) within a Postgres transaction that acquires a `SELECT FOR UPDATE` lock on the owner record.
- **Rationale**: Eliminates race conditions and prevents negative balances under concurrent access.

### DEC-006: Server-Side Single-Source Pricing
- **Context**: Clients might attempt to send price estimates in order creation requests.
- **Decision**: All order quotes and transactions calculate service price on the server: `customer_price_ghs = ceil_or_halfup((provider_cost_usd / 1000 * qty * usd_to_ghs_rate) + flat_markup_ghs)`. Client-supplied prices are completely ignored.
- **Rationale**: Protects against tampering and price drift.

### DEC-007: Flask-Limiter Endpoint Scoping & Tiered Limits
- **Context**: Brute-force protection for auth, payment submission, order creation, and public order tracking.
- **Decision**: Implemented `Flask-Limiter` with memory/Redis backing:
  - Auth (`/api/auth/login`, `/api/auth/register`): 5 requests / min
  - Payment Creation & Screenshot Upload (`/api/payments`): 10 requests / min
  - Order Creation (`/api/orders` POST): 20 requests / min
  - Public Order Tracking (`/api/orders/:public_id` GET): 60 requests / min
- **Rationale**: Tight restrictions on authentication endpoints prevent brute-force attacks on the admin login door, while looser tracking limits preserve public guest order lookup functionality.

### DEC-008: Non-Testing Environment PostgreSQL Strict Enforcement
- **Context**: SQLite does not support row-level locking (`SELECT FOR UPDATE`), causing SQLAlchemy to silently drop lock guarantees under concurrent access.
- **Decision**: `create_app()` raises `RuntimeError` on boot in non-testing environments (`TESTING=False`) if `DATABASE_URL` is not a `postgresql://` connection string.
- **Rationale**: Guarantees that production deployments never run on SQLite where money-safety row locks would no-op.

### DEC-009: Strict Repository Top-Level Layout (`frontend/` & `backend/` Only)
- **Context**: Spec and prompt required clear separation of root-level frontend and backend concerns. Loose directories (`docs/`, `scripts/`, `.figma/`, `.figaro/`) sat at top level.
- **Decision**: Consolidated root directory using `git mv` so the top level contains strictly `frontend/` and `backend/` folders. Project documentation lives in `backend/docs/`, scripts in `backend/scripts/`, and Figma design assets in `frontend/.figma/`. Root level retains only root orchestration configs (`README.md`, `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.env.example`, `.gitignore`).
- **Rationale**: Organizes mono-repo clearly, preserves git history, and aligns build scripts and Docker container paths.

### DEC-010: Gemini OpenAI API Integration & Free-Tier Rate-Limit Handling
- **Context**: AI payment verification relies on Google Gemini's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) using `gemini-2.0-flash-lite`. Gemini free tier enforces 15 requests per minute (RPM) and 1,500 requests per day (RPD).
- **Decision**: Set default `AI_API_URL` to `https://generativelanguage.googleapis.com/v1beta/openai/` and `AI_MODEL` to `gemini-2.0-flash-lite`. If API quota/rate limits (HTTP 429) or network errors occur, `PaymentAI.extract()` returns `integrity_flags=["AI_EXTRACTION_FAILED"]` and `confidence=0.0`. The decision engine routes failed extractions to `PaymentStatus.REVIEW_REQUIRED` for human admin review instead of rejecting payments.
- **Rationale**: Protects customers from false payment rejections during AI rate limit exhaustion or third-party outages while keeping verification zero-cost on Gemini free tier.

### DEC-00X: Account required; guest checkout removed (supersedes DEC-002)
- **Context**: Guest sessions (and claiming guest money on sign-up) allowed using the system without an account.
- **Decision**: An account is mandatory. All `/api/*` endpoints except login/register/me/logout require a signed-in customer (deny-by-default `before_request` guard); `/api/admin/*` requires the admin. Guest sessions, the guest cookie and claim-on-signup were removed. The administrator authenticates only with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` environment variables (no admin sign-up, no stored admin password).
- **Note**: Legacy `session_id` columns / `guest_sessions` table may still exist in older databases; the application no longer reads or writes them.

### DEC-011: Unconditional Password Change Session Revocation with Static Frontend Guidance
- **Context**: The reference Settings panel displays a "Revoke old sessions" option during password change. The backend (`POST /api/auth/change-password`) unconditionally increments `user.session_version += 1`, revoking all other active sessions while re-syncing `session["session_version"]` for the current session.
- **Decision**: Maintained unconditional session revocation on password change without adding a deceptive "optional" checkbox to the UI. Displayed a clear, static informational note in the Settings UI: `"Changing your password will sign you out of all other devices."`
- **Rationale**: Keeps session security robust and guarantees user feedback accurately reflects server behavior without adding unnecessary backend complexity or UI misrepresentation.
