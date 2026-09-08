"""Regression tests for the transport- and redirect-hardening fixes.

Each of these guards a setting that was previously wrong in a way no existing
test noticed: the login redirect accepted cross-origin targets, and the cookie
flags keyed off an environment variable the deployment never had to set.
"""

import pytest
from flask import Flask

import config as app_config
from app import uses_plain_http
from app.routes.auth.routes import is_safe_redirect_target


@pytest.mark.parametrize(
    "target",
    [
        "https:/evil.com",  # empty netloc, browser normalises to an origin
        r"/\evil.com",  # backslash authority, same normalisation
        "//evil.com",
        "http://evil.com",
        "javascript:alert(1)",
        r"\/evil.com",
        "",
        None,
    ],
)
def test_rejects_offsite_redirect_targets(target):
    assert is_safe_redirect_target(target) is False


@pytest.mark.parametrize(
    "target",
    ["/", "/dashboard", "/groups/1/picks?week=3", "/about#rules"],
)
def test_accepts_local_paths(target):
    assert is_safe_redirect_target(target) is True


def _config_of(config_class):
    """The Flask config a config class produces, without booting the app.

    create_app("production") would start the scheduler and open the real
    database from .env, so the cookie derivation is checked here instead.
    """
    app = Flask(__name__)
    app.config.from_object(config_class())
    return app.config


def test_production_serves_over_tls(monkeypatch):
    """FLASK_CONFIG alone must be enough - FLASK_ENV used to be required."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("WTF_CSRF_SECRET_KEY", "test-csrf-key")
    monkeypatch.delenv("FLASK_ENV", raising=False)

    assert uses_plain_http(_config_of(app_config.ProductionConfig)) is False


def test_development_and_testing_stay_on_plain_http():
    assert uses_plain_http(_config_of(app_config.DevelopmentConfig)) is True
    assert uses_plain_http(_config_of(app_config.TestingConfig)) is True


def test_testing_app_gets_the_plain_http_cookie_flags(app):
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["WTF_CSRF_SSL_STRICT"] is False
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"


def test_security_headers_present(app):
    with app.test_client() as client:
        headers = client.get("/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "object-src 'none'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
