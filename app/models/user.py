import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Profile information
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    display_name = db.Column(db.String(100))
    avatar_url = db.Column(db.String(500))  # Avatar URL from DiceBear API

    # Account status
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)  # Site-wide admin privileges

    # Pick preferences
    picks_are_global = db.Column(
        db.Boolean, default=False
    )  # False = separate picks per group (default)

    # Password reset
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login = db.Column(db.DateTime)

    # Relationships
    picks = db.relationship(
        "Pick", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    group_memberships = db.relationship(
        "GroupMember", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    created_groups = db.relationship("Group", backref="creator", lazy="dynamic")
    sent_invites = db.relationship(
        "Invite", foreign_keys="Invite.inviter_id", backref="inviter", lazy="dynamic"
    )
    received_invites = db.relationship(
        "Invite",
        foreign_keys="Invite.invitee_email",
        backref="invitee",
        lazy="dynamic",
        primaryjoin="User.email == Invite.invitee_email",
    )

    # Database indexes and constraints
    __table_args__ = (
        db.Index("idx_user_last_login", "last_login"),
        db.Index("idx_user_created_at", "created_at"),
        db.Index("idx_user_active_status", "is_active"),
    )

    def __repr__(self):
        return f"<User {self.username}>"

    @staticmethod
    def generate_avatar_url(seed=None):
        """Generate a random avatar URL using DiceBear API"""
        import random

        if seed is None:
            seed = secrets.token_urlsafe(16)

        # Using DiceBear's avataaars style (diverse, colorful avatars)
        # Other styles: bottts, identicon, initials, pixel-art, lorelei, notionists, adventurer
        styles = [
            "avataaars",
            "bottts",
            "pixel-art",
            "lorelei",
            "notionists",
            "adventurer",
        ]
        style = random.choice(styles)

        return f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)

    def set_display_name(self, display_name):
        """Set display name with sanitization"""
        import html

        if display_name:
            self.display_name = html.escape(display_name.strip())
        else:
            self.display_name = display_name

    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    def generate_reset_token(self):
        """Generate a password reset token"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        return self.reset_token

    @staticmethod
    def verify_reset_token(token):
        """Verify reset token and return user if valid"""
        user = User.query.filter_by(reset_token=token).first()
        if (
            user
            and user.reset_token_expiry
        ):
            # Ensure both datetimes are timezone-aware for comparison
            expiry = user.reset_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            
            if expiry > datetime.now(timezone.utc):
                return user
        return None

    def clear_reset_token(self):
        """Clear reset token after use"""
        self.reset_token = None
        self.reset_token_expiry = None

    @property
    def full_name(self):
        """Return display name or username"""
        return self.display_name or self.username

    def get_groups(self):
        """Get all groups this user is a member of (excludes inactive groups unless user is creator)"""
        from .group_member import GroupMember

        group_memberships = (
            db.session.query(GroupMember)
            .filter_by(user_id=self.id, is_active=True)
            .all()
        )

        # Filter groups: include all active groups, plus inactive groups where user is the creator
        groups = []
        for membership in group_memberships:
            group = membership.group
            # Include if group is active OR if user is the creator (so they can re-enable it)
            if group.is_active or group.creator_id == self.id:
                groups.append(group)

        return groups

    def is_member_of_group(self, group_id):
        """Check if user is a member of a specific group"""
        from .group_member import GroupMember

        return (
            GroupMember.query.filter_by(
                user_id=self.id, group_id=group_id, is_active=True
            ).first()
            is not None
        )

    def get_picks_for_season(self, season_id):
        """Get all picks for a specific season"""
        return self.picks.filter_by(season_id=season_id).all()

    def get_pick_for_week(self, season_id, week):
        """Get pick for a specific week"""
        from .game import Game
        from .pick import Pick

        return (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == self.id, Game.season_id == season_id, Game.week == week
            )
            .first()
        )

    def get_pick_for_game(self, game_id):
        """Get pick for a specific game"""
        return self.picks.filter_by(game_id=game_id).first()

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.now(timezone.utc)
        db.session.commit()

    def get_season_stats(self, season_id, group_id=None):
        """Get comprehensive season stats for new rules system

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by (for users with per-group picks)
        """
        from .game import Game
        from .pick import Pick
        from .season import Season

        season = Season.query.get(season_id)
        if not season:
            return None

        # Build filter for picks based on picks_are_global setting
        pick_filter = {"user_id": self.id, "season_id": season_id}

        # For users with per-group picks, filter by group_id
        if not self.picks_are_global and group_id is not None:
            pick_filter["group_id"] = group_id

        # Get all user picks for this season using filtered query
        picks = Pick.query.filter_by(**pick_filter).all()

        # Get all completed games in this season
        completed_games = Game.query.filter(
            Game.season_id == season_id, Game.status == "completed"
        ).all()

        # Separate into regular season and playoff games
        regular_season_completed_games = [
            g for g in completed_games if not season.is_playoff_week(g.week)
        ]
        playoff_completed_games = [
            g for g in completed_games if season.is_playoff_week(g.week)
        ]

        # Create sets of weeks with completed games (for tracking missed picks)
        regular_season_weeks_with_games = set(
            g.week for g in regular_season_completed_games
        )
        playoff_weeks_with_games = set(g.week for g in playoff_completed_games)

        # Separate user picks into regular season and playoff picks
        regular_picks = []
        playoff_picks = []

        for pick in picks:
            if season.is_playoff_week(pick.game.week):
                playoff_picks.append(pick)
            else:
                regular_picks.append(pick)

        # Calculate regular season stats
        regular_completed = [p for p in regular_picks if p.is_correct is not None]
        regular_wins = sum(1 for p in regular_completed if p.is_correct)
        regular_losses = sum(1 for p in regular_completed if not p.is_correct)
        regular_total_tiebreaker = sum(
            p.tiebreaker_points or 0 for p in regular_completed
        )

        # Count missed games in regular season (weeks with completed games but no pick)
        regular_picks_by_week = {p.week for p in regular_picks}
        regular_missed_weeks = regular_season_weeks_with_games - regular_picks_by_week
        regular_missed_games = len(regular_missed_weeks)

        # Accuracy includes missed games as losses
        regular_accuracy_denominator = len(regular_completed) + regular_missed_games
        regular_accuracy = (
            (regular_wins / regular_accuracy_denominator * 100)
            if regular_accuracy_denominator > 0
            else 0
        )

        # Calculate playoff stats
        playoff_completed = [p for p in playoff_picks if p.is_correct is not None]
        playoff_wins = sum(1 for p in playoff_completed if p.is_correct)
        playoff_losses = sum(1 for p in playoff_completed if not p.is_correct)
        playoff_total_tiebreaker = sum(
            p.tiebreaker_points or 0 for p in playoff_completed
        )

        # Count missed games in playoffs
        playoff_picks_by_week = {p.week for p in playoff_picks}
        playoff_missed_weeks = playoff_weeks_with_games - playoff_picks_by_week
        playoff_missed_games = len(playoff_missed_weeks)

        # Accuracy includes missed games as losses
        playoff_accuracy_denominator = len(playoff_completed) + playoff_missed_games
        playoff_accuracy = (
            (playoff_wins / playoff_accuracy_denominator * 100)
            if playoff_accuracy_denominator > 0
            else 0
        )

        # Total stats
        total_wins = regular_wins + playoff_wins
        total_losses = regular_losses + playoff_losses
        total_missed_games = regular_missed_games + playoff_missed_games
        total_tiebreaker = regular_total_tiebreaker + playoff_total_tiebreaker
        total_picks = len(regular_picks) + len(playoff_picks)
        total_completed = len(regular_completed) + len(playoff_completed)

        # Total accuracy includes missed games as losses
        total_accuracy_denominator = total_completed + total_missed_games
        total_accuracy = (
            (total_wins / total_accuracy_denominator * 100)
            if total_accuracy_denominator > 0
            else 0
        )

        # Calculate longest streak for the season
        longest_streak = self._calculate_longest_streak(season_id, group_id)

        return {
            "regular_season": {
                "wins": regular_wins,
                "losses": regular_losses,
                "missed_games": regular_missed_games,
                "total_picks": len(regular_picks),
                "completed_picks": len(regular_completed),
                "tiebreaker_points": regular_total_tiebreaker,
                "accuracy": regular_accuracy,
            },
            "playoffs": {
                "wins": playoff_wins,
                "losses": playoff_losses,
                "missed_games": playoff_missed_games,
                "total_picks": len(playoff_picks),
                "completed_picks": len(playoff_completed),
                "tiebreaker_points": playoff_total_tiebreaker,
                "accuracy": playoff_accuracy,
            },
            "total": {
                "wins": total_wins,
                "losses": total_losses,
                "missed_games": total_missed_games,
                "total_picks": total_picks,
                "completed_picks": total_completed,
                "tiebreaker_points": total_tiebreaker,
                "accuracy": total_accuracy,
                "longest_streak": longest_streak,
            },
        }

    def _calculate_longest_streak(self, season_id, group_id=None):
        """Calculate longest winning or losing streak for a season

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by (for users with per-group picks)

        Returns:
            Longest streak (positive for wins, negative for losses)
        """
        from .game import Game
        from .pick import Pick

        # Build filter for picks based on picks_are_global setting
        pick_filter = {"user_id": self.id, "season_id": season_id}

        # For users with per-group picks, filter by group_id
        if not self.picks_are_global and group_id is not None:
            pick_filter["group_id"] = group_id

        # Get completed picks ordered by week
        picks = (
            Pick.query.filter_by(**pick_filter)
            .join(Game)
            .filter(Pick.is_correct.isnot(None))
            .order_by(Game.week.asc())
            .all()
        )

        if not picks:
            return 0

        # Calculate all streaks and find the longest
        longest_win_streak = 0
        longest_loss_streak = 0
        current_streak = 0
        last_result = None

        for pick in picks:
            if last_result is None or pick.is_correct == last_result:
                # Continue streak
                if pick.is_correct:
                    current_streak += 1
                else:
                    current_streak -= 1
            else:
                # Streak ended, check if it was longest
                if current_streak > 0:
                    longest_win_streak = max(longest_win_streak, current_streak)
                else:
                    longest_loss_streak = min(longest_loss_streak, current_streak)

                # Start new streak
                if pick.is_correct:
                    current_streak = 1
                else:
                    current_streak = -1

            last_result = pick.is_correct

        # Check final streak
        if current_streak > 0:
            longest_win_streak = max(longest_win_streak, current_streak)
        else:
            longest_loss_streak = min(longest_loss_streak, current_streak)

        # Return the streak with largest absolute value
        if abs(longest_win_streak) >= abs(longest_loss_streak):
            return longest_win_streak
        else:
            return longest_loss_streak

    def calculate_alltime_longest_streak(self):
        """Calculate longest winning or losing streak across all seasons

        Returns:
            Longest streak ever (positive for wins, negative for losses)
        """
        from .game import Game
        from .pick import Pick

        # Get all completed picks across all seasons ordered by season and week
        picks = (
            Pick.query.join(Game)
            .filter(Pick.user_id == self.id, Pick.is_correct.isnot(None))
            .order_by(Game.season_id.asc(), Game.week.asc())
            .all()
        )

        if not picks:
            return 0

        # Calculate all streaks and find the longest
        longest_win_streak = 0
        longest_loss_streak = 0
        current_streak = 0
        last_result = None

        for pick in picks:
            if last_result is None or pick.is_correct == last_result:
                # Continue streak
                if pick.is_correct:
                    current_streak += 1
                else:
                    current_streak -= 1
            else:
                # Streak ended, check if it was longest
                if current_streak > 0:
                    longest_win_streak = max(longest_win_streak, current_streak)
                else:
                    longest_loss_streak = min(longest_loss_streak, current_streak)

                # Start new streak
                if pick.is_correct:
                    current_streak = 1
                else:
                    current_streak = -1

            last_result = pick.is_correct

        # Check final streak
        if current_streak > 0:
            longest_win_streak = max(longest_win_streak, current_streak)
        else:
            longest_loss_streak = min(longest_loss_streak, current_streak)

        # Return the streak with largest absolute value
        if abs(longest_win_streak) >= abs(longest_loss_streak):
            return longest_win_streak
        else:
            return longest_loss_streak

    def _calculate_current_streak(self, season_id):
        """Calculate current winning/losing streak - DEPRECATED, use _calculate_longest_streak instead"""
        from .game import Game
        from .pick import Pick

        # Get completed picks ordered by week (most recent first)
        picks = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == self.id,
                Pick.season_id == season_id,
                Pick.is_correct.isnot(None),
            )
            .order_by(Game.week.desc())
            .all()
        )

        if not picks:
            return 0

        # Calculate streak from most recent pick
        streak = 0
        last_result = picks[0].is_correct

        for pick in picks:
            if pick.is_correct == last_result:
                if pick.is_correct:
                    streak += 1  # Winning streak (positive)
                else:
                    streak -= 1  # Losing streak (negative)
            else:
                break

        return streak

    def is_playoff_eligible(self, season_id, group_id=None):
        """Check if user is in top 4 for playoff eligibility

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by
        """
        from .season import Season

        season = Season.query.get(season_id)
        if not season or season.current_week <= season.regular_season_weeks:
            return False, "Regular season not complete"

        # Get leaderboard for regular season only
        leaderboard = self.get_season_leaderboard(
            season_id, regular_season_only=True, group_id=group_id
        )

        # Find user's position
        user_position = None
        for i, entry in enumerate(leaderboard):
            if entry["user_id"] == self.id:
                user_position = i + 1
                break

        if user_position is None:
            return False, "User not found in leaderboard"

        return user_position <= 4, f"Position: {user_position}"

    def is_superbowl_eligible(self, season_id, group_id=None):
        """Check if user is in top 2 for Super Bowl eligibility (of playoff participants)

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by
        """
        from .season import Season

        season = Season.query.get(season_id)
        if (
            not season or season.current_week <= season.regular_season_weeks + 2
        ):  # Need to be past first playoff rounds
            return False, "Playoffs not advanced enough"

        # Get leaderboard for regular season only to find playoff participants
        leaderboard = self.get_season_leaderboard(
            season_id, regular_season_only=True, group_id=group_id
        )

        # Find user's position
        user_position = None
        for i, entry in enumerate(leaderboard):
            if entry["user_id"] == self.id:
                user_position = i + 1
                break

        if user_position is None:
            return False, "User not found in leaderboard"

        # Must be in top 4 to make playoffs, and top 2 of those for Super Bowl
        return user_position <= 2, f"Position: {user_position}"

    def get_used_teams_this_season(self, season_id, group_id=None):
        """Get list of teams already used by this user in regular season

        Args:
            season_id: Season ID
            group_id: Group ID (None for global picks)
        """
        from .game import Game
        from .pick import Pick
        from .season import Season

        season = Season.query.get(season_id)
        if not season:
            return []

        # Build filter based on picks_are_global setting
        pick_filter = [
            Pick.user_id == self.id,
            Pick.season_id == season_id,
            Game.week <= season.regular_season_weeks,
        ]

        if not self.picks_are_global:
            pick_filter.append(Pick.group_id == group_id)
        else:
            pick_filter.append(Pick.group_id.is_(None))

        # Only count regular season picks for the "one team per season" rule
        picks = Pick.query.join(Game).filter(*pick_filter).all()

        return [pick.selected_team for pick in picks if pick.selected_team]

    def can_pick_team(
        self, team_id, week, season_id, group_id=None, exclude_pick_id=None
    ):
        """Check if user can pick a specific team for a specific week

        Args:
            team_id: ID of the team to pick
            week: Week number
            season_id: Season ID
            group_id: Group ID (None for global picks)
            exclude_pick_id: Pick ID to exclude from validation (for updates)
        """
        from .game import Game
        from .pick import Pick
        from .season import Season

        season = Season.query.get(season_id)
        if not season:
            return False, "Invalid season"

        # Build filter for picks based on picks_are_global setting
        pick_filter = [Pick.user_id == self.id, Pick.season_id == season_id]
        if not self.picks_are_global:
            pick_filter.append(Pick.group_id == group_id)
        else:
            pick_filter.append(Pick.group_id.is_(None))

        # Exclude current pick if updating
        if exclude_pick_id:
            pick_filter.append(Pick.id != exclude_pick_id)

        # Rule 1: Team already used this season (except playoffs)
        if not season.is_playoff_week(week):
            # Get used teams for this group (or globally)
            used_picks = Pick.query.filter(*pick_filter).all()
            used_team_ids = [pick.selected_team_id for pick in used_picks]

            if team_id in used_team_ids:
                return False, "Team already used this season"

        # Rule 2: Check losing team restriction
        if week > 1:
            previous_week_filter = pick_filter + [Game.week == week - 1]
            previous_week_pick = (
                Pick.query.join(Game).filter(*previous_week_filter).first()
            )

            if (
                previous_week_pick
                and previous_week_pick.is_correct is False
                and previous_week_pick.selected_team_id == team_id
            ):
                return False, "Cannot pick losing team from previous game week"

        return True, "Team available"

    @staticmethod
    def get_season_leaderboard(season_id, regular_season_only=False, group_id=None):
        """Get leaderboard for the season with new scoring rules

        Args:
            season_id: Season ID
            regular_season_only: If True, only count regular season stats
            group_id: Optional group ID to filter picks by
        """
        from .group_member import GroupMember
        from .pick import Pick
        from .season import Season

        season = Season.query.get(season_id)
        if not season:
            return []

        # Get all users who have picks in this season using SQLAlchemy but with fresh session
        db.session.commit()  # Ensure any pending changes are committed
        db.session.expire_all()  # Force all objects to be reloaded from DB

        # Build query to get users with picks in this season
        query = db.session.query(User.id).join(Pick).filter(Pick.season_id == season_id)

        # If filtering by group, only get users who are members of that group
        if group_id is not None:
            # Join with GroupMember to ensure we only get users who are members of the group
            query = query.join(GroupMember, GroupMember.user_id == User.id).filter(
                GroupMember.group_id == group_id, GroupMember.is_active.is_(True)
            )

        users_with_picks = query.distinct().all()

        user_ids = [user.id for user in users_with_picks]

        leaderboard = []

        for user_id in user_ids:
            # Get fresh user object
            user = User.query.get(user_id)

            # Pass group_id to get_season_stats for per-group filtering
            # For users with global picks, this will still get all their picks
            # For users with per-group picks, this will filter by the specific group
            stats = user.get_season_stats(season_id, group_id=group_id)

            if not stats:
                continue

            # Use regular season stats only if requested
            if regular_season_only:
                user_stats = stats["regular_season"]
            else:
                user_stats = stats["total"]

            leaderboard.append(
                {
                    "user_id": user.id,
                    "user": user,
                    "wins": user_stats["wins"],
                    "losses": user_stats.get("losses", 0),
                    "missed_games": user_stats.get("missed_games", 0),
                    "completed_picks": user_stats["completed_picks"],
                    "total_picks": user_stats["total_picks"],
                    "tiebreaker_points": user_stats["tiebreaker_points"],
                    "accuracy": user_stats["accuracy"],
                    "longest_streak": stats["total"].get("longest_streak", 0),
                }
            )

        # Sort by wins (descending), then by tiebreaker points (descending)
        leaderboard.sort(
            key=lambda x: (x["wins"], x["tiebreaker_points"]), reverse=True
        )

        return leaderboard

    def to_dict(self):
        """Convert user to dictionary for API responses"""
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
