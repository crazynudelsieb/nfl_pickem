from datetime import datetime, timezone

from app import db


class AdminAction(db.Model):
    __tablename__ = "admin_actions"

    id = db.Column(db.Integer, primary_key=True)

    # Action details
    admin_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )  # User being acted upon
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)

    # Action type and details
    action_type = db.Column(
        db.String(50), nullable=False
    )  # 'create_pick', 'update_pick', 'delete_pick', 'promote_member', etc.
    action_description = db.Column(db.String(500), nullable=False)

    # Related object IDs for context
    pick_id = db.Column(db.Integer, db.ForeignKey("picks.id"), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=True)
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=True)

    # Additional context data (JSON)
    action_metadata = db.Column(db.JSON, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    admin_user = db.relationship(
        "User", foreign_keys=[admin_user_id], backref="admin_actions_performed"
    )
    target_user = db.relationship(
        "User", foreign_keys=[target_user_id], backref="admin_actions_received"
    )
    group = db.relationship(
        "Group", backref=db.backref("admin_actions", cascade="all, delete-orphan")
    )
    pick = db.relationship("Pick", backref="admin_actions")
    game = db.relationship("Game", backref="admin_actions")
    season = db.relationship("Season", backref="admin_actions")

    # Indexes
    __table_args__ = (
        db.Index("idx_admin_action_group", "group_id"),
        db.Index("idx_admin_action_admin", "admin_user_id"),
        db.Index("idx_admin_action_target", "target_user_id"),
        db.Index("idx_admin_action_type", "action_type"),
        db.Index("idx_admin_action_created", "created_at"),
    )

    def __repr__(self):
        return f'<AdminAction {self.action_type} by {self.admin_user.username if self.admin_user else "Unknown"} in group {self.group_id}>'

    @staticmethod
    def log_action(
        admin_user_id,
        group_id,
        action_type,
        description,
        target_user_id=None,
        pick_id=None,
        game_id=None,
        season_id=None,
        action_metadata=None,
    ):
        """Log an admin action"""
        action = AdminAction(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            group_id=group_id,
            action_type=action_type,
            action_description=description,
            pick_id=pick_id,
            game_id=game_id,
            season_id=season_id,
            action_metadata=action_metadata or {},
        )

        db.session.add(action)
        return action

    @staticmethod
    def log_pick_creation(
        admin_user, target_user, group, pick, description_override=None
    ):
        """Convenience method for logging pick creation"""
        if description_override:
            description = description_override
        else:
            description = f"Created pick for {target_user.username}: {pick.selected_team.abbreviation} in {pick.game.away_team.abbreviation} vs {pick.game.home_team.abbreviation} (Week {pick.week})"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="create_pick",
            description=description,
            pick_id=pick.id,
            game_id=pick.game_id,
            season_id=pick.season_id,
            action_metadata={
                "team_selected": pick.selected_team.abbreviation,
                "week": pick.week,
                "game_matchup": f"{pick.game.away_team.abbreviation} vs {pick.game.home_team.abbreviation}",
            },
        )

    @staticmethod
    def log_pick_update(admin_user, target_user, group, old_pick, new_pick):
        """Convenience method for logging pick updates"""
        description = f"Updated pick for {target_user.username}: {old_pick.selected_team.abbreviation} → {new_pick.selected_team.abbreviation} in Week {new_pick.week}"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="update_pick",
            description=description,
            pick_id=new_pick.id,
            game_id=new_pick.game_id,
            season_id=new_pick.season_id,
            action_metadata={
                "old_team": old_pick.selected_team.abbreviation,
                "new_team": new_pick.selected_team.abbreviation,
                "week": new_pick.week,
                "game_matchup": f"{new_pick.game.away_team.abbreviation} vs {new_pick.game.home_team.abbreviation}",
            },
        )

    @staticmethod
    def log_pick_deletion(admin_user, target_user, group, pick):
        """Convenience method for logging pick deletion"""
        description = f"Deleted pick for {target_user.username}: {pick.selected_team.abbreviation} in Week {pick.week}"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="delete_pick",
            description=description,
            game_id=pick.game_id,
            season_id=pick.season_id,
            action_metadata={
                "team_deleted": pick.selected_team.abbreviation,
                "week": pick.week,
                "game_matchup": f"{pick.game.away_team.abbreviation} vs {pick.game.home_team.abbreviation}",
            },
        )

    @staticmethod
    def log_member_promotion(admin_user, target_user, group):
        """Convenience method for logging member promotion"""
        description = f"Promoted {target_user.username} to admin"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="promote_member",
            description=description,
        )

    @staticmethod
    def log_member_demotion(admin_user, target_user, group):
        """Convenience method for logging member demotion"""
        description = f"Demoted {target_user.username} from admin"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="demote_member",
            description=description,
        )

    @staticmethod
    def log_member_removal(admin_user, target_user, group):
        """Convenience method for logging member removal"""
        description = f"Removed {target_user.username} from group"

        return AdminAction.log_action(
            admin_user_id=admin_user.id,
            target_user_id=target_user.id,
            group_id=group.id,
            action_type="remove_member",
            description=description,
        )

    def to_dict(self):
        """Convert action to dictionary for API responses"""
        return {
            "id": self.id,
            "admin_user": self.admin_user.username if self.admin_user else None,
            "target_user": self.target_user.username if self.target_user else None,
            "group_id": self.group_id,
            "group_name": self.group.name if self.group else None,
            "action_type": self.action_type,
            "action_description": self.action_description,
            "action_metadata": self.action_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
