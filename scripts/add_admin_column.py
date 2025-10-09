#!/usr/bin/env python3
"""
Add is_admin column to users table
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import User  # noqa: E402


def add_admin_column():
    """Add is_admin column to users table"""
    app = create_app()

    with app.app_context():
        # Add the column using raw SQL since it's a simple addition
        try:
            from sqlalchemy import text

            with db.engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
                )
                conn.commit()
            print("✅ Added is_admin column to users table")
        except Exception as e:
            if (
                "already exists" in str(e).lower()
                or "duplicate column" in str(e).lower()
            ):
                print("ℹ️  is_admin column already exists")
            else:
                print(f"❌ Error adding column: {e}")
                return

        # Refresh the metadata to pick up the new column
        db.metadata.reflect(bind=db.engine)

        # Optionally, make the first user an admin
        first_user = User.query.first()
        if first_user:
            # Force reload the user object to get the new column
            db.session.refresh(first_user)
            if not getattr(first_user, "is_admin", False):
                first_user.is_admin = True
                db.session.commit()
                print(f"✅ Made user '{first_user.username}' an admin")


if __name__ == "__main__":
    add_admin_column()
