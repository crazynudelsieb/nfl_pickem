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
        """Award winners for a completed season
        
        For seasons with Super Bowl:
        - Rank 1 (Champion): Winner of Super Bowl (among top 2 eligible)
        - Rank 2 (Runner-up): Loser of Super Bowl (among top 2 eligible)
        - Rank 3 (Third place): Best of remaining users
        
        For seasons without Super Bowl:
        - Use full season leaderboard
        """
        from app.models import Group, User, Game, Pick
        from app.models.regular_season_snapshot import RegularSeasonSnapshot

        results = {"global_winners": [], "group_winners": {}}

        # Check if Super Bowl exists and is complete
        from app.models.season import Season
        season = Season.query.get(season_id)
        super_bowl_week = season.regular_season_weeks + season.playoff_weeks
        super_bowl_game = Game.query.filter_by(
            season_id=season_id, week=super_bowl_week
        ).first()

        # Determine if we should use Super Bowl results
        use_super_bowl = (
            super_bowl_game 
            and super_bowl_game.is_final
            and RegularSeasonSnapshot.query.filter_by(
                season_id=season_id,
                group_id=None,
                is_superbowl_eligible=True
            ).count() > 0
        )

        if use_super_bowl:
            # Super Bowl-based ranking
            # Get Super Bowl eligible users (top 2)
            sb_eligible = RegularSeasonSnapshot.query.filter_by(
                season_id=season_id,
                group_id=None,
                is_superbowl_eligible=True
            ).order_by(RegularSeasonSnapshot.final_rank).all()

            # Get their Super Bowl picks
            sb_picks = Pick.query.filter_by(game_id=super_bowl_game.id).all()
            pick_map = {p.user_id: p for p in sb_picks}

            # Rank by Super Bowl result
            sb_ranked = []
            for eligible in sb_eligible:
                pick = pick_map.get(eligible.user_id)
                if pick:
                    # Winner first, loser second
                    sb_ranked.append((eligible.user_id, pick.is_correct, eligible))

            # Sort: True (winner) first, then False (loser)
            sb_ranked.sort(key=lambda x: (not x[1] if x[1] is not None else True, x[2].final_rank))

            # Award top 2 (Super Bowl participants)
            awards = [("champion", 1), ("runner_up", 2)]
            for i, (award_type, rank) in enumerate(awards):
                if i < len(sb_ranked):
                    user_id, won_sb, snapshot = sb_ranked[i]
                    
                    existing = SeasonWinner.query.filter_by(
                        season_id=season_id,
                        user_id=user_id,
                        group_id=None,
                        award_type=award_type,
                    ).first()

                    if not existing:
                        # Get full season stats
                        stats = User.query.get(user_id).get_season_stats(season_id)
                        
                        winner = SeasonWinner(
                            season_id=season_id,
                            user_id=user_id,
                            group_id=None,
                            award_type=award_type,
                            rank=rank,
                            total_wins=stats["wins"],
                            total_points=int(stats["total_score"]),
                            tiebreaker_points=int(stats["tiebreaker"]),
                            accuracy=stats.get("accuracy", 0.0),
                        )
                        db.session.add(winner)
                        results["global_winners"].append(winner)

            # Award third place from regular season leaderboard (excluding SB participants)
            sb_user_ids = {r[0] for r in sb_ranked}
            global_leaderboard = User.get_season_leaderboard(
                season_id, regular_season_only=True, group_id=None
            )
            
            # Find best user not in Super Bowl
            for entry in global_leaderboard:
                if entry["user_id"] not in sb_user_ids:
                    existing = SeasonWinner.query.filter_by(
                        season_id=season_id,
                        user_id=entry["user_id"],
                        group_id=None,
                        award_type="third_place",
                    ).first()

                    if not existing:
                        winner = SeasonWinner(
                            season_id=season_id,
                            user_id=entry["user_id"],
                            group_id=None,
                            award_type="third_place",
                            rank=3,
                            total_wins=entry["wins"],
                            total_points=int(entry.get("total_score", entry["wins"])),
                            tiebreaker_points=int(entry.get("tiebreaker_points", 0)),
                            accuracy=entry.get("accuracy", 0.0),
                        )
                        db.session.add(winner)
                        results["global_winners"].append(winner)
                    break

        else:
            # No Super Bowl or not complete - use full season leaderboard
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
                                total_points=int(entry.get("total_score", entry["wins"])),
                                tiebreaker_points=int(entry.get("tiebreaker_points", 0)),
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
