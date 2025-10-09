import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from app import db

logger = logging.getLogger(__name__)


class Invite(db.Model):
    __tablename__ = "invites"

    id = db.Column(db.Integer, primary_key=True)

    # Invite details
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    inviter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    invitee_email = db.Column(db.String(120), nullable=False, index=True)

    # Invite token and expiry
    token = db.Column(db.String(32), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Status
    is_used = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    used_at = db.Column(db.DateTime)

    # Indexes
    __table_args__ = (
        db.Index("idx_invite_email_group", "invitee_email", "group_id"),
        db.Index("idx_invite_token_active", "token", "is_active"),
    )

    def __repr__(self):
        return f"<Invite {self.invitee_email} to group {self.group_id}>"

    def __init__(self, **kwargs):
        super(Invite, self).__init__(**kwargs)
        if not self.token:
            self.token = self.generate_token()
        if not self.expires_at:
            self.expires_at = datetime.now(timezone.utc) + timedelta(
                hours=168
            )  # 1 week default

    @staticmethod
    def generate_token():
        """Generate a unique token for the invite"""
        while True:
            token = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
            )
            if not Invite.query.filter_by(token=token).first():
                return token

    @property
    def is_expired(self):
        """Check if invite has expired"""
        # Ensure both datetimes are timezone-aware for comparison
        current_time = datetime.now(timezone.utc)
        expires_at = self.expires_at

        # If expires_at is timezone-naive, assume it's UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Debug logging to help troubleshoot
        try:
            is_expired = current_time > expires_at
            logger.debug(
                f"Invite {self.token}: current_time={current_time}, expires_at={expires_at}, is_expired={is_expired}"
            )
            return is_expired
        except Exception as e:
            logger.error(f"Error comparing invite expiration times: {e}")
            # If there's an error, assume not expired to be safe
            return False

    @property
    def is_valid(self):
        """Check if invite is valid (not used, not expired, active)"""
        is_active = self.is_active
        is_not_used = not self.is_used
        is_not_expired = not self.is_expired

        is_valid = is_active and is_not_used and is_not_expired

        logger.debug(
            f"Invite {self.token} validity check: active={is_active}, not_used={is_not_used}, not_expired={is_not_expired}, valid={is_valid}"
        )

        return is_valid

    def use_invite(self, user_id=None):
        """Mark invite as used"""
        if not self.is_valid:
            return False, "Invite is not valid"

        from .user import User

        # Check if email matches a user
        if user_id:
            user = User.query.get(user_id)
            if not user or user.email != self.invitee_email:
                return False, "Email mismatch"

        # Add user to group
        success, message = self.group.add_member(user if user_id else None)
        if success:
            self.is_used = True
            self.used_at = datetime.now(timezone.utc)
            return True, "Invite used successfully"

        return False, message

    def revoke(self):
        """Revoke the invite"""
        self.is_active = False

    def extend_expiry(self, hours=168):
        """Extend invite expiry"""
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    @staticmethod
    def create_invite(group_id, inviter_id, invitee_email, expires_hours=168):
        """Create a new invite"""
        from .group import Group
        from .user import User

        # Check if group exists
        group = Group.query.get(group_id)
        if not group:
            return None, "Group not found"

        # Check if invitee is already a member
        invitee = User.query.filter_by(email=invitee_email).first()
        if invitee and group.is_user_member(invitee.id):
            return None, "User is already a member"

        # Check if there's already an active invite for this email
        existing_invite = Invite.query.filter_by(
            group_id=group_id,
            invitee_email=invitee_email,
            is_active=True,
            is_used=False,
        ).first()

        if existing_invite and not existing_invite.is_expired:
            return None, "Active invite already exists for this email"

        # Deactivate any existing invites
        if existing_invite:
            existing_invite.is_active = False

        # Create new invite
        invite = Invite(
            group_id=group_id,
            inviter_id=inviter_id,
            invitee_email=invitee_email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        )

        db.session.add(invite)
        return invite, "Invite created successfully"

    @staticmethod
    def get_by_token(token):
        """Get invite by token"""
        # First try to find any invite with this token for debugging
        invite = Invite.query.filter_by(token=token).first()
        if invite:
            logger.debug(
                f"Found invite with token {token}: active={invite.is_active}, used={invite.is_used}, expired={invite.is_expired}"
            )
            # Only return if active
            if invite.is_active:
                return invite
            else:
                logger.warning(f"Invite {token} found but is not active")
        else:
            logger.warning(f"No invite found with token {token}")

        return None

    def get_invite_url(self, base_url):
        """Get the full invite URL"""
        return f"{base_url}/invite/{self.token}"

    def to_dict(self, include_token=False):
        """Convert invite to dictionary for API responses"""
        data = {
            "id": self.id,
            "group_id": self.group_id,
            "group_name": self.group.name if self.group else None,
            "inviter": self.inviter.username if self.inviter else None,
            "invitee_email": self.invitee_email,
            "is_used": self.is_used,
            "is_expired": self.is_expired,
            "is_valid": self.is_valid,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
        }

        if include_token:
            data["token"] = self.token

        return data
