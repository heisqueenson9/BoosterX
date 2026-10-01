import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from backend.app.config import Config
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

    # In production / non-testing environments, enforce Postgres requirement for row locking
    if not app.config.get("TESTING"):
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_uri.startswith("postgresql://"):
            raise RuntimeError(
                "DATABASE_URL must be a PostgreSQL connection string (postgresql://) in non-testing environments. "
                "SQLite does not support row-level locking (SELECT FOR UPDATE)."
            )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    from backend.app.middleware import limiter
    limiter.init_app(app)
    CORS(app, supports_credentials=True)

    # Enforce CSRF on every state-changing request (the guest-session bootstrap
    # endpoint is exempted inside validate_csrf itself).
    from backend.app.middleware import validate_csrf
    app.before_request(validate_csrf)

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
