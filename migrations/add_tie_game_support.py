#!/usr/bin/env python3
"""
Database migration: Add tie game support with half points
- Convert points_earned from INTEGER to FLOAT
- Convert tiebreaker_points from INTEGER to FLOAT
- Retroactively update all existing tie game picks
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
    """Convert points columns to Float and update tie games"""
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cursor = conn.cursor()

        print("🔄 Step 1: Converting points_earned to DOUBLE PRECISION (Float)...")

        # Check current column type
        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name='picks' AND column_name='points_earned';
        """
        )
        current_type = cursor.fetchone()

        if current_type and current_type[0] == 'integer':
            # Convert INTEGER to DOUBLE PRECISION (PostgreSQL's Float type)
            cursor.execute(
                """
                ALTER TABLE picks
                ALTER COLUMN points_earned TYPE DOUBLE PRECISION;
            """
            )
            print("✅ Converted points_earned to DOUBLE PRECISION")
        else:
            print(f"✅ Column points_earned already type: {current_type[0] if current_type else 'unknown'}")

        print("🔄 Step 2: Converting tiebreaker_points to DOUBLE PRECISION (Float)...")

        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name='picks' AND column_name='tiebreaker_points';
        """
        )
        current_type = cursor.fetchone()

        if current_type and current_type[0] == 'integer':
            cursor.execute(
                """
                ALTER TABLE picks
                ALTER COLUMN tiebreaker_points TYPE DOUBLE PRECISION;
            """
            )
            print("✅ Converted tiebreaker_points to DOUBLE PRECISION")
        else:
            print(f"✅ Column tiebreaker_points already type: {current_type[0] if current_type else 'unknown'}")

        print("🔄 Step 3: Finding and updating tie game picks...")

        # Update picks for tie games retroactively
        cursor.execute(
            """
            UPDATE picks
            SET
                points_earned = 0.5,
                tiebreaker_points = (
                    SELECT (COALESCE(g.home_score, 0) + COALESCE(g.away_score, 0)) / 2.0
                    FROM games g
                    WHERE g.id = picks.game_id
                ),
                is_correct = NULL
            WHERE game_id IN (
                SELECT id FROM games
                WHERE is_final = true
                AND home_score = away_score
                AND home_score IS NOT NULL
            );
        """
        )

        updated_rows = cursor.rowcount
        print(f"✅ Updated {updated_rows} tie game pick records")

        # Show some stats
        print("\n📊 Migration Statistics:")
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_tie_picks,
                SUM(points_earned) as total_tie_points
            FROM picks
            WHERE is_correct IS NULL;
        """
        )
        stats = cursor.fetchone()
        if stats:
            print(f"   - Total tie game picks: {stats[0]}")
            print(f"   - Total points from ties: {stats[1]}")

        cursor.close()
        conn.close()

        print("\n🎉 Migration completed successfully!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    print("🏈 NFL Pick'em - Add Tie Game Support Migration")
    print("=" * 60)
    print("This migration will:")
    print("  1. Convert points_earned to Float (DOUBLE PRECISION)")
    print("  2. Convert tiebreaker_points to Float (DOUBLE PRECISION)")
    print("  3. Retroactively update all tie game picks with 0.5 points")
    print("=" * 60)

    if run_migration():
        print("\n✅ All migrations completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
