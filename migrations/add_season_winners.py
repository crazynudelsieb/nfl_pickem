"""Add season winners table for tracking champions and awards

This migration adds the season_winners table to track:
- Season champions (global and per-group)
- Runner-ups and third place finishers
- User awards and achievements
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


def upgrade():
    # Create season_winners table
    op.create_table(
        "season_winners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("award_type", sa.String(length=50), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("total_wins", sa.Integer(), default=0),
        sa.Column("total_points", sa.Integer(), default=0),
        sa.Column("tiebreaker_points", sa.Integer(), default=0),
        sa.Column("accuracy", sa.Float(), default=0.0),
        sa.Column(
            "created_at", sa.DateTime(), default=lambda: datetime.now(timezone.utc)
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["seasons.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "season_id",
            "user_id",
            "group_id",
            "award_type",
            name="unique_season_winner",
        ),
    )

    # Create indexes
    op.create_index("idx_winner_season", "season_winners", ["season_id"])
    op.create_index("idx_winner_user", "season_winners", ["user_id"])
    op.create_index("idx_winner_group", "season_winners", ["group_id"])


def downgrade():
    # Drop indexes
    op.drop_index("idx_winner_group", table_name="season_winners")
    op.drop_index("idx_winner_user", table_name="season_winners")
    op.drop_index("idx_winner_season", table_name="season_winners")

    # Drop table
    op.drop_table("season_winners")
