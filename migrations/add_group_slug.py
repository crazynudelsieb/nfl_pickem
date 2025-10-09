"""Add slug column to groups table"""

import secrets

from app import create_app, db
from app.models import Group


def upgrade():
    """Add slug column and populate for existing groups"""
    app = create_app()
    with app.app_context():
        # Add slug column
        print("Adding slug column to groups table...")
        db.session.execute(
            db.text(
                "ALTER TABLE groups ADD COLUMN IF NOT EXISTS slug VARCHAR(16) UNIQUE"
            )
        )
        db.session.commit()

        # Generate slugs for existing groups
        print("Generating slugs for existing groups...")
        groups = Group.query.filter(db.or_(Group.slug == None, Group.slug == "")).all()

        for group in groups:
            while True:
                slug = secrets.token_urlsafe(12)[:16]
                if not Group.query.filter_by(slug=slug).first():
                    group.slug = slug
                    break

        db.session.commit()
        print(f"Generated slugs for {len(groups)} groups")

        # Make slug column NOT NULL
        print("Making slug column NOT NULL...")
        db.session.execute(db.text("ALTER TABLE groups ALTER COLUMN slug SET NOT NULL"))
        db.session.commit()

        print("Migration completed successfully!")


if __name__ == "__main__":
    upgrade()
