from datetime import datetime, timezone

from app import db


class Season(db.Model):
    __tablename__ = "seasons"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True, index=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., "2025 NFL Season"

    # Season dates
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    regular_season_weeks = db.Column(db.Integer, default=18)
    playoff_weeks = db.Column(db.Integer, default=4)

    # Status
    is_active = db.Column(db.Boolean, default=False)
    is_complete = db.Column(db.Boolean, default=False)
    current_week = db.Column(db.Integer, default=1)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    games = db.relationship(
        "Game", backref="season", lazy="dynamic", cascade="all, delete-orphan"
    )
    teams = db.relationship("Team", backref="season", lazy="dynamic")

    # Database indexes and constraints
    __table_args__ = (
        db.UniqueConstraint("year", name="unique_season_year"),
        db.Index("idx_season_active", "is_active"),
        db.Index("idx_season_year", "year"),
        db.Index("idx_season_dates", "start_date", "end_date"),
    )

    def __repr__(self):
        return f"<Season {self.year}>"

    @staticmethod
    def get_current_season():
        """Get the currently active season"""
        return Season.query.filter_by(is_active=True).first()

    @staticmethod
    def create_season(year, start_date, end_date):
        """Create a new season"""
        season = Season(
            year=year,
            name=f"{year} NFL Season",
            start_date=start_date,
            end_date=end_date,
        )
        db.session.add(season)
        return season

    def activate(self):
        """Activate this season (deactivates all others)"""
        # Deactivate all other seasons
        Season.query.update({"is_active": False})
        self.is_active = True
        db.session.commit()

    def get_weeks(self):
        """Get list of all weeks in the season"""
        weeks = []

        # Regular season weeks
        for week in range(1, self.regular_season_weeks + 1):
            weeks.append({"week": week, "type": "regular", "name": f"Week {week}"})

        # Playoff weeks
        playoff_names = [
            "Wild Card",
            "Divisional",
            "Conference Championship",
            "Super Bowl",
        ]
        for i in range(self.playoff_weeks):
            week_num = self.regular_season_weeks + i + 1
            weeks.append(
                {
                    "week": week_num,
                    "type": "playoff",
                    "name": (
                        playoff_names[i]
                        if i < len(playoff_names)
                        else f"Playoff Week {i + 1}"
                    ),
                }
            )

        return weeks

    def get_games_for_week(self, week):
        """Get all games for a specific week"""
        return self.games.filter_by(week=week).order_by("game_time").all()

    def is_playoff_week(self, week):
        """Check if a week is a playoff week"""
        return week > self.regular_season_weeks

    def get_completed_weeks(self):
        """Get list of completed weeks"""
        completed_weeks = []
        for week in range(1, self.current_week):
            if self.games.filter_by(week=week, is_final=True).count() > 0:
                completed_weeks.append(week)
        return completed_weeks

    def advance_week(self):
        """Advance to the next week"""
        max_week = self.regular_season_weeks + self.playoff_weeks
        if self.current_week < max_week:
            self.current_week += 1

            # Check if season is complete
            if self.current_week > max_week:
                self.finalize_season()

    def finalize_season(self):
        """Mark season as complete and award winners"""
        if self.is_complete:
            return  # Already finalized

        self.is_complete = True
        self.is_active = False

        # Award winners
        from .season_winner import SeasonWinner

        results = SeasonWinner.award_season_winners(self.id)

        # Send notifications
        self._send_season_end_notifications(results)

        db.session.commit()

        return results

    def _send_season_end_notifications(self, results):
        """Send notifications to winners"""
        from app.socketio_handlers import notify_user

        # Notify global winners
        for winner in results.get("global_winners", []):
            message = (
                f"🏆 Congratulations! You finished #{winner.rank} in the {self.name}!"
            )
            notify_user(
                winner.user_id,
                "season_complete",
                message,
                {
                    "season_id": self.id,
                    "award_type": winner.award_type,
                    "rank": winner.rank,
                },
            )

        # Notify group winners
        for group_id, winners in results.get("group_winners", {}).items():
            for winner in winners:
                from .group import Group

                group = Group.query.get(group_id)
                message = (
                    f"🏆 Congratulations! You won {group.name} in the {self.name}!"
                )
                notify_user(
                    winner.user_id,
                    "group_champion",
                    message,
                    {
                        "season_id": self.id,
                        "group_id": group_id,
                        "group_name": group.name,
                    },
                )

    def check_super_bowl_complete(self):
        """Check if Super Bowl is complete and finalize season if so"""
        from .game import Game

        # Week 22 is Super Bowl
        super_bowl_week = self.regular_season_weeks + self.playoff_weeks

        super_bowl_games = Game.query.filter_by(
            season_id=self.id, week=super_bowl_week
        ).all()

        if super_bowl_games:
            all_final = all(game.is_final for game in super_bowl_games)
            if all_final and not self.is_complete:
                return self.finalize_season()

        return None

    def get_current_week_auto(self):
        """Automatically determine current week based on game schedule and current date"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        # Get all games for this season, ordered by week and game time
        all_games = self.games.order_by("week", "game_time").all()

        if not all_games:
            return 1

        # Find the current week based on games
        for week_num in range(1, self.regular_season_weeks + self.playoff_weeks + 1):
            week_games = [game for game in all_games if game.week == week_num]
            if not week_games:
                continue

            # Get the first and last game of this week
            first_game_of_week = min(week_games, key=lambda g: g.game_time)
            last_game_of_week = max(week_games, key=lambda g: g.game_time)

            # Ensure game times are timezone-aware for comparison
            first_game_time = first_game_of_week.game_time
            if first_game_time.tzinfo is None:
                first_game_time = first_game_time.replace(tzinfo=timezone.utc)

            last_game_time = last_game_of_week.game_time
            if last_game_time.tzinfo is None:
                last_game_time = last_game_time.replace(tzinfo=timezone.utc)

            # If we haven't reached the first game of this week yet,
            # but we're within 3 days, consider it current week for pick making
            from datetime import timedelta

            if now < first_game_time:
                time_until_week = first_game_time - now
                if time_until_week <= timedelta(days=3):
                    return week_num
                # Otherwise, continue to check if previous week is still current
                continue

            # If we're after the first game but before the last game finishes,
            # or if this week is still in progress (some games finished, some not)
            if now <= last_game_time:
                return week_num

            # Check if this week has unfinished games
            games_finished = sum(1 for game in week_games if game.is_final)
            if games_finished < len(week_games):
                return week_num

        # If we're here, we might be past all games, return the last week with games
        if all_games:
            last_week = max(game.week for game in all_games)
            return last_week

        return 1

    def update_current_week(self):
        """Update the current_week field based on actual game schedule"""
        calculated_week = self.get_current_week_auto()
        if calculated_week != self.current_week:
            self.current_week = calculated_week
            from app import db

            db.session.commit()
        return self.current_week

    def to_dict(self):
        """Convert season to dictionary for API responses"""
        return {
            "id": self.id,
            "year": self.year,
            "name": self.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "is_complete": self.is_complete,
            "current_week": self.current_week,
            "regular_season_weeks": self.regular_season_weeks,
            "playoff_weeks": self.playoff_weeks,
        }
