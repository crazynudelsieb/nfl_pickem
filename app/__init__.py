import os

from flask import Flask, jsonify, render_template, request
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import config

# Single source of truth for the released version, reported by /health. The
# release workflow stamps this from the git tag it is publishing and commits it
# alongside that tag, so a running instance always names a version that
# actually shipped.
__version__ = "1.2.40"

db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO()
cache = Cache()
migrate = Migrate()
csrf = CSRFProtect()


# Client IPs come from request.remote_addr, which ProxyFix (configured in
# create_app) rewrites from X-Forwarded-For for the trusted proxy hops only.
# Never read forwarding headers directly - they are client-spoofable.
#
# Counters live in this process. The app runs a single worker, so shared
# storage would add a dependency without changing behaviour; the only cost is
# that counters reset on restart, which is immaterial at these limits.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["10000 per day", "1000 per hour"],  # Liberal limits - Cloudflare/Traefik provide primary protection
)


def create_app(config_name=None):
    app = Flask(__name__)

    # Determine configuration: FLASK_CONFIG wins, otherwise FLASK_ENV=production
    # selects the production config (docker-compose only sets FLASK_ENV).
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG")
    if config_name is None:
        config_name = (
            "production"
            if os.environ.get("FLASK_ENV") == "production"
            else "default"
        )

    app.config.from_object(config[config_name]())

    # Configure logging before anything else, so the rest of startup reports
    # through it instead of bare prints.
    from app.utils.logging_config import setup_logging

    setup_logging(app)

    # Trust forwarding headers from the reverse proxy (Traefik/nginx) only.
    # PROXY_HOPS is the number of proxies in front of the app (0 disables).
    proxy_hops = int(os.environ.get("PROXY_HOPS", "1"))
    if proxy_hops > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops, x_host=proxy_hops
        )

    # Configure session settings for better multi-device support
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    # Don't force SECURE in development, let it work over HTTP
    app.config["SESSION_COOKIE_SECURE"] = (
        False
        if app.config.get("DEBUG")
        else app.config.get("FLASK_ENV") == "production"
    )
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours

    # CSRF configuration for better mobile compatibility
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # No time limit on CSRF tokens
    app.config["WTF_CSRF_SSL_STRICT"] = False  # Allow HTTP in development
    app.config["WTF_CSRF_CHECK_DEFAULT"] = True

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Configure WebSocket CORS based on environment
    allowed_origins = app.config.get("SOCKETIO_CORS_ORIGINS", "*")
    if allowed_origins == "*" and not app.config.get("DEBUG"):
        # In production, restrict CORS to configured domains
        allowed_origins = os.environ.get(
            "ALLOWED_ORIGINS", "https://yourdomain.com,https://www.yourdomain.com"
        ).split(",")

    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        # Ordinary OS threads with simple-websocket as the WebSocket transport.
        # No monkey patching, and no dependency on eventlet or gevent - both of
        # which are unmaintained and/or dropped by newer Gunicorn.
        async_mode="threading",
        logger=app.debug,
        engineio_logger=app.debug,
        ping_timeout=60,
        ping_interval=25,
        # No message_queue: emits stay in this process, which is where every
        # emitter (request handlers and the APScheduler job) already runs. A
        # queue would only matter with more than one worker - and that needs
        # sticky session routing at the proxy first, see the Dockerfile CMD.
    )
    cache.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Initialize rate limiter
    limiter.init_app(app)

    # Login manager configuration
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    # Import and register blueprints
    from app.routes.auth import bp as auth_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.routes.main import bp as main_bp

    app.register_blueprint(main_bp)

    from app.routes.groups import bp as groups_bp

    app.register_blueprint(groups_bp, url_prefix="/groups")

    from app.routes.api import bp as api_bp

    app.register_blueprint(api_bp, url_prefix="/api")

    # Contact / legal globals for the footer and legal pages (computed once per
    # request from config). Shared standard across the appchen apps.
    from app.contact import legal_globals

    @app.context_processor
    def inject_legal_globals():
        return legal_globals(app.config)

    # Register error handlers
    register_error_handlers(app)

    # Show configuration warnings
    show_config_warnings(app, config_name)

    # Create database tables. create_all only creates missing tables - the
    # schema guard adds columns introduced after a table already exists.
    with app.app_context():
        db.create_all()
        from app.utils.schema_guard import ensure_schema

        ensure_schema()

    # Initialize and start background scheduler
    if not app.config.get("TESTING", False):
        from app.services.scheduler_service import scheduler_service

        scheduler_service.init_app(app)

    # Register SocketIO handlers
    from app import socketio_handlers  # noqa: F401 - imported for side effects

    return app


