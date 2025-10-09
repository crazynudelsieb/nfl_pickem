"""
Migration: Add avatar_url column to users table and populate existing users
Date: October 8, 2025
"""

from app import db
from app.models import User


def upgrade():
    """Add avatar_url column and populate existing users with random avatars"""
    print("Adding avatar_url column to users table...")

    # Add column if it doesn't exist
    try:
        db.session.execute(
            db.text(
                """
            ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);
        """
            )
        )
        db.session.commit()
        print("✓ avatar_url column added")
    except Exception as e:
        if (
            "duplicate column name" in str(e).lower()
            or "already exists" in str(e).lower()
        ):
            print("✓ avatar_url column already exists")
            db.session.rollback()
        else:
            raise e

    # Populate existing users without avatars
    print("Populating avatars for existing users...")
    users_without_avatars = User.query.filter(
        (User.avatar_url == None) | (User.avatar_url == "")
    ).all()

    count = 0
    for user in users_without_avatars:
        # Generate avatar based on username for consistency
        user.avatar_url = User.generate_avatar_url(user.username)
        count += 1

        if count % 10 == 0:
            db.session.commit()
            print(f"  Updated {count} users...")

    db.session.commit()
    print(f"✓ Updated {count} users with avatars")
    print("Migration completed successfully!")


def downgrade():
    """Remove avatar_url column"""
    print("Removing avatar_url column from users table...")

    try:
        db.session.execute(
            db.text(
                """
            ALTER TABLE users DROP COLUMN avatar_url;
        """
            )
        )
        db.session.commit()
        print("✓ avatar_url column removed")
    except Exception as e:
        print(f"Error removing column: {e}")
        db.session.rollback()
        raise e


if __name__ == "__main__":
    print("=" * 60)
    print("Running Avatar URL Migration")
    print("=" * 60)
    upgrade()
