from datetime import datetime, timezone

from app import db


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)

    # Game identification
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False)
    week = db.Column(db.Integer, nullable=False)

    # Teams
    home_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    away_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)

    # Game timing
    game_time = db.Column(db.DateTime, nullable=False)

    # Scores
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)

    # Game status
    is_final = db.Column(db.Boolean, default=False)
    is_overtime = db.Column(db.Boolean, default=False)

    # External IDs for API integration
    espn_id = db.Column(db.String(50), unique=True, index=True)
    nfl_id = db.Column(db.String(50), unique=True, index=True)

    # Additional game info
    spread = db.Column(db.Float)  # Point spread (positive = home team favored)
    over_under = db.Column(db.Float)  # Total points over/under

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    picks = db.relationship(
        "Pick", backref="game", lazy="dynamic", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        db.Index("idx_game_season_week", "season_id", "week"),
        db.Index("idx_game_time", "game_time"),
        db.CheckConstraint("home_team_id != away_team_id", name="different_teams"),
    )

    def __repr__(self):
        return f'<Game {self.away_team.abbreviation if self.away_team else "TBD"} @ {self.home_team.abbreviation if self.home_team else "TBD"} Week {self.week}>'

    @property
    def winning_team(self):
        """Get the winning team (None if game not final or tie)"""
        if not self.is_final or self.home_score == self.away_score:
            return None

        if self.home_score > self.away_score:
            return self.home_team
        else:
            return self.away_team

    @property
    def losing_team(self):
        """Get the losing team (None if game not final or tie)"""
        if not self.is_final or self.home_score == self.away_score:
            return None

        if self.home_score < self.away_score:
            return self.home_team
        else:
            return self.away_team

    @property
    def margin_of_victory(self):
        """Get margin of victory (None if game not final)"""
        if not self.is_final:
            return None

        return abs(self.home_score - self.away_score)

    @property
    def total_score(self):
        """Get total combined score"""
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score + self.away_score

    @property
    def is_tie(self):
        """Check if game ended in a tie"""
        return self.is_final and self.home_score == self.away_score

    @property
    def status(self):
        """Get game status as string"""
        if self.is_final:
            return "completed"

        # Handle timezone comparison properly
        now_utc = datetime.now(timezone.utc)
        game_time = self.game_time

        # If game_time is timezone-naive, assume it's in UTC
        if game_time and game_time.tzinfo is None:
            game_time = game_time.replace(tzinfo=timezone.utc)

        if game_time and game_time <= now_utc and not self.is_final:
            # Game has started but not finished
            return "in_progress"
        else:
            # Game hasn't started yet
            return "scheduled"

    @property
    def local_game_time(self):
        """Get game time in the application's timezone"""
        # Lazy import to avoid circular imports
        from app.utils.timezone_utils import convert_to_app_timezone

        return convert_to_app_timezone(self.game_time)

    def format_game_time_local(self, format_str="%a %m/%d at %I:%M %p"):
        """Format game time in the application's timezone"""
        # Lazy import to avoid circular imports
        from app.utils.timezone_utils import format_game_time

        return format_game_time(self.game_time, format_str)

    def get_team_score(self, team_id):
        """Get score for a specific team"""
        if team_id == self.home_team_id:
            return self.home_score
        elif team_id == self.away_team_id:
            return self.away_score
        return None

    def get_opponent(self, team_id):
        """Get opponent team for a given team"""
        if team_id == self.home_team_id:
            return self.away_team
        elif team_id == self.away_team_id:
            return self.home_team
        return None

    def is_team_winner(self, team_id):
        """Check if a team won this game"""
        if not self.is_final:
            return None

        winning_team = self.winning_team
        return winning_team and winning_team.id == team_id

    def update_score(self, home_score, away_score, is_final=False):
        """Update game score"""
        self.home_score = home_score
        self.away_score = away_score
        self.is_final = is_final

        if is_final:
            # Update all related picks
            # NOTE: picks is lazy="dynamic", so we need .all() to get actual list
            for pick in self.picks.all():
                pick.update_result()

    def get_picks_count(self):
        """Get count of picks for each team"""
        home_picks = self.picks.filter_by(selected_team_id=self.home_team_id).count()
        away_picks = self.picks.filter_by(selected_team_id=self.away_team_id).count()

        return {
            "home_team": home_picks,
            "away_team": away_picks,
            "total": home_picks + away_picks,
        }

    @staticmethod
    def get_games_for_week(season_id, week):
        """Get all games for a specific week with eager loading"""
        from sqlalchemy.orm import joinedload

        return (
            Game.query.filter_by(season_id=season_id, week=week)
            .options(joinedload(Game.home_team), joinedload(Game.away_team))
            .order_by(Game.game_time)
            .all()
        )

    @staticmethod
    def get_current_week_games(season_id):
        """Get games for current week"""
        from .season import Season

        season = Season.query.get(season_id)
        if season:
            current_week = season.update_current_week()
            return Game.get_games_for_week(season_id, current_week)
        return []

    def has_started(self):
        """Check if game has started"""
        if not self.game_time:
            return False
        # Handle timezone comparison properly
        now_utc = datetime.now(timezone.utc)
        game_time = self.game_time

        # If game_time is timezone-naive, assume it's in UTC
        if game_time.tzinfo is None:
            game_time = game_time.replace(tzinfo=timezone.utc)

        return now_utc >= game_time

    def is_pickable(self):
        """Check if game is available for picks (hasn't started yet)"""
        return not self.has_started() and not self.is_final

    def to_dict(self, include_picks_count=False):
        """Convert game to dictionary for API responses"""
        data = {
            "id": self.id,
            "season_id": self.season_id,
            "week": self.week,
            "game_time": self.game_time.isoformat() if self.game_time else None,
            "home_team": self.home_team.to_dict() if self.home_team else None,
            "away_team": self.away_team.to_dict() if self.away_team else None,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "is_final": self.is_final,
            "is_overtime": self.is_overtime,
            "spread": self.spread,
            "over_under": self.over_under,
            "margin_of_victory": self.margin_of_victory,
            "winning_team_id": self.winning_team.id if self.winning_team else None,
            "is_pickable": self.is_pickable(),
            "status": self.status,
        }

        if include_picks_count:
            data["picks_count"] = self.get_picks_count()

        return data
