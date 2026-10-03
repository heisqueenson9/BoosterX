import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from backend.app.config import Config, INSECURE_DEFAULT_SECRET_KEY
from backend.app.db import db
from backend.app.cli import register_cli_commands

migrate = Migrate()

def create_app(config_class=Config):
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dist_path = os.path.join(repo_root, "frontend", "dist")
    if not os.path.exists(dist_path):
        dist_path = os.path.join(repo_root, "dist")

    app = Flask(
        __name__,
        static_folder=dist_path,
        static_url_path="/static"
    )
    app.config.from_object(config_class)

    # Sessions are signed with SECRET_KEY: refuse to run outside tests with the
    # well-known development default.
    if not app.config.get("TESTING") and app.config.get("SECRET_KEY") == INSECURE_DEFAULT_SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set to a private random value in non-testing environments.")

    # In production / non-testing environments, enforce Postgres requirement for row locking
    if not app.config.get("TESTING") and not os.getenv("ALLOW_SQLITE", "false").lower() in ("true", "1"):
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_uri.startswith("postgresql://"):
            raise RuntimeError(
                "DATABASE_URL must be a PostgreSQL connection string (postgresql://) in non-testing environments. "
                "SQLite does not support row-level locking (SELECT FOR UPDATE). Set ALLOW_SQLITE=true to bypass for local dev."
            )

    # Initialize extensions
    db.init_app(app)
    # Migrations live in backend/migrations, not ./migrations (Flask-Migrate default),
    # so `flask db upgrade` works from the repo root / Docker WORKDIR.
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(__file__), "..", "migrations"))
    from backend.app.middleware import limiter
    limiter.init_app(app)
    # The SPA is served by this app (same origin), so cross-origin browser
    # access is opt-in via CORS_ORIGINS.
    if app.config.get("CORS_ORIGINS"):
        CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    # Order matters: authenticate first (401), then enforce CSRF on signed-in
    # state-changing requests (login/register are exempt inside validate_csrf).
    from backend.app.middleware import require_authentication, validate_csrf, no_store_api_responses
    app.before_request(require_authentication)
    app.before_request(validate_csrf)
    app.after_request(no_store_api_responses)

    @app.errorhandler(429)
    def rate_limited(_exc):
        return jsonify({"error": "Too many attempts. Please wait a minute and try again."}), 429

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:
            app.logger.warning(f"db.create_all() auto-initialization note: {exc}")

    # Register CLI commands
    register_cli_commands(app)

    # Register blueprints (will be populated in subsequent milestones)
    from backend.app.auth.routes import auth_bp
    from backend.app.api.catalog import catalog_bp
    from backend.app.payments.routes import payments_bp
    from backend.app.api.orders import orders_bp
    from backend.app.admin.routes import admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "ok"}), 200

    # Serve built React SPA & hash routing fallback
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # Do not hijack API routes
        if path.startswith("api/"):
            return jsonify({"error": "Resource not found"}), 404

        if app.static_folder and os.path.exists(app.static_folder):
            if path and os.path.exists(os.path.join(app.static_folder, path)) and os.path.isfile(os.path.join(app.static_folder, path)):
                return send_from_directory(app.static_folder, path)
            return send_from_directory(app.static_folder, "index.html")
        return jsonify({"message": "BoostX API is running."}), 200

    return app
