"""Timestamps are absolute instants, shown in the app's timezone.

Production's PostgreSQL runs in Europe/Vienna. Every column was a naive
TIMESTAMP, so the UTC-aware datetimes the app writes were stored as Vienna wall
clock and read back as UTC - two hours late. For kickoff that kept games
pickable after they had started; for invites it stretched every expiry. All
columns are now TIMESTAMP WITH TIME ZONE, and the schema guard converts any a
database still has naive.
"""

from datetime import UTC, datetime

from flask import render_template_string
from sqlalchemy import DateTime

from app.models import Game
from app.utils.schema_guard import timestamptz_columns


def model_timestamps(db):
    return {
        (table.name, column.name)
        for table in db.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, DateTime)
    }


def test_every_model_timestamp_is_zoned(db):
    """A naive column takes on the database session's zone - Vienna in prod."""
    assert set(timestamptz_columns()) == model_timestamps(db)


def test_schema_guard_covers_the_columns_that_were_naive_in_production(db):
    # reset_token_expiry was declared zoned in the model and was still naive
    # in the database, because create_all never alters an existing column.
    assert {
        ("games", "game_time"),
        ("invites", "expires_at"),
        ("users", "reset_token_expiry"),
    } <= set(timestamptz_columns())


def test_localtime_filter_shows_the_app_timezone(app):
    app.config["TIMEZONE"] = "Europe/Vienna"
    rendered = render_template_string(
        "{{ aware|localtime('%H:%M') }} {{ naive|localtime('%H:%M') }} "
        "[{{ missing|localtime('%H:%M') }}]",
        aware=datetime(2026, 10, 18, 17, 0, tzinfo=UTC),
        naive=datetime(2026, 10, 18, 17, 0),  # SQLite hands back naive UTC
        missing=None,
    )

    assert rendered == "19:00 19:00 []"


def test_local_game_time_shows_kickoff_in_the_app_timezone(app):
    app.config["TIMEZONE"] = "Europe/Vienna"
    game = Game(game_time=datetime(2026, 10, 18, 17, 0, tzinfo=UTC))

    assert game.local_game_time.strftime("%H:%M") == "19:00"
