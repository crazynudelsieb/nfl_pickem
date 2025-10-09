#!/usr/bin/env python3
"""
Database migration: Add tiebreaker_points column to picks table
Run this script to add the new tiebreaker_points column for the updated scoring system
"""

import os
import sys

import psycopg


def get_db_connection():
    """Get database connection from environment variables"""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://nfl_user:nfl_password@localhost:5432/nfl_pickem_db",
    )

    # Convert SQLAlchemy URL format to psycopg format for direct connection
    if db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://")

    # psycopg 3 can handle the full URL directly
    return psycopg.connect(db_url)


def run_migration():
    """Add tiebreaker_points column to picks table"""
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cursor = conn.cursor()

        print("🔄 Adding tiebreaker_points column to picks table...")

        # Check if column already exists
        cursor.execute(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='picks' AND column_name='tiebreaker_points';
        """
        )

        if cursor.fetchone():
            print("✅ Column tiebreaker_points already exists")
        else:
            # Add the column
            cursor.execute(
                """
                ALTER TABLE picks 
                ADD COLUMN tiebreaker_points INTEGER DEFAULT 0;
            """
            )
            print("✅ Added tiebreaker_points column")

        # Update existing records to calculate tiebreaker points
        print("🔄 Updating existing pick records...")
        cursor.execute(
            """
            UPDATE picks 
            SET tiebreaker_points = CASE 
                WHEN is_correct = true THEN (
                    SELECT ABS(COALESCE(home_score, 0) - COALESCE(away_score, 0))
                    FROM games 
                    WHERE games.id = picks.game_id AND games.is_final = true
                )
                WHEN is_correct = false THEN -(
                    SELECT ABS(COALESCE(home_score, 0) - COALESCE(away_score, 0))
                    FROM games 
                    WHERE games.id = picks.game_id AND games.is_final = true
                )
                ELSE 0
            END
            WHERE tiebreaker_points = 0 OR tiebreaker_points IS NULL;
        """
        )

        updated_rows = cursor.rowcount
        print(f"✅ Updated {updated_rows} existing pick records")

        cursor.close()
        conn.close()

        print("🎉 Migration completed successfully!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

    return True


if __name__ == "__main__":
    print("🏈 NFL Pick'em - Adding Tiebreaker Points Migration")
    print("=" * 50)

    if run_migration():
        print("\n✅ All migrations completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
