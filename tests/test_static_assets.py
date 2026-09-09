"""Guards on how static assets are versioned and how the mobile nav is pinned.

Both cover the same outage. A release stretched the mobile bottom nav over the
whole viewport, the follow-up corrected the stylesheet, and users kept seeing
the broken bar anyway because the asset URL never changed and the service
worker serves `/static/` cache-first without revalidating.
"""

import re
from pathlib import Path

from app import __version__, create_app, static_url

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "main.css"

STAMP = re.compile(r"\?v=[0-9a-f]{12}$")


def test_stylesheet_link_is_content_stamped():
    app = create_app("testing")

    with app.test_client() as client:
        html = client.get("/auth/login", follow_redirects=True).get_data(as_text=True)

    links = re.findall(r'href="(/static/css/main\.css[^"]*)"', html)
    assert links, "base.html no longer links the stylesheet"
    assert STAMP.search(links[0]), f"stylesheet URL is not content-stamped: {links[0]}"


def test_stamp_follows_the_bytes():
    """A hand-maintained `?v=` is what let the fix sit undelivered. The stamp
    has to move on its own when the file does, and settle back when it doesn't.
    """
    app = create_app("testing")

    with app.test_request_context("/"):
        before = static_url("css/main.css")
        original = CSS.read_bytes()
        try:
            CSS.write_bytes(original + b"\n/* stamp probe */\n")
            changed = static_url("css/main.css")
        finally:
            CSS.write_bytes(original)
        after = static_url("css/main.css")

    assert changed != before, "stamp did not change when the stylesheet changed"
    assert after == before, "stamp did not settle back when the change was undone"


def test_missing_asset_still_gets_a_stamp():
    """Dropping the stamp would pin a typo'd URL in caches indefinitely."""
    app = create_app("testing")

    with app.test_request_context("/"):
        assert static_url("css/not-here.css").endswith(f"?v={__version__}")


def test_bottom_nav_pins_to_the_bottom_only():
    """`position: fixed` with both `top` and `bottom` resolved stretches the bar
    to the full viewport, and its z-index then covers the page with five giant
    buttons. The explicit `top: auto` is what keeps a broader rule from doing
    that, so it has to stay in the declaration.
    """
    block = re.search(r"\.mobile-bottom-nav\s*\{([^}]*)\}", CSS.read_text(encoding="utf-8"))
    assert block, ".mobile-bottom-nav rule is gone"
    assert re.search(r"\btop:\s*auto\b", block.group(1)), block.group(1)


def test_no_bare_nav_element_selector():
    """The header bar's rules once matched every <nav>, which is how `top: 0`
    reached the bottom bar and the footer's link list. Keep them scoped.
    """
    css = CSS.read_text(encoding="utf-8")
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    offenders = re.findall(r"(?:^|[},])\s*(nav\s*(?:,|\{))", stripped, flags=re.M)
    assert not offenders, f"unscoped nav selector(s): {offenders}"
