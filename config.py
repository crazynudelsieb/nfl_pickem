import os
import secrets
import warnings

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    # Generate secure keys if not provided (with warnings)
    _secret_key = os.environ.get("SECRET_KEY")
    _csrf_key = os.environ.get("WTF_CSRF_SECRET_KEY")

    # Use provided keys or generate secure defaults
    if not _secret_key:
        _secret_key = secrets.token_urlsafe(32)
        warnings.warn(
            "🔐 SECRET_KEY not set! Using auto-generated key. "
            "This will cause sessions to reset on app restart. "
            "Run 'python3 generate_secrets.py' to generate secure keys.",
            UserWarning,
        )

    if not _csrf_key:
        _csrf_key = secrets.token_urlsafe(32)
        warnings.warn(
            "🔐 WTF_CSRF_SECRET_KEY not set! Using auto-generated key. "
            "Run 'python3 generate_secrets.py' to generate secure keys.",
            UserWarning,
        )

    SECRET_KEY = _secret_key
    WTF_CSRF_SECRET_KEY = _csrf_key

    # Database configuration - built from environment at initialization
    def __init__(self):
        """Initialize configuration with dynamic database URI"""
        self.SQLALCHEMY_DATABASE_URI = self._build_database_uri()

    def _build_database_uri(self):
        """Build database URI from environment variables"""
        database_url = os.environ.get("DATABASE_URL")

        if database_url:
            return database_url

        db_type = os.environ.get("DB_TYPE", "sqlite")

        if db_type.lower() == "postgresql":
            db_host = os.environ.get("DB_HOST") or "localhost"
            db_port = os.environ.get("DB_PORT") or "5432"
            db_name = os.environ.get("DB_NAME") or "nfl_pickem_db"
            db_user = os.environ.get("DB_USER") or "nfl_user"
            db_password = os.environ.get("DB_PASSWORD") or "nfl_password"

            return f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            # Default to SQLite for development
            return "sqlite:///" + os.path.join(basedir, "app.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email configuration
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")  # Flask-Mail setting

    # Custom email settings for our email service
    FROM_EMAIL = os.environ.get("FROM_EMAIL") or os.environ.get("MAIL_USERNAME")
    FROM_NAME = os.environ.get("FROM_NAME", "NFL Pick'em")

    # API configuration
    NFL_API_BASE_URL = (
        os.environ.get("NFL_API_BASE_URL")
        or "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    )

    # Application settings
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE") or 20)
    SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT") or 3600)
    INVITE_TOKEN_EXPIRY = int(os.environ.get("INVITE_TOKEN_EXPIRY") or 168)  # hours
    TIMEZONE = os.environ.get("TIMEZONE", "UTC")  # Default to UTC if not specified

    # Caching configuration
    CACHE_TYPE = os.environ.get("CACHE_TYPE", "RedisCache")
    CACHE_DEFAULT_TIMEOUT = int(
        os.environ.get("CACHE_DEFAULT_TIMEOUT", 300)
    )  # 5 minutes
    CACHE_REDIS_URL = os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379/0")
    CACHE_KEY_PREFIX = "nfl_pickem:"

    # Scheduler configuration
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "True").lower() == "true"

    # Logging configuration
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_TO_CONSOLE = os.environ.get("LOG_TO_CONSOLE", "True").lower() == "true"
    LOG_TO_FILE = os.environ.get("LOG_TO_FILE", "True").lower() == "true"
    LOG_DIR = os.environ.get("LOG_DIR", "logs")
    SLOW_QUERY_THRESHOLD = float(os.environ.get("SLOW_QUERY_THRESHOLD", "1.0"))

    # Display name used in page titles, the footer, and the legal pages
    APP_NAME = os.environ.get("APP_NAME", "NFL Pick'em")

    # --- Contact / social (optional; only the ones set are shown) ---------
    # Standardized across the appchen apps. Each channel is opt-in: leave a
    # value blank and it simply never appears in the footer or on the legal
    # pages. The email is rendered obfuscated (no literal "@" or mailto: in
    # the HTML source) to resist naive address harvesters - the client
    # reassembles it (see the js-mail handler in base.html).
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "").strip()
    CONTACT_MASTODON = os.environ.get("CONTACT_MASTODON", "").strip()
    CONTACT_GITHUB = os.environ.get("CONTACT_GITHUB", "").strip()
    CONTACT_KOFI = os.environ.get("CONTACT_KOFI", "").strip()
    CONTACT_BUYMEACOFFEE = os.environ.get("CONTACT_BUYMEACOFFEE", "").strip()

    # --- Legal / Impressum (optional) -------------------------------------
    # Site notice required by EU law (e.g. Germany's TMG, Austria's ECG).
    # The /impressum page is served (and linked in the footer) only once
    # IMPRINT_NAME is set; the rest are optional detail lines. Use "\n"
    # inside address / extra to force line breaks.
    IMPRINT_NAME = os.environ.get("IMPRINT_NAME", "").strip()
    IMPRINT_ADDRESS = os.environ.get("IMPRINT_ADDRESS", "").strip().replace("\\n", "\n")
    IMPRINT_EMAIL = os.environ.get("IMPRINT_EMAIL", "").strip() or CONTACT_EMAIL
    IMPRINT_PHONE = os.environ.get("IMPRINT_PHONE", "").strip()
    IMPRINT_VAT = os.environ.get("IMPRINT_VAT", "").strip()
    IMPRINT_EXTRA = os.environ.get("IMPRINT_EXTRA", "").strip().replace("\\n", "\n")
    IMPRINT_ENABLED = bool(IMPRINT_NAME)

    # Optional data-residency note shown on /privacy. Blank hides the line.
    DATA_LOCATION = os.environ.get("DATA_LOCATION", "").strip()

    # Environment detection
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"
    TESTING = False


class DevelopmentConfig(Config):
    """Development configuration with helpful defaults"""

    DEBUG = True
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "False").lower() == "true"

    def __init__(self):
        super().__init__()
        # Fallback to SimpleCache if Redis isn't available in development
        try:
            import redis

            redis_client = redis.Redis.from_url(self.CACHE_REDIS_URL)
            redis_client.ping()
        except Exception:
            self.CACHE_TYPE = "SimpleCache"
            warnings.warn(
                "🔶 Redis not available, falling back to SimpleCache for development. "
                "Run 'docker-compose -f docker-compose.redis.yml up -d' to use Redis.",
                UserWarning,
            )


class ProductionConfig(Config):
    """Production configuration with security focus"""

    DEBUG = False

    # In production, require explicit environment variables
    def __init__(self):
        super().__init__()  # Call parent __init__ to build database URI

        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError(
                "SECRET_KEY must be set in production. An auto-generated key "
                "would invalidate all sessions and CSRF tokens on every "
                "restart. Run 'python generate_secrets.py' and add the keys "
                "to your .env file."
            )
        if not os.environ.get("WTF_CSRF_SECRET_KEY"):
            warnings.warn(
                "🚨 PRODUCTION WARNING: WTF_CSRF_SECRET_KEY not explicitly set!",
                UserWarning,
            )


class TestingConfig(Config):
    """Testing configuration"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Tests must not depend on a running Redis; cache in-process instead.
    CACHE_TYPE = "SimpleCache"

    def __init__(self):
        # Config.__init__ sets an instance attribute from the environment which
        # would override a class attribute - set it here so tests always run
        # against in-memory SQLite, never a real database.
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# Configuration mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
