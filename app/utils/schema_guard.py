"""
Minimal schema guard for databases managed by db.create_all().

create_all() only creates missing tables; it never adds columns to tables that
already exist, and it never reshapes an index whose definition has changed.
Until the project adopts versioned Alembic migrations, both kinds of change are
registered here and applied on startup with idempotent DDL (works on both
PostgreSQL and SQLite).
"""

import logging

from sqlalchemy import inspect

from app import db

logger = logging.getLogger(__name__)

# (table, column, DDL type + default) for columns added after tables shipped
COLUMNS = [
    ("groups", "pick_team_once", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("groups", "no_repeat_opponent", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("groups", "playoff_spots", "INTEGER NOT NULL DEFAULT 4"),
    ("groups", "superbowl_spots", "INTEGER NOT NULL DEFAULT 2"),
]

# (table, index, columns) for indexes that shipped UNIQUE but must not be.
#
# Teams get one row per season, so a franchise carries the same espn_id every
# year. A global unique index on it made the second season's teams impossible to
# insert - the first rollover attempt died on "duplicate key value violates
# unique constraint ix_teams_espn_id" and left the app on the old season. The
# uniqueness that actually holds is per season, recreated in UNIQUE_INDEXES.
DROP_UNIQUE_INDEXES = [
    ("teams", "ix_teams_espn_id", ["espn_id"]),
    ("teams", "ix_teams_nfl_id", ["nfl_id"]),
]

# (table, index, columns) for unique indexes an existing database may lack.
# On a fresh database create_all() builds these from the model's
# UniqueConstraint, and the guard finds them already present.
UNIQUE_INDEXES = [
    ("teams", "unique_team_season_espn", ["season_id", "espn_id"]),
]

# (table, column) whose stored values must be folded to lower case. The models
# normalise on write, but rows written before that shipped are still mixed
# case, and the expression unique indexes below cannot be trusted until they
# are. Runs before EXPRESSION_UNIQUE_INDEXES for that reason.
LOWERCASE_BACKFILL = [
    ("users", "email"),
    ("invites", "invitee_email"),
]

# (table, index, expression) for uniqueness that holds case-insensitively.
#
# Checking this in the WTForms validators only was not enough: it covered the
# two routes that use those forms, missed every other write path, and two
# concurrent registrations could still race past it. `Andi` and `andi` both
# existing would make sign-in ambiguous, so the guarantee belongs in the
# database. Postgres and SQLite (3.9+) both index expressions.
EXPRESSION_UNIQUE_INDEXES = [
    ("users", "uq_users_username_lower", "lower(username)"),
    ("users", "uq_users_email_lower", "lower(email)"),
]


def _ensure_columns(existing_tables):
    """Add any registered columns that are missing from existing tables"""
    for table, column, ddl in COLUMNS:
        if table not in existing_tables:
            continue  # create_all will create it with all columns

        try:
            inspector = inspect(db.engine)
            existing_columns = {c["name"] for c in inspector.get_columns(table)}
            if column in existing_columns:
                continue

            db.session.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            db.session.commit()
            logger.info(f"Schema guard: added column {table}.{column}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Schema guard failed adding {table}.{column}: {e}")


def _relax_unique_indexes(existing_tables):
    """Recreate registered indexes without UNIQUE where a database still has it"""
    for table, index, columns in DROP_UNIQUE_INDEXES:
        if table not in existing_tables:
            continue  # create_all builds it from the current model definition

        try:
            inspector = inspect(db.engine)
            existing = {i["name"]: i for i in inspector.get_indexes(table)}.get(index)
            if existing is None or not existing.get("unique"):
                continue  # already gone, or already non-unique

            column_list = ", ".join(columns)
            db.session.execute(db.text(f"DROP INDEX {index}"))
            db.session.execute(
                db.text(f"CREATE INDEX {index} ON {table} ({column_list})")
            )
            db.session.commit()
            logger.info(f"Schema guard: dropped UNIQUE from {table}.{index}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Schema guard failed relaxing {table}.{index}: {e}")


def _ensure_unique_indexes(existing_tables):
    """Create registered unique indexes that an existing database is missing"""
    for table, index, columns in UNIQUE_INDEXES:
        if table not in existing_tables:
            continue  # create_all will build it from the model

        try:
            inspector = inspect(db.engine)
            names = {i["name"] for i in inspector.get_indexes(table)}
            names |= {c["name"] for c in inspector.get_unique_constraints(table)}
            if index in names:
                continue

            column_list = ", ".join(columns)
            db.session.execute(
                db.text(f"CREATE UNIQUE INDEX {index} ON {table} ({column_list})")
            )
            db.session.commit()
            logger.info(f"Schema guard: created unique index {table}.{index}")
        except Exception as e:
            # Duplicate rows would make this fail; the app still runs without it.
            db.session.rollback()
            logger.error(f"Schema guard failed creating {table}.{index}: {e}")


def _backfill_lowercase(existing_tables):
    """Fold registered columns to lower case where a row still differs"""
    for table, column in LOWERCASE_BACKFILL:
        if table not in existing_tables:
            continue

        try:
            result = db.session.execute(
                db.text(
                    f"UPDATE {table} SET {column} = lower({column}) "
                    f"WHERE {column} IS NOT NULL AND {column} <> lower({column})"
                )
            )
            db.session.commit()
            if result.rowcount:
                logger.info(
                    f"Schema guard: lower-cased {result.rowcount} "
                    f"{table}.{column} value(s)"
                )
        except Exception as e:
            db.session.rollback()
            logger.error(f"Schema guard failed normalising {table}.{column}: {e}")


def _ensure_expression_unique_indexes(existing_tables):
    """Create registered expression unique indexes that a database is missing"""
    for table, index, expression in EXPRESSION_UNIQUE_INDEXES:
        if table not in existing_tables:
            continue

        try:
            db.session.execute(
                db.text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index} "
                    f"ON {table} ({expression})"
                )
            )
            db.session.commit()
        except Exception as e:
            # Rows colliding case-insensitively would make this fail. The app
            # still runs without the index - sign-in folds case either way -
            # so log it and leave the collision for an operator to resolve.
            db.session.rollback()
            logger.error(f"Schema guard failed creating {table}.{index}: {e}")


def ensure_schema():
    """Bring an existing database in line with the current models"""
    try:
        existing_tables = set(inspect(db.engine).get_table_names())
    except Exception as e:
        logger.error(f"Schema guard could not inspect database: {e}")
        return

    _ensure_columns(existing_tables)
    _relax_unique_indexes(existing_tables)
    _backfill_lowercase(existing_tables)
    _ensure_unique_indexes(existing_tables)
    _ensure_expression_unique_indexes(existing_tables)
