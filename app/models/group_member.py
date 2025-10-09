from datetime import datetime, timezone

from app import db


class GroupMember(db.Model):
    __tablename__ = "group_members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)

    # Membership status and role
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)

    # Timestamps
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    left_at = db.Column(db.DateTime)

    # Constraints
    __table_args__ = (
        db.UniqueConstraint("user_id", "group_id", name="unique_user_group"),
        db.Index("idx_group_members_active", "group_id", "is_active"),
        db.Index("idx_user_memberships", "user_id", "is_active"),
    )

    def __repr__(self):
        return f"<GroupMember user_id={self.user_id} group_id={self.group_id}>"

    def promote_to_admin(self):
        """Promote member to admin"""
        self.is_admin = True

    def demote_from_admin(self):
        """Remove admin privileges"""
        self.is_admin = False

    def deactivate(self):
        """Deactivate membership"""
        self.is_active = False
        self.left_at = datetime.now(timezone.utc)

    def reactivate(self):
        """Reactivate membership"""
        self.is_active = True
        self.left_at = None
        self.joined_at = datetime.now(timezone.utc)

    def to_dict(self):
        """Convert membership to dictionary for API responses"""
        return {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "username": self.user.username if self.user else None,
            "display_name": self.user.full_name if self.user else None,
            "is_admin": self.is_admin,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }
