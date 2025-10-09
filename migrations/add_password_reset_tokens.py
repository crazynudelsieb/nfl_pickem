"""
Add password reset token fields to users table

This migration adds reset_token and reset_token_expiry columns to support
password reset functionality.
"""

from app import db


def upgrade():
    """Add reset token columns to users table"""
    with db.engine.connect() as conn:
        # Add reset_token column
        conn.execute(
            db.text(
                """
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS reset_token VARCHAR(100) UNIQUE
        """
            )
        )

        # Add reset_token_expiry column
        conn.execute(
            db.text(
                """
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP
        """
            )
        )

        conn.commit()

    print("✅ Added password reset token columns to users table")


def downgrade():
    """Remove reset token columns from users table"""
    with db.engine.connect() as conn:
        conn.execute(
            db.text(
                """
            ALTER TABLE users 
            DROP COLUMN IF EXISTS reset_token,
            DROP COLUMN IF EXISTS reset_token_expiry
        """
            )
        )

        conn.commit()

    print("✅ Removed password reset token columns from users table")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")

    from app import create_app

    app = create_app()
    with app.app_context():
        upgrade()
        print("Migration completed successfully!")
