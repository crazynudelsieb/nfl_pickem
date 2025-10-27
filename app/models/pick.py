from datetime import datetime, timezone

from app import db


class Pick(db.Model):
    __tablename__ = "picks"

    id = db.Column(db.Integer, primary_key=True)

    # Pick identification
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False)
    group_id = db.Column(
        db.Integer, db.ForeignKey("groups.id"), nullable=True
    )  # Nullable for global picks

    # Pick details
    selected_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)

    # Results (calculated after game completion)
    is_correct = db.Column(db.Boolean)
    points_earned = db.Column(db.Float, default=0.0)
    tiebreaker_points = db.Column(
        db.Float, default=0.0
    )  # Point differential for tiebreaking (half for ties)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    selected_team = db.relationship("Team", foreign_keys=[selected_team_id])
    season = db.relationship("Season", foreign_keys=[season_id])
    group = db.relationship("Group", foreign_keys=[group_id])

    # Constraints and indexes
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "game_id", "group_id", name="unique_user_game_group_pick"
        ),
        db.Index("idx_pick_user_season", "user_id", "season_id"),
        db.Index("idx_pick_game", "game_id"),
        db.Index("idx_pick_group", "group_id"),
    )

    def __repr__(self):
        return f'<Pick user_id={self.user_id} game_id={self.game_id} team={self.selected_team.abbreviation if self.selected_team else "TBD"}>'

    @property
    def week(self):
        """Get the week number from the associated game"""
        return self.game.week if self.game else None

    def is_valid_pick(self):
        """Validate pick according to NEW GAME RULES"""
        # Ensure we have a game loaded
        if not self.game:
            # Try to load the game if we have a game_id
            if self.game_id:
                from .game import Game

                self.game = Game.query.get(self.game_id)
            if not self.game:
                return False, "Game not found"

        # Check basic game conditions
        basic_valid, basic_message = self._validate_basic_conditions()
        if not basic_valid:
            return False, basic_message

        # Check week-level rules
        week_valid, week_message = self._validate_week_rules()
        if not week_valid:
            return False, week_message

        # Check team-level rules
        team_valid, team_message = self._validate_team_rules()
        if not team_valid:
            return False, team_message

        return True, "Valid pick"

    def _validate_basic_conditions(self):
        """Validate basic game conditions"""
        if self.game.has_started():
            return False, "Game has already started"

        if self.game.is_final:
            return False, "Game is already complete"

        return True, "Basic conditions valid"

    def _validate_week_rules(self):
        """Validate week-level rules"""
        from .game import Game

        # RULE 1: One pick per game week - can switch as long as current pick hasn't started
        # Build filter that respects group context
        week_filter = [
            Pick.user_id == self.user_id,
            Pick.season_id == self.season_id,
            Game.week == self.game.week,
            Pick.id != self.id,  # Exclude current pick when updating
        ]

        # Filter by group_id to respect per-group vs global picks
        # If this pick has a group_id, only check within that group
        # If this pick has no group_id (global), only check global picks
        if self.group_id is not None:
            week_filter.append(Pick.group_id == self.group_id)
        else:
            week_filter.append(Pick.group_id.is_(None))

        existing_week_pick = (
            Pick.query.join(Game)
            .filter(*week_filter)
            .first()
        )

        if existing_week_pick:
            # Check if the existing pick's game has started
            if existing_week_pick.game.has_started():
                return (
                    False,
                    f"Cannot switch pick: Your current pick ({existing_week_pick.game.away_team.abbreviation} vs {existing_week_pick.game.home_team.abbreviation}) has already started",
                )

        return True, "Week rules valid"

    def _validate_team_rules(self):
        """Validate team-based rules"""
        from .game import Game
        from .season import Season

        # Get season info
        season = Season.query.get(self.season_id)
        if not season:
            return False, "Invalid season"

        # Build base filter that respects group context
        # If this pick has a group_id, only check within that group
        # If this pick has no group_id (global), only check global picks
        base_filter = [
            Pick.user_id == self.user_id,
            Pick.season_id == self.season_id,
            Pick.id != self.id,
        ]

        if self.group_id is not None:
            base_filter.append(Pick.group_id == self.group_id)
        else:
            base_filter.append(Pick.group_id.is_(None))

        # RULE 2: One pick per team per season (except playoffs, super bowl, and special games)
        is_special_game = season.is_playoff_week(self.game.week)

        if not is_special_game:
            team_filter = base_filter + [
                Pick.selected_team_id == self.selected_team_id,
                Game.week < self.game.week,
            ]

            previous_team_pick = (
                Pick.query.join(Game)
                .filter(*team_filter)
                .first()
            )

            if previous_team_pick:
                return (
                    False,
                    f"Team {self.selected_team.abbreviation} already used in game week {previous_team_pick.game.week}",
                )

        # RULE 3: Loser can't be picked twice in a row (must have a game week between)
        # This rule only applies to regular season, not playoffs
        if self.game.week > 1 and not is_special_game:
            prev_week_filter = base_filter + [Game.week == self.game.week - 1]

            previous_week_pick = (
                Pick.query.join(Game)
                .filter(*prev_week_filter)
                .first()
            )

            if (
                previous_week_pick
                and previous_week_pick.is_correct is False
                and previous_week_pick.selected_team_id == self.selected_team_id
            ):
                return (
                    False,
                    f"Cannot use {self.selected_team.abbreviation} - they lost last game week. Must have a game week between using losing teams.",
                )

        return True, "Team rules valid"

    def update_result(self):
        """Update pick result after game completion"""
        # Null check for game relationship
        if not self.game:
            return

        if not self.game.is_final:
            return

        # Check if game is a tie
        if self.game.is_tie:
            # Tie game: award 0.5 points, but no tiebreaker (no score differential)
            self.is_correct = None  # Neither correct nor incorrect

            # Calculate points using ScoringEngine (handles playoff multipliers for ties)
            from app.utils.scoring import ScoringEngine
            scoring = ScoringEngine()
            self.points_earned = scoring.calculate_pick_score(self)

            # No tiebreaker points for ties (no point differential)
            self.tiebreaker_points = 0
            return

        # Determine if pick is correct (win/loss)
        winning_team = self.game.winning_team
        if winning_team:
            self.is_correct = self.selected_team_id == winning_team.id
        else:
            # Should not reach here if is_tie check above works
            self.is_correct = False

        # Calculate points using ScoringEngine to apply playoff multipliers
        from app.utils.scoring import ScoringEngine

        scoring = ScoringEngine()

        margin = self.game.margin_of_victory or 0

        if self.is_correct:
            # Use scoring engine to calculate points (handles playoff multipliers)
            self.points_earned = scoring.calculate_pick_score(self)
            # Tiebreaker: add margin of victory
            self.tiebreaker_points = float(margin)
        else:
            # No points for loss
            self.points_earned = 0.0
            # Tiebreaker: subtract margin of loss
            self.tiebreaker_points = float(-margin)

    def get_user_season_picks(self):
        """Get all picks by this user for this season"""
        from .game import Game

        return (
            Pick.query.filter_by(user_id=self.user_id, season_id=self.season_id)
            .join(Game)
            .order_by(Game.week)
            .all()
        )

    def get_used_teams(self):
        """Get list of teams already used by this user this season"""
        picks = self.get_user_season_picks()
        return [pick.selected_team for pick in picks if pick.id != self.id]

    def get_available_teams_for_week(self, week):
        """Get teams available for selection in a specific week"""
        from .season import Season
        from .team import Team

        season = Season.query.get(self.season_id)
        if not season:
            return []

        # Get all teams for the season
        all_teams = Team.get_all_for_season(self.season_id)

        # If playoff week, all teams are available
        if season.is_playoff_week(week):
            # Filter to teams that are actually playing this week
            from .game import Game

            games = Game.query.filter_by(season_id=self.season_id, week=week).all()
            playing_teams = []
            for game in games:
                playing_teams.extend([game.home_team, game.away_team])
            return playing_teams

        # For regular season, exclude already used teams
        used_teams = self.get_used_teams()
        used_team_ids = [team.id for team in used_teams]

        available_teams = [team for team in all_teams if team.id not in used_team_ids]

        # Also check losing team restriction
        if week > 1:
            from .game import Game

            previous_week_pick = (
                Pick.query.join(Game)
                .filter(
                    Pick.user_id == self.user_id,
                    Pick.season_id == self.season_id,
                    Game.week == week - 1,
                )
                .first()
            )

            if previous_week_pick and previous_week_pick.is_correct is False:
                available_teams = [
                    team
                    for team in available_teams
                    if team.id != previous_week_pick.selected_team_id
                ]

        # Filter to teams playing this week
        from .game import Game

        games = Game.query.filter_by(season_id=self.season_id, week=week).all()
        playing_team_ids = []
        for game in games:
            playing_team_ids.extend([game.home_team_id, game.away_team_id])

        available_teams = [
            team for team in available_teams if team.id in playing_team_ids
        ]

        return available_teams

    @staticmethod
    def create_pick(user_id, game_id, selected_team_id):
        """Create a new pick with validation - handles switching picks automatically"""
        from .game import Game

        game = Game.query.get(game_id)
        if not game:
            return None, "Game not found"

        # Check if user already has a pick for this week
        existing_week_pick = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == user_id,
                Pick.season_id == game.season_id,
                Game.week == game.week,
            )
            .first()
        )

        if existing_week_pick:
            # If trying to pick the same game, just update the team selection
            if existing_week_pick.game_id == game_id:
                if existing_week_pick.game.has_started():
                    return None, "Cannot change pick: Game has already started"
                existing_week_pick.selected_team_id = selected_team_id
                return existing_week_pick, "Pick updated successfully"

            # If switching to a different game, check if current pick's game has started
            if existing_week_pick.game.has_started():
                return (
                    None,
                    f"Cannot switch pick: Your current pick ({existing_week_pick.game.away_team.abbreviation} vs {existing_week_pick.game.home_team.abbreviation}) has already started",
                )

            # Delete the existing pick to allow switching
            db.session.delete(existing_week_pick)
            db.session.flush()  # Ensure deletion happens before creating new pick

        # Create new pick
        pick = Pick(
            user_id=user_id,
            game_id=game_id,
            season_id=game.season_id,
            selected_team_id=selected_team_id,
        )

        # Manually set the game relationship since it's not loaded yet
        pick.game = game

        # Validate the new pick (but skip the week check since we handled it above)
        is_valid, message = pick._validate_team_rules()
        if not is_valid:
            return None, message

        db.session.add(pick)
        return pick, "Pick created successfully"

    def to_dict(self):
        """Convert pick to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "game_id": self.game_id,
            "season_id": self.season_id,
            "week": self.week,
            "selected_team": (
                self.selected_team.to_dict() if self.selected_team else None
            ),
            "is_correct": self.is_correct,
            "points_earned": self.points_earned,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "game": self.game.to_dict() if self.game else None,
        }
