"""The upstream feed rejects some User-Agent strings, and a rejected one is
silent: every sync fails, the automatic season rollover never creates the new
season, and the app keeps serving last season's finished standings.

A bare "NFL-Pickem-App/1.0" started answering 403 in September 2026, which is
exactly how that happened. These tests pin the two properties that keep it from
recurring: the default carries a contact URL, and an operator can override it
from the environment without waiting for a new image.
"""

from app.utils.data_sync import DEFAULT_USER_AGENT, DataSync


def test_default_user_agent_identifies_the_app_with_a_contact_url():
    assert DataSync().session.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert DEFAULT_USER_AGENT.startswith("NFL-Pickem-App/")
    # The contact URL is the part the upstream edge accepts; a bare product
    # token is refused.
    assert "https://github.com/crazynudelsieb/nfl_pickem" in DEFAULT_USER_AGENT


def test_env_overrides_the_default(monkeypatch):
    monkeypatch.setenv("NFL_API_USER_AGENT", "curl/8.14.1")

    assert DataSync().session.headers["User-Agent"] == "curl/8.14.1"


def test_explicit_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("NFL_API_USER_AGENT", "from-env/1.0")

    assert DataSync(user_agent="explicit/1.0").session.headers["User-Agent"] == "explicit/1.0"


def test_unset_env_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("NFL_API_USER_AGENT", raising=False)

    assert DataSync().session.headers["User-Agent"] == DEFAULT_USER_AGENT