def show_config_warnings(app, config_name):
    """Display configuration warnings and status"""
    import warnings

    # Report the config that was actually resolved. Reading FLASK_CONFIG here
    # used to print "default" while FLASK_ENV=production was really in effect.
    print(f"NFL Pick'em starting with '{config_name}' configuration")

    if config_name == "production" and app.config.get("DEBUG"):
        warnings.warn(
            "DEBUG mode is enabled in production!", UserWarning, stacklevel=2
        )

    if not os.environ.get("SECRET_KEY"):
        print(
            "WARNING: Using auto-generated SECRET_KEY (sessions will reset on restart)"
        )
        print("   Run: python3 generate_secrets.py")

    if not os.environ.get("WTF_CSRF_SECRET_KEY"):
        print("WARNING: Using auto-generated CSRF key")

    db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if "sqlite" in db_url:
        print("Using SQLite database (development mode)")
        if "memory" in db_url:
            print("   Database: In-memory (testing)")
        else:
            print("   Database: app.db file")
    elif "postgresql" in db_url:
        # Extract host and database name for display (hide password)
        try:
            import re

            match = re.search(r"postgresql.*?://.*?@([^:/]+):?(\d+)?/([^?]+)", db_url)
            if match:
                host, port, dbname = match.groups()
                port = port or "5432"
                print("Using PostgreSQL database")
                print(f"   Host: {host}:{port}")
                print(f"   Database: {dbname}")
            else:
                print("Using PostgreSQL database")
        except Exception:
            print("Using PostgreSQL database")
    else:
        print(
            f"Using database: {db_url.split('://')[0] if '://' in db_url else 'Unknown'}"
        )

    print("Configuration loaded successfully")


def register_error_handlers(app):
    """Register global error handlers"""

    # Add middleware to catch SocketIO disconnection errors
    @app.before_request
    def handle_socketio_errors():
        pass  # We'll catch errors in after_request

    @app.after_request
    def after_request(response):
        # Add security headers to all responses
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Add Strict-Transport-Security in production
        if not app.config.get("DEBUG"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.socket.io https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
            "img-src 'self' data: https://api.dicebear.com https://a.espncdn.com https://http.cat",
            "connect-src 'self' wss: ws: https://site.api.espn.com",
            "font-src 'self' https://cdnjs.cloudflare.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        return response

    @app.errorhandler(KeyError)
    def handle_key_error(error):
        # Suppress SocketIO session disconnection errors
        if "Session is disconnected" in str(error):
            return jsonify({"error": "Session disconnected"}), 200
        # Re-raise other KeyErrors
        raise error

    # CSRF error handler
    from flask import flash, redirect
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        app.logger.warning(
            f"CSRF Error: {error.description} - Path: {request.path} - User-Agent: {request.user_agent}"
        )
        flash("Security token expired or invalid. Please try again.", "error")
        return redirect(request.url)

    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Access forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(400)
    def bad_request_error(error):
        app.logger.warning(
            f"400 Bad Request: {str(error)} - Path: {request.path} - Method: {request.method}"
        )
        if request.path.startswith("/api/"):
            return jsonify({"error": "Bad request"}), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(429)
    def too_many_requests_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Too many requests"}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(503)
    def service_unavailable_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Service unavailable"}), 503
        return render_template("errors/503.html"), 503


from app import models  # noqa: F401, E402 - imported for model registration
