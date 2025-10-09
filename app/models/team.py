from datetime import datetime, timezone

from app import db


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)

    # Team identification
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    abbreviation = db.Column(db.String(10), nullable=False, index=True)

    # External IDs for API integration
    espn_id = db.Column(db.String(20), unique=True, index=True)
    nfl_id = db.Column(db.String(20), unique=True, index=True)

    # Team details
    conference = db.Column(db.String(10))  # AFC or NFC
    division = db.Column(db.String(20))  # North, South, East, West

    # Visual elements
    primary_color = db.Column(db.String(7))  # Hex color
    secondary_color = db.Column(db.String(7))  # Hex color
    logo_url = db.Column(db.String(500))

    # Season context
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False)

    # Status
    is_active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    # Define bidirectional relationships with Game model
    home_games = db.relationship(
        "Game",
        foreign_keys="Game.home_team_id",
        backref=db.backref("home_team", lazy="joined"),
        lazy="dynamic",
    )
    away_games = db.relationship(
        "Game",
        foreign_keys="Game.away_team_id",
        backref=db.backref("away_team", lazy="joined"),
        lazy="dynamic",
    )

    # Indexes
    __table_args__ = (
        db.Index("idx_team_season_abbr", "season_id", "abbreviation"),
        db.UniqueConstraint(
            "season_id", "abbreviation", name="unique_team_season_abbr"
        ),
    )

    def __repr__(self):
        return f"<Team {self.city} {self.name}>"

    @property
    def full_name(self):
        """Return full team name"""
        return f"{self.city} {self.name}"

    @property
    def short_name(self):
        """Return abbreviated team name"""
        return self.abbreviation

    def get_all_games(self):
        """Get all games for this team (home and away)"""
        from .game import Game

        return (
            Game.query.filter(
                db.or_(Game.home_team_id == self.id, Game.away_team_id == self.id)
            )
            .order_by(Game.game_time)
            .all()
        )

    def get_games_for_week(self, week):
        """Get games for this team in a specific week"""
        from .game import Game

        return Game.query.filter(
            db.or_(Game.home_team_id == self.id, Game.away_team_id == self.id),
            Game.week == week,
        ).first()

    def get_record(self):
        """Get team's win-loss record"""
        games = self.get_all_games()
        wins = 0
        losses = 0

        for game in games:
            if not game.is_final:
                continue

            if game.home_team_id == self.id:
                if game.home_score > game.away_score:
                    wins += 1
                else:
                    losses += 1
            else:
                if game.away_score > game.home_score:
                    wins += 1
                else:
                    losses += 1

        return wins, losses

    def is_opponent_in_week(self, week):
        """Get opponent team for a specific week"""
        game = self.get_games_for_week(week)
        if not game:
            return None

        if game.home_team_id == self.id:
            return game.away_team
        else:
            return game.home_team

    def has_bye_week(self, week):
        """Check if team has a bye week"""
        return self.get_games_for_week(week) is None

    @staticmethod
    def get_by_abbreviation(abbreviation, season_id):
        """Get team by abbreviation for a specific season"""
        return Team.query.filter_by(
            abbreviation=abbreviation.upper(), season_id=season_id
        ).first()

    @staticmethod
    def get_all_for_season(season_id):
        """Get all teams for a specific season"""
        return (
            Team.query.filter_by(season_id=season_id, is_active=True)
            .order_by(Team.city, Team.name)
            .all()
        )

    def to_dict(self):
        """Convert team to dictionary for API responses"""
        wins, losses = self.get_record()
        return {
            "id": self.id,
            "name": self.name,
            "city": self.city,
            "full_name": self.full_name,
            "abbreviation": self.abbreviation,
            "conference": self.conference,
            "division": self.division,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "logo_url": self.logo_url,
            "wins": wins,
            "losses": losses,
            "season_id": self.season_id,
        }
