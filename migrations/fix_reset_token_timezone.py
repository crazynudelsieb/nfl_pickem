"""
Fix reset_token_expiry timezone handling.

This migration ensures that the reset_token_expiry column properly handles
timezone-aware datetimes. PostgreSQL TIMESTAMP WITH TIME ZONE is used to
store timezone-aware values.

Run with: python migrations/fix_reset_token_timezone.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text


def upgrade():
    """Convert reset_token_expiry to TIMESTAMP WITH TIME ZONE"""
    print("Converting reset_token_expiry to timezone-aware column...")

    # PostgreSQL: ALTER COLUMN TYPE to TIMESTAMP WITH TIME ZONE
    # This preserves existing data and makes the column timezone-aware
    db.session.execute(
        text("""
        ALTER TABLE users
        ALTER COLUMN reset_token_expiry
        TYPE TIMESTAMP WITH TIME ZONE
        USING reset_token_expiry AT TIME ZONE 'UTC'
        """)
    )

    db.session.commit()
    print("SUCCESS: reset_token_expiry column is now timezone-aware")


def downgrade():
    """Revert reset_token_expiry to TIMESTAMP WITHOUT TIME ZONE"""
    print("Reverting reset_token_expiry to timezone-naive column...")

    db.session.execute(
        text("""
        ALTER TABLE users
        ALTER COLUMN reset_token_expiry
        TYPE TIMESTAMP WITHOUT TIME ZONE
        """)
    )

    db.session.commit()
    print("SUCCESS: reset_token_expiry column reverted to timezone-naive")


if __name__ == "__main__":
    import os

    # Disable background services during migration
    os.environ['SCHEDULER_ENABLED'] = 'False'
    os.environ['SOCKETIO_ENABLED'] = 'False'

    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("Password Reset Token Timezone Migration")
        print("=" * 60)

        try:
            upgrade()
            print("\nSUCCESS: Migration completed successfully!")
        except Exception as e:
            print(f"\nERROR: Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
