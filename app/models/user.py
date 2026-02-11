import html
import random
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

    def get_group_id_for_filtering(self, group_id=None):
        """Helper to determine the correct group_id value for pick filtering

        Args:
            group_id: The requested group_id (can be None)

        Returns:
            None if user has global picks, otherwise the provided group_id
        """
        return None if self.picks_are_global else group_id

    def build_pick_filter(self, season_id=None, group_id=None, **extra_filters):
        """Build pick query filter dict respecting picks_are_global setting

        Args:
            season_id: Optional season ID to filter by
            group_id: Optional group ID (respects picks_are_global)
            **extra_filters: Additional filter key-value pairs

        Returns:
            dict: Filter dictionary for Pick.query.filter_by()

        Example:
            filter_dict = user.build_pick_filter(season_id=2024, group_id=5)
            picks = Pick.query.filter_by(**filter_dict).all()
        """
        pick_filter = {"user_id": self.id}

        if season_id is not None:
            pick_filter["season_id"] = season_id

        # Apply group filtering based on picks_are_global setting
        effective_group_id = self.get_group_id_for_filtering(group_id)
        if effective_group_id is not None:
            pick_filter["group_id"] = effective_group_id

        # Add any additional filters
        pick_filter.update(extra_filters)

        return pick_filter

    def set_display_name(self, display_name):
        """Set display name with sanitization"""
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

        # Get all user picks for this season using helper
        pick_filter = self.build_pick_filter(season_id=season_id, group_id=group_id)
        picks = Pick.query.filter_by(**pick_filter).all()

        # Get all completed games in this season
        # NOTE: Must use is_final column, not status property (status is @property, can't filter)
        completed_games = Game.query.filter(
            Game.season_id == season_id, Game.is_final == True
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

        # Filter playoff weeks based on eligibility - users shouldn't be penalized
        # for missing playoff/Super Bowl games they weren't eligible to pick
        # 
        # IMPORTANT: Use snapshot-based eligibility checks ONLY to avoid recursion.
        # is_superbowl_eligible() calls get_season_stats() which would cause infinite loop.
        eligible_playoff_weeks = set()
        if playoff_weeks_with_games:
            # Check playoff eligibility using snapshot (avoids recursion)
            is_po_eligible = self._check_playoff_eligible_from_snapshot(season_id, group_id)
            
            if is_po_eligible:
                # User is playoff eligible - include playoff weeks (19-21)
                superbowl_week = season.regular_season_weeks + season.playoff_weeks
                for week in playoff_weeks_with_games:
                    if week < superbowl_week:
                        eligible_playoff_weeks.add(week)
                    elif week == superbowl_week:
                        # Check Super Bowl eligibility using snapshot (avoids recursion)
                        is_sb_eligible = self._check_superbowl_eligible_from_snapshot(season_id, group_id)
                        if is_sb_eligible:
                            eligible_playoff_weeks.add(week)

        # Separate user picks into regular season and playoff picks
        regular_picks = [p for p in picks if not season.is_playoff_week(p.game.week)]
        playoff_picks = [p for p in picks if season.is_playoff_week(p.game.week)]

        # Calculate stats using shared helper
        # For playoffs, only count eligible weeks as potential missed games
        regular_stats = self._compute_stats_for_picks(regular_picks, regular_season_weeks_with_games)
        playoff_stats = self._compute_stats_for_picks(playoff_picks, eligible_playoff_weeks)

        # Calculate total stats (combine regular and playoffs)
        total_wins = regular_stats["wins"] + playoff_stats["wins"]
        total_ties = regular_stats["ties"] + playoff_stats["ties"]
        total_losses = regular_stats["losses"] + playoff_stats["losses"]
        total_score = regular_stats["score"] + playoff_stats["score"]
        total_missed = regular_stats["missed"] + playoff_stats["missed"]
        total_tiebreaker = regular_stats["tiebreaker"] + playoff_stats["tiebreaker"]
        total_picks = regular_stats["total_picks"] + playoff_stats["total_picks"]
        total_completed = regular_stats["completed"] + playoff_stats["completed"]

        # Total accuracy
        total_accuracy_denominator = total_completed + total_missed
        total_accuracy = (
            (total_wins / total_accuracy_denominator * 100) if total_accuracy_denominator > 0 else 0
        )

        # Calculate longest streak for the season
        longest_streak = self._calculate_longest_streak(season_id, group_id)

        return {
            "regular_season": {
                "wins": regular_stats["wins"],
                "ties": regular_stats["ties"],
                "losses": regular_stats["losses"],
                "total_score": regular_stats["score"],
                "missed_games": regular_stats["missed"],
                "total_picks": regular_stats["total_picks"],
                "completed_picks": regular_stats["completed"],
                "tiebreaker_points": regular_stats["tiebreaker"],
                "accuracy": regular_stats["accuracy"],
            },
            "playoffs": {
                "wins": playoff_stats["wins"],
                "ties": playoff_stats["ties"],
                "losses": playoff_stats["losses"],
                "total_score": playoff_stats["score"],
                "missed_games": playoff_stats["missed"],
                "total_picks": playoff_stats["total_picks"],
                "completed_picks": playoff_stats["completed"],
                "tiebreaker_points": playoff_stats["tiebreaker"],
                "accuracy": playoff_stats["accuracy"],
            },
            "total": {
                "wins": total_wins,
                "ties": total_ties,
                "losses": total_losses,
                "total_score": total_score,
                "missed_games": total_missed,
                "total_picks": total_picks,
                "completed_picks": total_completed,
                "tiebreaker_points": total_tiebreaker,
                "accuracy": total_accuracy,
                "longest_streak": longest_streak,
            },
        }

    @staticmethod
    def _compute_stats_for_picks(picks, completed_weeks):
        """Calculate win/loss/tie stats for a set of picks

        Args:
            picks: List of Pick objects
            completed_weeks: Set of weeks with completed games (for missed game tracking)

        Returns:
            dict: {"wins": int, "ties": int, "losses": int, "completed": int,
                   "missed": int, "total_picks": int, "score": int,
                   "tiebreaker": int, "accuracy": float}
        """
        # Get completed picks (game is final)
        completed = [p for p in picks if p.game and p.game.is_final]

        # Count results
        wins = sum(1 for p in completed if p.is_correct is True)
        ties = sum(1 for p in completed if p.is_correct is None)
        losses = sum(1 for p in completed if p.is_correct is False)

        # Sum points
        total_score = sum(p.points_earned or 0 for p in completed)
        total_tiebreaker = sum(p.tiebreaker_points or 0 for p in completed)

        # Count missed games (weeks with completed games but no pick)
        picks_by_week = {p.week for p in picks}
        missed_weeks = completed_weeks - picks_by_week
        missed_games = len(missed_weeks)

        # Calculate accuracy (missed games count as losses)
        accuracy_denominator = len(completed) + missed_games
        accuracy = (
            (wins / accuracy_denominator * 100) if accuracy_denominator > 0 else 0
        )

        return {
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "completed": len(completed),
            "missed": missed_games,
            "total_picks": len(picks),
            "score": total_score,
            "tiebreaker": total_tiebreaker,
            "accuracy": accuracy,
        }

    @staticmethod
    def _compute_longest_streak_from_picks(picks):
        """Shared utility to compute longest streak from a list of picks

        Args:
            picks: List of Pick objects ordered chronologically

        Returns:
            Longest streak (positive for wins, negative for losses)
        """
        if not picks:
            return 0

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

        # Get completed picks ordered by week using helper
        pick_filter = self.build_pick_filter(season_id=season_id, group_id=group_id)
        picks = (
            Pick.query.filter_by(**pick_filter)
            .join(Game)
            .filter(Pick.is_correct.isnot(None))
            .order_by(Game.week.asc())
            .all()
        )

        return self._compute_longest_streak_from_picks(picks)

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

        return self._compute_longest_streak_from_picks(picks)

    def _check_playoff_eligible_from_snapshot(self, season_id, group_id=None):
        """Lightweight check for playoff eligibility using snapshot only.
        
        Used internally by get_season_stats to avoid recursion.
        Returns bool only, no message.
        """
        from .regular_season_snapshot import RegularSeasonSnapshot
        from .season import Season

        season = Season.query.get(season_id)
        if not season or season.current_week <= season.regular_season_weeks:
            return False

        effective_group_id = None if self.picks_are_global else group_id
        snapshot = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            user_id=self.id,
            group_id=effective_group_id
        ).first()

        return snapshot.is_playoff_eligible if snapshot else False

    def _check_superbowl_eligible_from_snapshot(self, season_id, group_id=None):
        """Lightweight check for Super Bowl eligibility using snapshot only.
        
        Used internally by get_season_stats to avoid recursion.
        Returns bool only, no message.
        """
        from .regular_season_snapshot import RegularSeasonSnapshot
        from .season import Season

        season = Season.query.get(season_id)
        if not season or season.current_week <= season.regular_season_weeks + 2:
            return False

        effective_group_id = None if self.picks_are_global else group_id
        snapshot = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            user_id=self.id,
            group_id=effective_group_id
        ).first()

        return snapshot.is_superbowl_eligible if snapshot else False

    def is_playoff_eligible(self, season_id, group_id=None):
        """Check if user is in top 4 for playoff eligibility

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by
        """
        from .regular_season_snapshot import RegularSeasonSnapshot
        from .season import Season

        season = Season.query.get(season_id)
        if not season:
            return False, "Invalid season"

        # If we're in regular season, always return False
        if season.current_week <= season.regular_season_weeks:
            return False, "Regular season not complete"

        # CHANGED: Use snapshot if available (more reliable than recalculating)
        effective_group_id = None if self.picks_are_global else group_id
        snapshot = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            user_id=self.id,
            group_id=effective_group_id
        ).first()

        if snapshot:
            if snapshot.is_playoff_eligible:
                return True, f"Qualified: Rank #{snapshot.final_rank}"
            else:
                # Get top 4 names for message
                top4_names = RegularSeasonSnapshot.get_top4_names(season_id, effective_group_id)
                return False, f"Did not qualify. Top 4: {', '.join(top4_names)}"

        # Fallback: dynamic calculation (original logic) if snapshot doesn't exist
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

        if user_position <= 4:
            return True, f"Qualified: Position {user_position}"
        else:
            # Get top 4 names for better message
            top4_names = [leaderboard[i]["user"].username for i in range(min(4, len(leaderboard)))]
            return False, f"Did not qualify. Top 4: {', '.join(top4_names)}"

    def is_superbowl_eligible(self, season_id, group_id=None):
        """Check if user is in top 2 for Super Bowl eligibility (of playoff participants)

        Ranks by playoff wins (weeks 19-21), not regular season standings.

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by
        """
        from .game import Game
        from .pick import Pick
        from .season import Season

        season = Season.query.get(season_id)
        if (
            not season or season.current_week <= season.regular_season_weeks + 2
        ):  # Need to be past first playoff rounds
            return False, "Playoffs not advanced enough"

        # Get playoff-eligible users (top 4 from regular season)
        # First try snapshot-based, then fall back to dynamic
        eligible_user_ids = []
        from .regular_season_snapshot import RegularSeasonSnapshot
        snapshot_eligible = RegularSeasonSnapshot.get_playoff_eligible_users(season_id, group_id)
        if snapshot_eligible:
            eligible_user_ids = snapshot_eligible
        else:
            # Dynamic fallback: get top 4 from regular season leaderboard
            leaderboard = self.get_season_leaderboard(
                season_id, regular_season_only=True, group_id=group_id
            )
            eligible_user_ids = [entry["user_id"] for entry in leaderboard[:4]]

        if self.id not in eligible_user_ids:
            return False, "Not playoff eligible"

        # Rank eligible users by playoff wins (weeks 19-21)
        playoff_rankings = []
        for uid in eligible_user_ids:
            user = User.query.get(uid)
            if not user:
                continue
            stats = user.get_season_stats(season_id, group_id=group_id)
            if not stats:
                continue
            playoff_rankings.append({
                "user_id": uid,
                "playoff_wins": stats["playoffs"]["wins"],
                "total_tiebreaker": stats["total"]["tiebreaker_points"],
            })

        # Sort by playoff wins DESC, then tiebreaker DESC
        playoff_rankings.sort(
            key=lambda x: (x["playoff_wins"], x["total_tiebreaker"]),
            reverse=True
        )

        # Find this user's position in playoff rankings
        user_position = None
        for i, entry in enumerate(playoff_rankings):
            if entry["user_id"] == self.id:
                user_position = i + 1
                break

        if user_position is None:
            return False, "User not found in playoff rankings"

        return user_position <= 2, f"Playoff position: {user_position}"

    def is_playoff_eligible_from_snapshot(self, season_id, group_id=None):
        """Check playoff eligibility from snapshot (more reliable than recalculating)

        This is the preferred method to check eligibility during playoffs.
        Falls back to is_playoff_eligible() if snapshot doesn't exist.

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by

        Returns:
            tuple: (boolean, message_string)
        """
        # Delegate to is_playoff_eligible which now checks snapshots first
        return self.is_playoff_eligible(season_id, group_id)

    def is_superbowl_eligible_from_snapshot(self, season_id, group_id=None):
        """Check Super Bowl eligibility from snapshot

        Falls back to dynamic calculation if snapshot doesn't exist.

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by

        Returns:
            tuple: (boolean, message_string)
        """
        from .regular_season_snapshot import RegularSeasonSnapshot

        effective_group_id = None if self.picks_are_global else group_id
        snapshot = RegularSeasonSnapshot.query.filter_by(
            season_id=season_id,
            user_id=self.id,
            group_id=effective_group_id
        ).first()

        if snapshot:
            if snapshot.is_superbowl_eligible:
                return True, "Super Bowl eligible"
            else:
                return False, "Only top 2 from playoffs can pick in Super Bowl"

        # Fallback: dynamic calculation if snapshot doesn't exist
        return self.is_superbowl_eligible(season_id, group_id)

    def get_playoff_stats(self, season_id, group_id=None):
        """Get ONLY playoff stats (weeks 19-22) - separate from regular season stats

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by

        Returns:
            dict: {"wins": int, "losses": int, "ties": int, "total_score": float,
                   "tiebreaker_points": float, "accuracy": float, ...}
        """
        stats = self.get_season_stats(season_id, group_id)
        return stats["playoffs"] if stats else None

    @staticmethod
    def get_playoff_leaderboard(season_id, group_id=None):
        """Get playoff-only leaderboard (weeks 19-22)

        Ranks by: (1) playoff wins, (2) total tiebreaker points (season-long)
        Only includes top 4 from regular season.

        Args:
            season_id: Season ID
            group_id: Optional group ID to filter picks by

        Returns:
            list: Leaderboard entries with playoff + regular season stats
        """
        from .regular_season_snapshot import RegularSeasonSnapshot

        # Get playoff-eligible users from snapshots
        eligible_user_ids = RegularSeasonSnapshot.get_playoff_eligible_users(season_id, group_id)

        if not eligible_user_ids:
            return []

        leaderboard = []
        for user_id in eligible_user_ids:
            user = User.query.get(user_id)
            if not user:
                continue

            stats = user.get_season_stats(season_id, group_id=group_id)

            if not stats:
                continue

            playoff_stats = stats["playoffs"]
            regular_stats = stats["regular_season"]

            # Key: Use playoff wins for ranking, but TOTAL tiebreaker for tiebreaking
            leaderboard.append({
                "user_id": user.id,
                "user": user,
                "playoff_wins": playoff_stats["wins"],
                "playoff_losses": playoff_stats["losses"],
                "playoff_ties": playoff_stats["ties"],
                "playoff_score": playoff_stats["total_score"],
                "total_tiebreaker": stats["total"]["tiebreaker_points"],  # Season-long
                "playoff_accuracy": playoff_stats["accuracy"],
                # Include regular season for display
                "regular_wins": regular_stats["wins"],
                "regular_score": regular_stats["total_score"],
                "total_score": stats["total"]["total_score"],  # Overall
            })

        # Sort: (1) playoff wins DESC, (2) total tiebreaker DESC
        leaderboard.sort(
            key=lambda x: (x["playoff_wins"], x["total_tiebreaker"]),
            reverse=True
        )

        return leaderboard

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
            
            # Rule 3: Can't pick against same opponent twice in a row (regular season only)
            if previous_week_pick and not season.is_playoff_week(week):
                # Get the opponent from last week's pick
                prev_game = previous_week_pick.game
                last_week_opponent_id = (
                    prev_game.home_team_id 
                    if previous_week_pick.selected_team_id == prev_game.away_team_id 
                    else prev_game.away_team_id
                )
                
                # Check if we're being asked about a specific game's opponent
                # Note: This requires game context which we don't have here
                # The frontend will handle this check with full game context
                pass

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
                    "total_score": user_stats["total_score"],
                    "wins": user_stats["wins"],
                    "ties": user_stats.get("ties", 0),
                    "losses": user_stats.get("losses", 0),
                    "missed_games": user_stats.get("missed_games", 0),
                    "completed_picks": user_stats["completed_picks"],
                    "total_picks": user_stats["total_picks"],
                    "tiebreaker_points": user_stats["tiebreaker_points"],
                    "accuracy": user_stats["accuracy"],
                    "longest_streak": stats["total"].get("longest_streak", 0),
                }
            )

        # Sort by total score (descending), then by tiebreaker points (descending)
        leaderboard.sort(
            key=lambda x: (x["total_score"], x["tiebreaker_points"]), reverse=True
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
