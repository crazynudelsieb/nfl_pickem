from datetime import datetime, timezone
import logging

from app import db

logger = logging.getLogger(__name__)


class RegularSeasonSnapshot(db.Model):
    """Snapshot of regular season standings at end of week 18

    Stores final regular season standings for playoff eligibility determination
    and historical reference. Created automatically when all week 18 games complete.
    """
    __tablename__ = "regular_season_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    # Links
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)  # NULL for global

    # Final regular season standings (weeks 1-18)
    final_rank = db.Column(db.Integer, nullable=False)
    total_wins = db.Column(db.Integer, default=0)
    total_losses = db.Column(db.Integer, default=0)
    total_ties = db.Column(db.Integer, default=0)
    total_score = db.Column(db.Float, default=0.0)
    tiebreaker_points = db.Column(db.Float, default=0.0)
    accuracy = db.Column(db.Float, default=0.0)

    # Playoff eligibility flags
    is_playoff_eligible = db.Column(db.Boolean, default=False)  # Top 4 from regular season
    is_superbowl_eligible = db.Column(db.Boolean, default=False)  # Top 2 from playoffs

    # Snapshot metadata
    snapshot_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    season = db.relationship("Season", backref="regular_season_snapshots")
    user = db.relationship("User", backref="regular_season_snapshots")
    group = db.relationship("Group", backref="regular_season_snapshots")

    # Constraints and indexes
    __table_args__ = (
        db.UniqueConstraint("season_id", "user_id", "group_id", name="unique_snapshot"),
        db.Index("idx_snapshot_season", "season_id"),
        db.Index("idx_snapshot_user", "user_id"),
        db.Index("idx_snapshot_eligible", "is_playoff_eligible"),
    )

    def __repr__(self):
        return f'<RegularSeasonSnapshot season={self.season_id} user={self.user_id} rank={self.final_rank}>'

    @staticmethod
    def create_snapshot(season_id, group_id=None):
        """Create regular season snapshots for all users at end of week 18

        Args:
            season_id: Season ID
            group_id: Optional group ID (None for global snapshot)

        Returns:
            List of created RegularSeasonSnapshot objects
        """
        from .user import User

        # Get regular season leaderboard (weeks 1-18 only)
        leaderboard = User.get_season_leaderboard(
            season_id,
            regular_season_only=True,
            group_id=group_id
        )

        if not leaderboard:
            logger.warning(f"No leaderboard data for season {season_id}, group {group_id}")
            return []

        snapshots = []
        for rank, entry in enumerate(leaderboard, start=1):
            # Check if snapshot already exists
            existing = RegularSeasonSnapshot.query.filter_by(
                season_id=season_id,
                user_id=entry["user_id"],
                group_id=group_id
            ).first()

            if existing:
                logger.info(f"Snapshot already exists for user {entry['user_id']}, season {season_id}, group {group_id}")
                snapshots.append(existing)
                continue

            snapshot = RegularSeasonSnapshot(
                season_id=season_id,
                user_id=entry["user_id"],
                group_id=group_id,
                final_rank=rank,
                total_wins=entry["wins"],
                total_losses=entry.get("losses", 0),
                total_ties=entry.get("ties", 0),
                total_score=entry["total_score"],
                tiebreaker_points=entry["tiebreaker_points"],
                accuracy=entry["accuracy"],
                is_playoff_eligible=(rank <= 4),  # Top 4 qualify for playoffs
                is_superbowl_eligible=False  # Updated later after playoff rounds
            )
            db.session.add(snapshot)
            snapshots.append(snapshot)

            logger.info(f"Created snapshot: user {entry['user_id']} rank #{rank} "
                       f"(playoff eligible: {rank <= 4})")

        try:
            db.session.commit()
            logger.info(f"Successfully created {len(snapshots)} snapshots for season {season_id}, group {group_id}")
        except Exception as e:
            logger.error(f"Error creating snapshots: {e}")
            db.session.rollback()
            raise

        return snapshots

    @staticmethod
    def update_superbowl_eligibility(season_id, group_id=None):
        """Update Super Bowl eligibility for top 2 from playoff rounds

        Called after playoff rounds (weeks 19-21) complete, before Super Bowl (week 22).
        Determines Super Bowl eligibility based on playoff performance (not regular season).

        Args:
            season_id: Season ID
            group_id: Optional group ID (None for global)
        """
        from .user import User

        # Get playoff leaderboard (weeks 19-21 only, ranked by playoff wins)
        playoff_leaderboard = User.get_playoff_leaderboard(season_id, group_id=group_id)

        if not playoff_leaderboard:
            logger.warning(f"No playoff leaderboard data for season {season_id}, group {group_id}")
            return

        # Top 2 from playoffs qualify for Super Bowl
        top2_user_ids = [entry["user_id"] for entry in playoff_leaderboard[:2]]

        # Reset all Super Bowl eligibility flags for this season/group
        reset_query = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            is_playoff_eligible=True  # Only reset for playoff participants
        )

        if group_id is not None:
            reset_query = reset_query.filter_by(group_id=group_id)
        else:
            reset_query = reset_query.filter(RegularSeasonSnapshot.group_id.is_(None))

        reset_query.update({"is_superbowl_eligible": False})

        # Set Super Bowl eligibility for top 2
        for rank, user_id in enumerate(top2_user_ids, start=1):
            snapshot = RegularSeasonSnapshot.query.filter_by(
                season_id=season_id,
                user_id=user_id,
                group_id=group_id if group_id is not None else None
            ).first()

            if snapshot:
                snapshot.is_superbowl_eligible = True
                logger.info(f"Set Super Bowl eligibility for user {user_id} (playoff rank #{rank})")

        try:
            db.session.commit()
            logger.info(f"Updated Super Bowl eligibility for season {season_id}, group {group_id}")
        except Exception as e:
            logger.error(f"Error updating Super Bowl eligibility: {e}")
            db.session.rollback()
            raise

    @staticmethod
    def get_playoff_eligible_users(season_id, group_id=None):
        """Get list of user IDs who are playoff eligible (top 4 from regular season)

        Args:
            season_id: Season ID
            group_id: Optional group ID (None for global)

        Returns:
            List of user IDs who can make playoff picks
        """
        query = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            is_playoff_eligible=True
        )

        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter(RegularSeasonSnapshot.group_id.is_(None))

        snapshots = query.order_by(RegularSeasonSnapshot.final_rank).all()
        return [s.user_id for s in snapshots]

    @staticmethod
    def get_superbowl_eligible_users(season_id, group_id=None):
        """Get list of user IDs who are Super Bowl eligible (top 2 from playoffs)

        Args:
            season_id: Season ID
            group_id: Optional group ID (None for global)

        Returns:
            List of user IDs who can make Super Bowl picks
        """
        query = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            is_superbowl_eligible=True
        )

        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter(RegularSeasonSnapshot.group_id.is_(None))

        snapshots = query.all()
        return [s.user_id for s in snapshots]

    @staticmethod
    def get_top4_names(season_id, group_id=None):
        """Get usernames of top 4 from regular season

        Useful for displaying "You did not qualify. Top 4: user1, user2, user3, user4"

        Args:
            season_id: Season ID
            group_id: Optional group ID (None for global)

        Returns:
            List of username strings
        """
        query = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            is_playoff_eligible=True
        )

        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter(RegularSeasonSnapshot.group_id.is_(None))

        snapshots = query.order_by(RegularSeasonSnapshot.final_rank).limit(4).all()
        return [s.user.username for s in snapshots]

    def to_dict(self):
        """Convert snapshot to dictionary for API responses"""
        return {
            "id": self.id,
            "season_id": self.season_id,
            "user_id": self.user_id,
            "user": self.user.username if self.user else None,
            "group_id": self.group_id,
            "final_rank": self.final_rank,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_ties": self.total_ties,
            "total_score": self.total_score,
            "tiebreaker_points": self.tiebreaker_points,
            "accuracy": self.accuracy,
            "is_playoff_eligible": self.is_playoff_eligible,
            "is_superbowl_eligible": self.is_superbowl_eligible,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
        }
