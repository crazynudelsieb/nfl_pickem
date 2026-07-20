"""
Minimal schema guard for databases managed by db.create_all().

create_all() only creates missing tables; it never adds columns to tables that
already exist. Until the project adopts versioned Alembic migrations, columns
added after the initial deployment are registered here and added on startup
with an idempotent ALTER TABLE (works on both PostgreSQL and SQLite).
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


def ensure_schema():
    """Add any registered columns that are missing from existing tables"""
    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as e:
        logger.error(f"Schema guard could not inspect database: {e}")
        return

    for table, column, ddl in COLUMNS:
        if table not in existing_tables:
            continue  # create_all will create it with all columns

        try:
            existing_columns = {c["name"] for c in inspector.get_columns(table)}
            if column in existing_columns:
                continue

            db.session.execute(
                db.text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            )
            db.session.commit()
            logger.info(f"Schema guard: added column {table}.{column}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Schema guard failed adding {table}.{column}: {e}")
