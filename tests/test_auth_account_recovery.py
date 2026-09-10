"""Sign-in and password recovery must agree on how an account is identified.

A user with two accounts reset the password on one of them twice and still
could not get in, because sign-in matched only the exact `username` column
while recovery was keyed on `email`. Nothing errored: each reset succeeded, on
an account other than the one being typed into the login form. Postgres made it
worse - `Andi` is not `andi`, and an address stored as `Andreas.C@gmail.com`
never matched the same address typed in lower case, so recovery answered "if an
account exists" and did nothing at all.
"""

import pytest

from app.forms.auth import RegistrationForm
from app.models import User
from tests.conftest import make_user


@pytest.fixture
def andi(db):
    """An account whose stored name and address both carry capitals."""
    user = User(username="Andi", email="Andreas.Cervinka@gmail.com")
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.mark.parametrize(
    "identifier",
    [
        "Andi",                          # exactly as stored
        "andi",                          # phone keyboard, all lower case
        "ANDI",
        "  Andi  ",                      # autofill dragged whitespace along
        "Andreas.Cervinka@gmail.com",    # the address, as stored
        "andreas.cervinka@gmail.com",    # the address, as a user types it
        " Andreas.Cervinka@Gmail.com ",
    ],
)
def test_login_identifier_finds_the_account(app, andi, identifier):
    assert User.find_by_login_identifier(identifier) is andi


@pytest.mark.parametrize("identifier", ["", "   ", None, "nobody", "no@one.example"])
def test_login_identifier_rejects_unknown(app, andi, identifier):
    assert User.find_by_login_identifier(identifier) is None


def test_exact_username_wins_over_a_case_variant(app, db, andi):
    """Fallback for a database that never got the case-insensitive index.

    `uq_users_username_lower` now makes `Andi` and `andi` impossible to hold at
    once - see test_identity_normalization.py. But schema_guard logs and
    continues if that index cannot be built (pre-existing collisions would do
    it), so the exact-match-first ordering stays as the tiebreak. Drop the
    index to reach that state deliberately.
    """
    from sqlalchemy import text

    db.session.execute(text("DROP INDEX uq_users_username_lower"))
    db.session.commit()

    other = User(username="andi", email="other@example.com")
    other.set_password("Password1")
    db.session.add(other)
    db.session.commit()

    assert User.find_by_login_identifier("Andi") is andi
    assert User.find_by_login_identifier("andi") is other


@pytest.mark.parametrize(
    "typed",
    [
        "Andreas.Cervinka@gmail.com",
        "andreas.cervinka@gmail.com",
        "  ANDREAS.CERVINKA@GMAIL.COM  ",
    ],
)
def test_forgot_password_finds_the_account(app, andi, typed):
    assert User.find_by_email(typed) is andi


@pytest.mark.parametrize("typed", ["", "   ", None, "someone@else.example"])
def test_forgot_password_rejects_unknown(app, andi, typed):
    assert User.find_by_email(typed) is None


def test_login_accepts_email_and_lands_on_the_right_account(app, andi):
    """The end-to-end path: sign in with the address, not the username."""
    client = app.test_client()
    response = client.post(
        "/auth/login",
        data={
            "username": "andreas.cervinka@gmail.com",
            "password": "Password1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302, "sign-in with the email address failed"

    with client.session_transaction() as session:
        assert session.get("_user_id") == str(andi.id)


def test_login_still_rejects_a_wrong_password(app, andi):
    client = app.test_client()
    response = client.post(
        "/auth/login",
        data={"username": "andi", "password": "not-the-password"},
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_accepts_an_email_longer_than_the_username_column(app, db):
    """The field caps at the email column (120), not the username column (80)."""
    address = "pickem.appchen.com.calculus118.a.rather.long.masked.relay.alias.v2@passmail.example"
    assert 80 < len(address) <= 120

    user = User(username="Ace", email=address)
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()

    client = app.test_client()
    response = client.post(
        "/auth/login", data={"username": address, "password": "Password1"}
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session.get("_user_id") == str(user.id)


def test_reset_flow_names_the_account_it_reset(app, db, andi):
    """The user is told the one thing the login form is about to ask for."""
    token = andi.generate_reset_token()
    db.session.commit()

    client = app.test_client()
    page = client.get(f"/auth/reset_password/{token}")
    assert b"Andi" in page.data, "reset page does not name the account"

    response = client.post(
        f"/auth/reset_password/{token}",
        data={"password": "BrandNew1", "confirm_password": "BrandNew1"},
        follow_redirects=True,
    )
    assert b"Sign in as &#39;Andi&#39;" in response.data or b"Sign in as 'Andi'" in response.data

    # And the new password actually works, by either identifier.
    assert User.find_by_login_identifier("andi").check_password("BrandNew1")


def test_reset_email_names_the_account(app, andi, monkeypatch):
    from app.utils.email_service import EmailService

    sent = {}

    def capture(self, message):
        sent["body"] = message.as_string()
        return True

    monkeypatch.setattr(EmailService, "_send_email", capture)

    with app.test_request_context("/", base_url="https://pickem.example"):
        EmailService().send_password_reset_email(andi, "tok123")

    assert "Andi" in sent["body"], "reset email never names the username"


@pytest.mark.parametrize("taken", ["ALICE", "Alice", "  alice  "])
def test_registration_rejects_a_case_variant_username(app, db, taken):
    """Two accounts differing only by case would make sign-in ambiguous."""
    make_user(db, "alice")
    db.session.commit()

    with app.test_request_context(
        method="POST",
        data={
            "username": taken,
            "email": "new@example.com",
            "display_name": "",
            "password": "Password1",
            "password_confirm": "Password1",
        },
    ):
        form = RegistrationForm()
        assert not form.validate()
        assert "username" in form.errors


@pytest.mark.parametrize("taken", ["ALICE@EXAMPLE.COM", "Alice@Example.com"])
def test_registration_rejects_a_case_variant_email(app, db, taken):
    make_user(db, "alice")
    db.session.commit()

    with app.test_request_context(
        method="POST",
        data={
            "username": "newname",
            "email": taken,
            "display_name": "",
            "password": "Password1",
            "password_confirm": "Password1",
        },
    ):
        form = RegistrationForm()
        assert not form.validate()
        assert "email" in form.errors


def test_reset_password_post_still_requires_csrf(db, andi):
    """The route dropped a hand-rolled check; CSRFProtect must still cover it.

    The manual `validate_csrf` call ignored WTF_CSRF_ENABLED, so it fired even
    where the app had switched CSRF off. Removing it is only safe because
    CSRFProtect guards every POST app-wide - assert that, rather than trusting
    it.
    """
    from app import create_app
    from app import db as _db

    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        _db.create_all()
        try:
            user = User(username="Andi", email="Andreas.Cervinka@gmail.com")
            user.set_password("Password1")
            _db.session.add(user)
            _db.session.commit()
            token = user.generate_reset_token()
            _db.session.commit()

            response = app.test_client().post(
                f"/auth/reset_password/{token}",
                data={"password": "BrandNew1", "confirm_password": "BrandNew1"},
            )
            # The app's CSRFError handler flashes and bounces back to the
            # form rather than returning 400; what matters is that the view
            # never ran.
            assert response.status_code == 302
            assert not user.check_password("BrandNew1"), "password changed anyway"
            assert user.reset_token is not None, "token was consumed"
        finally:
            _db.session.remove()
            _db.drop_all()
