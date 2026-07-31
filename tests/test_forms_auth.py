"""Name fields must reject markup on every form that writes them.

The leaderboard passes usernames to the browser through a data attribute that
client code reads back with getAttribute(), which returns the decoded value -
template escaping does not survive that path. EditProfileForm used to have no
character restriction at all, so a user could register cleanly and then edit
their way to a stored XSS payload.
"""

import pytest

from app.forms.auth import EditProfileForm, RegistrationForm

PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>",
    'a" onmouseover="alert(1)',
    "a<b>c",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_edit_profile_rejects_markup_username(app, payload):
    with app.test_request_context(
        method="POST",
        data={"username": payload, "email": "e@example.com", "display_name": ""},
    ):
        form = EditProfileForm(
            original_username="old", original_email="old@example.com"
        )
        assert not form.validate()
        assert "username" in form.errors


@pytest.mark.parametrize("payload", PAYLOADS)
def test_edit_profile_rejects_markup_display_name(app, payload):
    with app.test_request_context(
        method="POST",
        data={"username": "valid.name", "email": "e@example.com",
              "display_name": payload},
    ):
        form = EditProfileForm(
            original_username="old", original_email="old@example.com"
        )
        assert not form.validate()
        assert "display_name" in form.errors


@pytest.mark.parametrize("payload", PAYLOADS)
def test_registration_rejects_markup_username(app, payload):
    with app.test_request_context(
        method="POST",
        data={
            "username": payload,
            "email": "e@example.com",
            "display_name": "",
            "password": "Password1",
            "password_confirm": "Password1",
        },
    ):
        form = RegistrationForm()
        assert not form.validate()
        assert "username" in form.errors


def test_edit_profile_accepts_ordinary_name(app):
    with app.test_request_context(
        method="POST",
        data={
            "username": "alice.doe-1_x",
            "email": "e@example.com",
            "display_name": "Alice Doe",
        },
    ):
        form = EditProfileForm(
            original_username="old", original_email="old@example.com"
        )
        assert form.validate(), form.errors
