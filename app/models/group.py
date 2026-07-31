import secrets
from datetime import datetime, timezone

from app import db


# Default ruleset, used for global picks (no group context) and as form defaults:
# - pick_team_once: each team can only be picked once during the regular season
# - no_repeat_opponent: cannot pick against the same opponent two weeks in a row
# - playoff_spots: top N players qualify for the playoffs
# - superbowl_spots: top N playoff players qualify for the Super Bowl
DEFAULT_RULES = {
    "pick_team_once": True,
    "no_repeat_opponent": True,
    "playoff_spots": 4,
    "superbowl_spots": 2,
}


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Group settings
    is_public = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    max_members = db.Column(db.Integer, default=50)

    # Pick rule settings (see DEFAULT_RULES for the standard ruleset)
    pick_team_once = db.Column(db.Boolean, default=True, nullable=False)
    no_repeat_opponent = db.Column(db.Boolean, default=True, nullable=False)
    playoff_spots = db.Column(db.Integer, default=4, nullable=False)
    superbowl_spots = db.Column(db.Integer, default=2, nullable=False)

    # Group code for easy joining
    invite_code = db.Column(db.String(8), unique=True, nullable=False, index=True)

    # URL-safe slug for accessing group (non-guessable)
    slug = db.Column(db.String(16), unique=True, nullable=False, index=True)

    # Creator and timestamps
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Current season
    current_season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"))

    # Relationships
    members = db.relationship(
        "GroupMember", backref="group", lazy="dynamic", cascade="all, delete-orphan"
    )
    invites = db.relationship(
        "Invite", backref="group", lazy="dynamic", cascade="all, delete-orphan"
    )
    current_season = db.relationship("Season", foreign_keys=[current_season_id])

    # Database indexes and constraints
    __table_args__ = (
        db.Index("idx_group_creator", "creator_id"),
        db.Index("idx_group_active", "is_active"),
        db.Index("idx_group_public", "is_public"),
        db.Index("idx_group_invite_code", "invite_code"),
        db.Index("idx_group_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Group {self.name}>"

    def __init__(self, **kwargs):
        super(Group, self).__init__(**kwargs)
        if not self.invite_code:
            self.invite_code = self.generate_invite_code()
        if not self.slug:
            self.slug = self.generate_slug()

    @staticmethod
    def generate_invite_code():
        """Generate a unique 8-character invite code"""
        while True:
            code = secrets.token_urlsafe(6)[:8].upper()
            if not Group.query.filter_by(invite_code=code).first():
                return code

    @staticmethod
    def generate_slug():
        """Generate a unique 16-character URL-safe slug"""
        while True:
            slug = secrets.token_urlsafe(12)[:16]
            if not Group.query.filter_by(slug=slug).first():
                return slug

    def get_active_members(self):
        """Get all active members of the group"""
        from sqlalchemy.orm import joinedload

        from .group_member import GroupMember

        return (
            self.members.filter_by(is_active=True)
            .options(joinedload(GroupMember.user))
            .all()
        )

    def get_member_count(self):
        """Get count of active members"""
        return self.members.filter_by(is_active=True).count()

    def is_full(self):
        """Check if group has reached maximum capacity"""
        return self.get_member_count() >= self.max_members

    def can_user_join(self, user):
        """Check if a user can join this group"""
        if self.is_full():
            return False, "Group is full"

        if self.is_user_member(user.id):
            return False, "Already a member"

        return True, "Can join"

    def is_user_member(self, user_id):
        """Check if user is an active member"""
        return (
            self.members.filter_by(user_id=user_id, is_active=True).first() is not None
        )

    def is_user_admin(self, user_id):
        """Check if user is an admin of this group"""
        member = self.members.filter_by(user_id=user_id, is_active=True).first()
        return member and member.is_admin

    def add_member(self, user, is_admin=False):
        """Add a user to the group"""
        from .group_member import GroupMember

        # Check if user is already a member
        existing = self.members.filter_by(user_id=user.id).first()
        if existing:
            if existing.is_active:
                return False, "User is already a member"
            else:
                # Reactivate membership
                existing.is_active = True
                existing.joined_at = datetime.now(timezone.utc)
                return True, "Membership reactivated"

        # Check capacity
        can_join, message = self.can_user_join(user)
        if not can_join:
            return False, message

        # Create new membership
        membership = GroupMember(user_id=user.id, group_id=self.id, is_admin=is_admin)
        db.session.add(membership)
        return True, "User added successfully"

    def remove_member(self, user_id):
        """Remove a user from the group"""
        member = self.members.filter_by(user_id=user_id, is_active=True).first()
        if member:
            member.is_active = False
            member.left_at = datetime.now(timezone.utc)
            return True, "User removed successfully"
        return False, "User is not a member"

    # Fields frozen by rules_locked_reason(). Cosmetic settings - name,
    # description, visibility, capacity - stay editable all season.
    RULE_FIELDS = (
        "pick_team_once",
        "no_repeat_opponent",
        "playoff_spots",
        "superbowl_spots",
    )

    def rules_locked_reason(self):
        """Why this group's pick rules can no longer change, or None.

        Rules freeze as soon as a pick exists in this group for the active
        season. Those picks were made - and validated - under the current
        ruleset, so rewriting it afterwards retroactively changes which of them
        were ever legal, and can move the playoff cutoff under players who have
        already finished their regular season.

        Scoped to this group's own picks rather than to the calendar, so a
        group created mid-season can still be configured up until its first
        pick. Members whose picks are global are governed by DEFAULT_RULES and
        are deliberately not counted here.
        """
        from .pick import Pick
        from .season import Season

        season = Season.get_current_season()
        if not season:
            return None

        first_pick = Pick.query.filter_by(
            group_id=self.id, season_id=season.id
        ).first()

        if first_pick is None:
            return None

        return f"picks have already been made in {season.name}"

    def apply_rules(self, pick_team_once, no_repeat_opponent, playoff_spots,
                    superbowl_spots):
        """Apply a ruleset unless the rules are locked.

        Returns:
            tuple: (applied, reason) - reason is None when applied, and when
            refused it is set only if the submitted rules actually differed.
        """
        submitted = {
            "pick_team_once": pick_team_once,
            "no_repeat_opponent": no_repeat_opponent,
            "playoff_spots": playoff_spots,
            "superbowl_spots": superbowl_spots,
        }

        reason = self.rules_locked_reason()
        if reason is None:
            for field, value in submitted.items():
                setattr(self, field, value)
            return True, None

        changed = any(
            getattr(self, field) != value for field, value in submitted.items()
        )
        return False, (reason if changed else None)

    def get_rules(self):
        """Return this group's pick rule settings as a dict"""
        return {
            "pick_team_once": (
                self.pick_team_once
                if self.pick_team_once is not None
                else DEFAULT_RULES["pick_team_once"]
            ),
            "no_repeat_opponent": (
                self.no_repeat_opponent
                if self.no_repeat_opponent is not None
                else DEFAULT_RULES["no_repeat_opponent"]
            ),
            "playoff_spots": self.playoff_spots or DEFAULT_RULES["playoff_spots"],
            "superbowl_spots": self.superbowl_spots or DEFAULT_RULES["superbowl_spots"],
        }

    @classmethod
    def rules_for(cls, group_id):
        """Return pick rule settings for a group, or the defaults for global picks

        Args:
            group_id: Group ID or None (global picks use DEFAULT_RULES)
        """
        if group_id is not None:
            group = cls.query.get(group_id)
            if group:
                return group.get_rules()
        return dict(DEFAULT_RULES)

    def get_leaderboard(self, season_id=None):
        """Get leaderboard for the group using the new comprehensive stats system"""
        from .user import User

        season_id = season_id or self.current_season_id
        if not season_id:
            return []

        # Use the User.get_season_leaderboard method which properly handles per-group picks
        leaderboard_data = User.get_season_leaderboard(
            season_id, regular_season_only=False, group_id=self.id
        )

        return leaderboard_data

    def to_dict(self, include_members=False, include_invite_code=False):
        """Convert group to dictionary for API responses

        The invite code is opt-in: /api/search returns public groups the caller
        is not a member of, and the code is what grants membership. Callers
        that have already established membership pass include_invite_code=True.
        """
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_public": self.is_public,
            "is_active": self.is_active,
            "member_count": self.get_member_count(),
            "max_members": self.max_members,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "creator": self.creator.username if self.creator else None,
        }

        if include_invite_code:
            data["invite_code"] = self.invite_code

        if include_members:
            data["members"] = [member.to_dict() for member in self.get_active_members()]

        return data
