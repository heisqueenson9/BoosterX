import os
import sys
from datetime import timedelta
from decimal import Decimal

INSECURE_DEFAULT_SECRET_KEY = "boostx-secret-key-change-in-production"

class Config:
    TESTING = os.getenv("TESTING", "false").lower() in ("true", "1") or "pytest" in sys.modules
    SECRET_KEY = os.getenv("SECRET_KEY", INSECURE_DEFAULT_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'boostx.db')}"
    )
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = "memory://" if (TESTING or "pytest" in sys.modules or "REDIS_URL" not in os.environ) else os.getenv("REDIS_URL")
    RATELIMIT_ENABLED = not TESTING
    
    # Provider Settings (BaloonBoost API Integration)
    BALLOONBOOST_API_URL = os.getenv("BALLOONBOOST_API_URL", os.getenv("PROVIDER_API_URL", "https://baloonboost.com/api/v2"))
    BALLOONBOOST_API_KEY = os.getenv("BALLOONBOOST_API_KEY", os.getenv("SMM_AFRICA_API_KEY", os.getenv("PROVIDER_API_KEY", "mock-provider-key")))
    
    SMM_AFRICA_API_URL = BALLOONBOOST_API_URL
    SMM_AFRICA_API_KEY = BALLOONBOOST_API_KEY
    SMM_AFRICA_TEST_MODE = os.getenv("SMM_AFRICA_TEST_MODE", "false").lower() in ("true", "1")
    
    PROVIDER_MODE = os.getenv("PROVIDER_MODE", "fake")  # 'live' or 'fake'
    PROVIDER_API_URL = BALLOONBOOST_API_URL
    PROVIDER_API_KEY = BALLOONBOOST_API_KEY
    
    # AI Vision Verification Settings (Gemini OpenAI-compatible API)
    AI_API_URL = os.getenv("AI_API_URL", os.getenv("OPENAI_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))
    AI_API_KEY = os.getenv("AI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    AI_MODEL = os.getenv("AI_MODEL", os.getenv("OPENAI_VISION_MODEL", "gemini-2.0-flash-lite"))
    
    # FX Rate Settings
    FX_API_URL = os.getenv("FX_API_URL", "")
    DEFAULT_USD_TO_GHS = Decimal(os.getenv("USD_TO_GHS_RATE", os.getenv("DEFAULT_USD_TO_GHS", "10.70")))
    DEFAULT_FLAT_MARKUP_GHS = Decimal(os.getenv("FLAT_MARKUP_GHS", os.getenv("DEFAULT_FLAT_MARKUP_GHS", "5.00")))
    
    # Session settings. Authentication is a signed, HttpOnly cookie session.
    SESSION_COOKIE_NAME = "boostx_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies by default in production (HTTPS); override with SESSION_COOKIE_SECURE.
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "true" if os.getenv("FLASK_ENV") == "production" else "false"
    ).lower() in ("true", "1")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_LIFETIME_HOURS", "168")))

    # Administrator credentials. The admin is authenticated ONLY against these
    # server-side environment variables (never stored in source or sent to the
    # frontend). If either is unset, admin login is disabled.
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

    # Browser cross-origin access is disabled by default (the SPA is served by
    # this app). Set CORS_ORIGINS="https://a.example,https://b.example" to enable.
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    
    # Storage Settings
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
