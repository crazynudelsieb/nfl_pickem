"""Season Winner Model - Tracks champions and awards"""

from datetime import datetime, timezone

from app import db


class SeasonWinner(db.Model):
    """Tracks season winners for groups and global leaderboards"""

    __tablename__ = "season_winners"

    id = db.Column(db.Integer, primary_key=True)

    # Winner identification
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(
        db.Integer, db.ForeignKey("groups.id"), nullable=True
    )  # Null for global winner

    # Award type
    award_type = db.Column(
        db.String(50), nullable=False
    )  # 'champion', 'runner_up', 'third_place'
    rank = db.Column(db.Integer, nullable=False)

    # Stats at time of win
    total_wins = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    tiebreaker_points = db.Column(db.Integer, default=0)
    accuracy = db.Column(db.Float, default=0.0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    season = db.relationship("Season", backref="winners")
    user = db.relationship("User", backref="season_wins")
    group = db.relationship("Group", backref="winners")

    # Constraints
    __table_args__ = (
        db.UniqueConstraint(
            "season_id",
            "user_id",
            "group_id",
            "award_type",
            name="unique_season_winner",
        ),
        db.Index("idx_winner_season", "season_id"),
        db.Index("idx_winner_user", "user_id"),
        db.Index("idx_winner_group", "group_id"),
    )

    def __repr__(self):
        group_str = f" (Group {self.group_id})" if self.group_id else " (Global)"
        return f"<SeasonWinner {self.award_type}{group_str}: User {self.user_id}>"

    @staticmethod
    def award_season_winners(season_id):
        """Award winners for a completed season"""
        from app.models import Group, User

        results = {"global_winners": [], "group_winners": {}}

        # Award global winners
        global_leaderboard = User.get_season_leaderboard(
            season_id, regular_season_only=False, group_id=None
        )

        if global_leaderboard:
            # Top 3 places
            awards = [("champion", 1), ("runner_up", 2), ("third_place", 3)]

            for i, (award_type, rank) in enumerate(awards):
                if i < len(global_leaderboard):
                    entry = global_leaderboard[i]

                    # Check if already awarded
                    existing = SeasonWinner.query.filter_by(
                        season_id=season_id,
                        user_id=entry["user_id"],
                        group_id=None,
                        award_type=award_type,
                    ).first()

                    if not existing:
                        winner = SeasonWinner(
                            season_id=season_id,
                            user_id=entry["user_id"],
                            group_id=None,
                            award_type=award_type,
                            rank=rank,
                            total_wins=entry["wins"],
                            total_points=entry["wins"],  # Points = wins for now
                            tiebreaker_points=entry.get("tiebreaker_points", 0),
                            accuracy=entry.get("accuracy", 0.0),
                        )
                        db.session.add(winner)
                        results["global_winners"].append(winner)

        # Award group winners
        groups = Group.query.filter_by(is_active=True).all()
        for group in groups:
            group_leaderboard = group.get_leaderboard(season_id)

            if group_leaderboard:
                # Champion only for groups
                if len(group_leaderboard) > 0:
                    entry = group_leaderboard[0]

                    existing = SeasonWinner.query.filter_by(
                        season_id=season_id,
                        user_id=entry["user"].id,
                        group_id=group.id,
                        award_type="champion",
                    ).first()

                    if not existing:
                        winner = SeasonWinner(
                            season_id=season_id,
                            user_id=entry["user"].id,
                            group_id=group.id,
                            award_type="champion",
                            rank=1,
                            total_wins=entry["wins"],
                            total_points=entry.get("total_points", entry["wins"]),
                            tiebreaker_points=entry.get("tiebreaker_points", 0),
                            accuracy=entry.get("accuracy", 0.0),
                        )
                        db.session.add(winner)

                        if group.id not in results["group_winners"]:
                            results["group_winners"][group.id] = []
                        results["group_winners"][group.id].append(winner)

        db.session.commit()
        return results

    @staticmethod
    def get_user_awards(user_id):
        """Get all awards for a user"""
        return (
            SeasonWinner.query.filter_by(user_id=user_id)
            .order_by(SeasonWinner.season_id.desc(), SeasonWinner.rank.asc())
            .all()
        )

    @staticmethod
    def get_season_awards(season_id, group_id=None):
        """Get all awards for a season"""
        query = SeasonWinner.query.filter_by(season_id=season_id)

        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter(SeasonWinner.group_id.is_(None))

        return query.order_by(SeasonWinner.rank.asc()).all()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "season_id": self.season_id,
            "user_id": self.user_id,
            "user": self.user.to_dict() if self.user else None,
            "group_id": self.group_id,
            "award_type": self.award_type,
            "rank": self.rank,
            "total_wins": self.total_wins,
            "total_points": self.total_points,
            "tiebreaker_points": self.tiebreaker_points,
            "accuracy": self.accuracy,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
