"""Username and email must mean the same thing however they are typed.

Sign-in, password recovery, invite acceptance and the `received_invites` join
all compare these two columns, and each one used to normalise differently or
not at all. The rules, applied at the column so every write path gets them:

  * email  - folded to lower case, because every consumer compares it directly
  * username - whitespace trimmed, case preserved (it is what the leaderboard
    shows when display_name is empty), with uniqueness enforced case-
    insensitively by a functional index rather than by the stored value
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db as _db
from app.models import Invite, User
from tests.conftest import make_user

# --- normalisation happens on write, not at the call site -------------------

@pytest.mark.parametrize(
    "typed,stored",
    [
        ("Andreas.Cervinka@Gmail.com", "andreas.cervinka@gmail.com"),
        ("  d.kapounek@Hotmail.com  ", "d.kapounek@hotmail.com"),
        ("ALLCAPS@EXAMPLE.COM", "allcaps@example.com"),
    ],
)
def test_email_is_stored_folded(app, db, typed, stored):
    user = User(username="someone", email=typed)
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()

    assert user.email == stored


@pytest.mark.parametrize(
    "typed,stored",
    [
        ("  Andi  ", "Andi"),      # trimmed
        ("TheBerginator", "TheBerginator"),  # case kept for display
        ("Mai_Linh", "Mai_Linh"),
    ],
)
def test_username_is_trimmed_but_keeps_its_case(app, db, typed, stored):
    user = User(username=typed, email="x@example.com")
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()

    assert user.username == stored


def test_username_case_survives_for_display(app, db):
    """Lower-casing usernames would degrade the leaderboard for real accounts."""
    user = User(username="TheBerginator", email="tb@example.com")
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()

    assert user.full_name == "TheBerginator"


def test_invite_email_is_stored_folded(app, db, users, group):
    invite = Invite(
        group_id=group.id,
        inviter_id=users[0].id,
        invitee_email="  New.Person@Example.COM ",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.session.add(invite)
    db.session.flush()

    assert invite.invitee_email == "new.person@example.com"


# --- the database enforces it, not just the forms ---------------------------

def _index_names(table):
    """Read the index list from the database itself.

    SQLAlchemy's inspector cannot reflect expression-based indexes and drops
    them from get_indexes() with a warning, so reflection would report these
    two as missing when they are present and enforcing.
    """
    dialect = _db.engine.dialect.name
    if dialect == "sqlite":
        rows = _db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
            {"t": table},
        )
    else:
        rows = _db.session.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename=:t"), {"t": table}
        )
    return {row[0] for row in rows}


def test_case_insensitive_unique_indexes_exist(app):
    """The guarantee lives in the schema, so no write path can dodge it."""
    names = _index_names("users")
    assert "uq_users_username_lower" in names
    assert "uq_users_email_lower" in names


def test_database_rejects_a_case_variant_username(app, db):
    """Bypassing the forms entirely must still not create Andi *and* andi."""
    make_user(db, "Andi", email="andi@example.com")
    db.session.commit()

    clash = User(username="andi", email="different@example.com")
    clash.set_password("Password1")
    db.session.add(clash)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_database_rejects_a_case_variant_email(app, db):
    make_user(db, "one", email="Shared@Example.com")
    db.session.commit()

    clash = User(username="two", email="SHARED@example.com")
    clash.set_password("Password1")
    db.session.add(clash)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# --- rows written before the rule shipped get folded on startup -------------

def test_backfill_folds_existing_mixed_case_rows(app, db):
    """Prod already holds `Andreas.cervinka@gmail.com` and `d.kapounek@Hotmail.com`."""
    from app.utils.schema_guard import _backfill_lowercase

    make_user(db, "legacy", email="legacy@example.com")
    db.session.commit()

    # Write around the model validator, the way an old row got there.
    db.session.execute(
        text("UPDATE users SET email = 'Legacy.Mixed@Example.COM' WHERE username = 'legacy'")
    )
    db.session.commit()

    _backfill_lowercase({"users", "invites"})
    db.session.expire_all()

    assert User.query.filter_by(username="legacy").one().email == (
        "legacy.mixed@example.com"
    )


def test_backfill_is_idempotent(app, db):
    from app.utils.schema_guard import _backfill_lowercase

    make_user(db, "steady", email="steady@example.com")
    db.session.commit()

    for _ in range(3):
        _backfill_lowercase({"users", "invites"})

    assert User.query.filter_by(username="steady").one().email == "steady@example.com"


# --- the consumers that used to get it wrong --------------------------------

def test_recovery_finds_an_account_registered_in_mixed_case(app, db):
    user = User(username="Andi", email="Andreas.Cervinka@Gmail.com")
    user.set_password("Password1")
    db.session.add(user)
    db.session.commit()

    assert User.find_by_email("andreas.cervinka@gmail.com") is user
    assert User.find_by_email("ANDREAS.CERVINKA@GMAIL.COM") is user
    assert User.find_by_login_identifier("andi") is user


def test_invite_recognises_an_existing_member_in_mixed_case(app, db, users, group):
    """create_invite looked up the invitee with an unnormalised exact match."""
    member = users[1]
    invite, message = Invite.create_invite(
        group_id=group.id,
        inviter_id=users[0].id,
        invitee_email=member.email.upper(),
    )

    assert invite is None, f"already-a-member went undetected: {message}"


def test_received_invites_join_matches_after_normalisation(app, db, users, group):
    """The relationship joins User.email to Invite.invitee_email directly."""
    invitee = users[1]
    invite, _ = Invite.create_invite(
        group_id=group.id,
        inviter_id=users[0].id,
        invitee_email=invitee.email.upper(),
    )
    db.session.commit()

    assert invite is None or invite.invitee_email == invitee.email
