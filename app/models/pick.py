import logging
from datetime import UTC, datetime

from app import db

logger = logging.getLogger(__name__)


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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
        from .season import Season

        # Check playoff eligibility (top N from regular season, N per group rules)
        season = Season.query.get(self.season_id)
        if season and season.is_playoff_week(self.game.week):
            is_eligible, message = self.user.is_playoff_eligible(
                self.season_id,
                self.group_id
            )

            if not is_eligible:
                return False, message

            # Super Bowl restriction (final week): only the top N playoff
            # players may pick. Each qualifier picks any team freely - there is
            # no opposing-teams constraint.
            superbowl_week = season.regular_season_weeks + season.playoff_weeks
            if self.game.week == superbowl_week:
                is_sb_eligible, sb_message = self.user.is_superbowl_eligible_from_snapshot(
                    self.season_id,
                    self.group_id
                )

                if not is_sb_eligible:
                    return False, sb_message

        # EXISTING: One pick per game week validation
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
        """Validate team-based rules by delegating to User.can_pick_team()"""
        # Delegate to User.can_pick_team() to avoid duplicate validation logic
        can_pick, reason = self.user.can_pick_team(
            team_id=self.selected_team_id,
            week=self.game.week,
            season_id=self.season_id,
            group_id=self.group_id,
            exclude_pick_id=self.id,  # Exclude this pick when checking (for updates)
            game=self.game,
        )

        if not can_pick:
            # Make error messages more specific with team abbreviation if available
            if "already used" in reason.lower():
                team_abbr = self.selected_team.abbreviation if self.selected_team else f"Team {self.selected_team_id}"
                return False, f"{team_abbr} already used this season"
            else:
                return False, reason

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

            # Calculate points using scoring function
            from app.utils.scoring import calculate_pick_score
            self.points_earned = calculate_pick_score(self)

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

        # Calculate points
        from app.utils.scoring import calculate_pick_score

        margin = self.game.margin_of_victory or 0

        if self.is_correct:
            # Calculate points for correct pick
            self.points_earned = calculate_pick_score(self)
            # Tiebreaker: add margin of victory
            self.tiebreaker_points = float(margin)
        else:
            # No points for loss
            self.points_earned = 0.0
            # Tiebreaker: subtract margin of loss
            self.tiebreaker_points = float(-margin)

    @classmethod
    def recalculate_for_game(cls, game_id, commit=True):
        """
        Recalculate all picks for a specific game.

        This is the SAFE way to update picks after a game is finalized.
        Separates score updates from pick calculations to avoid transaction boundary issues.

        Args:
            game_id: ID of the game to recalculate picks for
            commit: Whether to commit after recalculation (default: True)

        Returns:
            tuple: (updated_count, game_week) or (0, None) if game not found
        """
        from app.models.game import Game
        from app.utils.cache_utils import invalidate_model_cache

        game = db.session.get(Game, game_id)
        if not game:
            logger.warning(f"Game {game_id} not found for pick recalculation")
            return 0, None
            
        if not game.is_final:
            logger.info(f"Game {game_id} not final yet, skipping pick recalculation")
            return 0, game.week
        
        # Get all picks for this game
        picks = cls.query.filter_by(game_id=game_id).all()
        
        if not picks:
            logger.debug(f"No picks found for game {game_id}")
            return 0, game.week
        
        updated = 0
        for pick in picks:
            old_correct = pick.is_correct
            old_points = pick.points_earned
            
            # Recalculate pick result
            pick.update_result()
            
            # Track if anything changed
            if old_correct != pick.is_correct or old_points != pick.points_earned:
                updated += 1
                logger.debug(
                    f"Pick {pick.id} updated: is_correct {old_correct} -> {pick.is_correct}, "
                    f"points {old_points} -> {pick.points_earned}"
                )
        
        if commit:
            db.session.commit()
            invalidate_model_cache('Pick')
            invalidate_model_cache('Game')
            db.session.expire_all()
            
        logger.info(
            f"Recalculated {updated}/{len(picks)} picks for game {game_id} (week {game.week})"
        )
        
        return updated, game.week

    @staticmethod
    def create_pick(user_id, game_id, selected_team_id, group_id=None):
        """Create a new pick with validation - handles switching picks automatically

        Args:
            user_id: User making the pick
            game_id: Game being picked
            selected_team_id: Team being picked
            group_id: Group context for the pick (None for global picks). Must
                already reflect the user's picks_are_global setting.
        """
        from .game import Game
        from .season import Season
        from .user import User

        game = Game.query.get(game_id)
        if not game:
            return None, "Game not found"

        user = User.query.get(user_id)
        if not user:
            return None, "User not found"

        # The game must still be open. This check has to happen here and not
        # only in the caller: without it a pick can be created on a game that
        # has kicked off - or already finished - and then scored from a result
        # that is already known.
        if game.has_started():
            return None, "Game has already started"

        if game.is_final:
            return None, "Game is already complete"

        # Playoff and Super Bowl eligibility, matching _validate_week_rules().
        # Checked before anything is mutated so a rejected pick leaves the
        # existing one untouched.
        season = Season.query.get(game.season_id)
        if season and season.is_playoff_week(game.week):
            is_eligible, message = user.is_playoff_eligible(game.season_id, group_id)
            if not is_eligible:
                return None, message

            superbowl_week = season.regular_season_weeks + season.playoff_weeks
            if game.week == superbowl_week:
                is_sb_eligible, sb_message = user.is_superbowl_eligible_from_snapshot(
                    game.season_id, group_id
                )
                if not is_sb_eligible:
                    return None, sb_message

        # Check if user already has a pick for this week in this group context
        week_filter = [
            Pick.user_id == user_id,
            Pick.season_id == game.season_id,
            Game.week == game.week,
        ]
        if group_id is not None:
            week_filter.append(Pick.group_id == group_id)
        else:
            week_filter.append(Pick.group_id.is_(None))

        existing_week_pick = Pick.query.join(Game).filter(*week_filter).first()

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
            group_id=group_id,
        )

        # Manually set the relationships since the pick isn't flushed yet
        pick.game = game
        pick.user = user

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
