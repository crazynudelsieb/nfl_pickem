import re

from app import __version__, create_app


def test_health_endpoint_reports_ok():
    app = create_app("testing")

    with app.test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload
    assert payload.get("status") == "healthy"
    assert payload.get("version") == __version__


def test_version_is_stampable():
    """The release workflow rewrites __version__ with a sed anchored on
    `^__version__ = "..."`. If that line is ever reformatted, the stamp
    silently no-ops and the image reports a version it isn't.
    """
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
