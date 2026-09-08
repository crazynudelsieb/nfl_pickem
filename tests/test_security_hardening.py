"""Regression tests for the transport- and redirect-hardening fixes.

Each of these guards a setting that was previously wrong in a way no existing
test noticed: the login redirect accepted cross-origin targets, and the cookie
flags keyed off an environment variable the deployment never had to set.
"""

import re
from pathlib import Path

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


# --------------------------------------------------------------------------
# CSP: script-src no longer carries 'unsafe-inline'.
#
# That only holds while every inline <script> in the templates has a nonce and
# no markup carries an on*= handler or a javascript: URL - a nonce cannot cover
# either of those. The template scan below is what keeps the header honest: add
# one inline handler back and script-src silently stops protecting anything.
# --------------------------------------------------------------------------

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "app" / "templates"

INLINE_HANDLER = re.compile(r"(?:^|[^a-zA-Z-])on[a-z]+\s*=\s*[\"']")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)


def _templates():
    return sorted(TEMPLATE_ROOT.rglob("*.html"))


def test_no_template_uses_an_inline_event_handler():
    offenders = [
        f"{path.relative_to(TEMPLATE_ROOT)}:{i}"
        for path in _templates()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if INLINE_HANDLER.search(line)
    ]
    assert offenders == [], (
        "inline on*= handlers are unreachable under this CSP - "
        f"use data-action and appActions.register: {offenders}"
    )


def test_no_template_uses_a_javascript_url():
    offenders = [
        str(path.relative_to(TEMPLATE_ROOT))
        for path in _templates()
        if "javascript:" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"javascript: URLs are blocked by script-src: {offenders}"


def test_every_inline_script_block_carries_a_nonce():
    offenders = [
        f"{path.relative_to(TEMPLATE_ROOT)}: {tag}"
        for path in _templates()
        for tag in INLINE_SCRIPT.findall(path.read_text(encoding="utf-8"))
        if "csp_nonce()" not in tag
    ]
    assert offenders == [], f"inline <script> without a nonce will not run: {offenders}"


def test_script_src_is_nonced_and_not_unsafe(app):
    with app.test_client() as client:
        csp = client.get("/health").headers["Content-Security-Policy"]

    script_src = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert re.search(r"'nonce-[A-Za-z0-9_-]{20,}'", script_src), script_src


def test_the_nonce_changes_between_requests(app):
    """Including under one long-lived app context, which is what `g` would share."""
    with app.test_client() as client:
        first = client.get("/health").headers["Content-Security-Policy"]
        second = client.get("/health").headers["Content-Security-Policy"]

    assert _nonce_of(first) != _nonce_of(second)


def test_the_rendered_page_uses_the_nonce_from_its_own_header(app):
    """A mismatch here means every inline block on the page is dead."""
    with app.test_client() as client:
        response = client.get("/")

    nonce = _nonce_of(response.headers["Content-Security-Policy"])
    body = response.get_data(as_text=True)
    assert f'nonce="{nonce}"' in body
    # And exactly one nonce is in play, not one per rendered block.
    assert set(re.findall(r'nonce="([^"]+)"', body)) == {nonce}


def _nonce_of(csp):
    return re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp).group(1)


# --------------------------------------------------------------------------
# The other half of the trade: behaviour that used to live in an on*= attribute
# now lives behind a data-action name, and a name that resolves to nothing is a
# button that silently does nothing. A typo in either half fails here.
# --------------------------------------------------------------------------

STATIC_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js"

ACTION_ATTRIBUTE = re.compile(r'data-action(?:-change|-submit|-error)?="([a-z0-9-]+)"')
REGISTERED_KEY = re.compile(r"^\s*'([a-z0-9-]+)':\s", re.M)
JS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _register_blocks(text):
    """The object literal passed to each appActions.register(...) call."""
    for match in re.finditer(r"appActions\.register\(\{", text):
        start = text.index("{", match.start())
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : i + 1]
                    break


def _action_names():
    used, registered = {}, set()
    for path in _templates() + sorted(STATIC_JS.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        # Doc comments in the dispatcher itself are not usages.
        for name in ACTION_ATTRIBUTE.findall(JS_COMMENT.sub("", text)):
            used.setdefault(name, set()).add(str(path.name))
        for block in _register_blocks(text):
            registered.update(REGISTERED_KEY.findall(block))
    return used, registered


def test_every_data_action_resolves_to_a_registered_handler():
    used, registered = _action_names()
    orphans = {name: sorted(files) for name, files in used.items() if name not in registered}
    assert orphans == {}, f"data-action names with no handler: {orphans}"


def test_no_handler_is_registered_for_an_action_nothing_uses():
    used, registered = _action_names()
    assert sorted(registered - set(used)) == []
