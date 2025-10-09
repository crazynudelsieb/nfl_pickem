"""
Migration: Add per-group picks support
- Add group_id column to picks table
- Add picks_are_global column to users table
- Update constraint to allow multiple picks per game (one per group)
"""

import os

import psycopg2

# PostgreSQL connection from environment variable
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "postgresql://nfl_user:nfl_password@localhost:5432/nfl_pickem_db"
)


def migrate():
    print("Starting migration: Add per-group picks support")
    print(f"Connecting to PostgreSQL...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        # 1. Add group_id column to picks table
        print("Adding group_id column to picks table...")
        cur.execute(
            """
            ALTER TABLE picks 
            ADD COLUMN IF NOT EXISTS group_id INTEGER NULL
        """
        )

        # 2. Add foreign key constraint
        print("Adding foreign key constraint...")
        cur.execute(
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_pick_group'
                ) THEN
                    ALTER TABLE picks 
                    ADD CONSTRAINT fk_pick_group 
                    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """
        )

        # 3. Add index for group_id
        print("Adding index for group_id...")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pick_group ON picks(group_id)
        """
        )

        # 4. Drop old unique constraint if exists
        print("Updating unique constraint...")
        cur.execute(
            """
            ALTER TABLE picks 
            DROP CONSTRAINT IF EXISTS unique_user_game_pick
        """
        )

        # 5. Add new unique constraint including group_id
        cur.execute(
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'unique_user_game_group_pick'
                ) THEN
                    ALTER TABLE picks 
                    ADD CONSTRAINT unique_user_game_group_pick 
                    UNIQUE (user_id, game_id, group_id);
                END IF;
            END $$;
        """
        )

        # 6. Add picks_are_global column to users table
        print("Adding picks_are_global column to users table...")
        cur.execute(
            """
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS picks_are_global BOOLEAN DEFAULT FALSE
        """
        )

        # 7. Update existing picks to use first group (for users who want per-group picks)
        print("Migrating existing picks to first group...")
        cur.execute(
            """
            UPDATE picks 
            SET group_id = (
                SELECT gm.group_id 
                FROM group_members gm 
                WHERE gm.user_id = picks.user_id 
                AND gm.is_active = TRUE
                ORDER BY gm.joined_at ASC
                LIMIT 1
            )
            WHERE group_id IS NULL
        """
        )

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migrate()
