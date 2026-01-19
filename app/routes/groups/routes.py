import logging

from flask import (
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.forms.groups import AdminPickForm, CreateGroupForm, EditGroupForm, InviteForm
from app.models import (
    AdminAction,
    Game,
    Group,
    GroupMember,
    Invite,
    Pick,
    Season,
    Team,
    User,
)
from app.routes.groups import bp

logger = logging.getLogger(__name__)


@bp.route("/")
@login_required
def index():
    """List user's groups"""
    user_groups = current_user.get_groups()
    public_groups = (
        Group.query.filter_by(is_public=True, is_active=True).limit(10).all()
    )

    # Get current season for leaderboard
    current_season = Season.get_current_season()

    # Get selected group from URL parameter
    group_slug = request.args.get("group")
    selected_group = None
    leaderboard = []
    membership = None

    if group_slug and user_groups:
        selected_group = next((g for g in user_groups if g.slug == group_slug), None)
    elif user_groups and not group_slug:
        # Redirect to latest group with slug in URL
        return redirect(url_for("groups.index", group=user_groups[-1].slug))

    # Check if selected group is active (allow creator to access)
    if (
        selected_group
        and not selected_group.is_active
        and selected_group.creator_id != current_user.id
    ):
        flash(
            f'Group "{selected_group.name}" has been disabled by the owner.', "warning"
        )
        # Redirect to another active group if available
        active_groups = [g for g in user_groups if g.is_active]
        if active_groups:
            return redirect(url_for("groups.index", group=active_groups[-1].slug))
        else:
            selected_group = None  # Show no group selected

    is_playoff_mode = False
    if selected_group and current_season:
        # Check if we're in playoffs
        is_playoff_mode = current_season.is_playoff_week(current_season.current_week)

        if is_playoff_mode:
            # During playoffs: show dual scores for ALL users (not just top 4)
            from app.models.regular_season_snapshot import RegularSeasonSnapshot

            # Get all active members of this group
            member_ids = [m.user_id for m in selected_group.get_active_members()]
            all_users = User.query.filter(User.id.in_(member_ids)).all()
            leaderboard = []

            for user in all_users:
                stats = user.get_season_stats(current_season.id, group_id=selected_group.id)
                if not stats:
                    continue

                # Check if user is playoff eligible
                snapshot = RegularSeasonSnapshot.query.filter_by(
                    season_id=current_season.id,
                    user_id=user.id,
                    group_id=selected_group.id
                ).first()

                leaderboard.append({
                    "user_id": user.id,
                    "user": user,
                    "total_score": stats["total"]["total_score"],
                    "wins": stats["total"]["wins"],
                    "ties": stats["total"]["ties"],
                    "losses": stats["total"]["losses"],
                    "missed_games": stats["total"]["missed_games"],
                    "completed_picks": stats["total"]["completed_picks"],
                    "tiebreaker_points": stats["total"]["tiebreaker_points"],
                    "accuracy": stats["total"]["accuracy"],
                    "longest_streak": stats["total"]["longest_streak"],
                    # Playoff-specific data
                    "is_playoff_eligible": snapshot.is_playoff_eligible if snapshot else False,
                    "regular_wins": stats["regular_season"]["wins"],
                    "regular_score": stats["regular_season"]["total_score"],
                    "playoff_wins": stats["playoffs"]["wins"],
                    "playoff_score": stats["playoffs"]["total_score"],
                    "regular_rank": snapshot.final_rank if snapshot else None,
                })

            # Sort by total_score (descending), then by tiebreaker points (descending)
            leaderboard.sort(
                key=lambda x: (x["total_score"], x["tiebreaker_points"]), reverse=True
            )
        else:
            # Regular season: use existing leaderboard
            leaderboard = User.get_season_leaderboard(
                current_season.id, regular_season_only=False, group_id=selected_group.id
            )

        membership = GroupMember.query.filter_by(
            user_id=current_user.id, group_id=selected_group.id, is_active=True
        ).first()

    return render_template(
        "groups/index.html",
        user_groups=user_groups,
        public_groups=public_groups,
        selected_group=selected_group,
        leaderboard=leaderboard,
        current_season=current_season,
        membership=membership,
        is_playoff_mode=is_playoff_mode,
    )


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """Create a new group"""
    form = CreateGroupForm()

    if form.validate_on_submit():
        group = Group(
            name=form.name.data,
            description=form.description.data,
            is_public=form.is_public.data,
            max_members=form.max_members.data,
            creator_id=current_user.id,
        )

        db.session.add(group)
        db.session.flush()  # Get the group ID

        # Add creator as admin member
        success, message = group.add_member(current_user, is_admin=True)
        if not success:
            db.session.rollback()
            flash(f"Error creating group: {message}", "error")
            return render_template("groups/create.html", form=form)

        db.session.commit()
        flash(
            f'Group "{group.name}" created successfully! Invite code: {group.invite_code}',
            "success",
        )
        return redirect(url_for("groups.index", group=group.slug))

    # Log form validation errors
    if request.method == "POST" and form.errors:
        logger.warning(
            f"Group creation form validation failed for user {current_user.username}"
        )
        for field, errors in form.errors.items():
            for error in errors:
                logger.warning(f"  {field}: {error}")
                flash(f"{field}: {error}", "error")

    return render_template("groups/create.html", form=form)


@bp.route("/<int:group_id>")
@login_required
def detail(group_id):
    """Group detail page"""
    group = Group.query.get_or_404(group_id)

    # Check if user is a member
    if not group.is_user_member(current_user.id):
        flash("You are not a member of this group.", "error")
        return redirect(url_for("groups.index"))

    # Check if group is active (allow creator to access for re-enabling)
    if not group.is_active and group.creator_id != current_user.id:
        flash("This group has been disabled by the owner.", "warning")
        return redirect(url_for("groups.index"))

    # Get group leaderboard
    current_season = Season.get_current_season()
    leaderboard = []
    if current_season:
        leaderboard = group.get_leaderboard(current_season.id)

    # Get user's membership info
    membership = GroupMember.query.filter_by(
        user_id=current_user.id, group_id=group_id, is_active=True
    ).first()

    return render_template(
        "groups/detail.html",
        group=group,
        leaderboard=leaderboard,
        current_season=current_season,
        membership=membership,
    )


@bp.route("/<int:group_id>/edit", methods=["GET", "POST"])
@login_required
def edit(group_id):
    """Edit group settings"""
    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        flash("You do not have permission to edit this group.", "error")
        return redirect(url_for("groups.index", group=group.slug))

    form = EditGroupForm(obj=group)

    if form.validate_on_submit():
        group.name = form.name.data
        group.description = form.description.data
        group.is_public = form.is_public.data
        group.max_members = form.max_members.data

        db.session.commit()
        flash("Group updated successfully!", "success")
        return redirect(url_for("groups.index", group=group.slug))

    return render_template("groups/edit.html", form=form, group=group)


@bp.route("/<int:group_id>/members")
@login_required
def members(group_id):
    """Manage group members"""
    group = Group.query.get_or_404(group_id)

    # Check if user is a member
    if not group.is_user_member(current_user.id):
        flash("You are not a member of this group.", "error")
        return redirect(url_for("groups.index"))

    members = group.get_active_members()
    is_admin = group.is_user_admin(current_user.id)

    return render_template(
        "groups/members.html", group=group, members=members, is_admin=is_admin
    )


@bp.route("/<int:group_id>/invite", methods=["GET", "POST"])
@login_required
def invite(group_id):
    """Invite users to group"""
    group = Group.query.get_or_404(group_id)

    # Check if user can invite (is admin or group allows member invites)
    if not group.is_user_admin(current_user.id):
        flash("You do not have permission to invite users to this group.", "error")
        return redirect(url_for("groups.index", group=group.slug))

    form = InviteForm()

    if form.validate_on_submit():
        invite, message = Invite.create_invite(
            group_id=group_id, inviter_id=current_user.id, invitee_email=form.email.data
        )

        if invite:
            db.session.commit()
            # Send email with invite link
            invite_url = url_for(
                "groups.join_by_token", token=invite.token, _external=True
            )

            try:
                from app.utils.email_service import EmailService

                email_service = EmailService()
                success = email_service.send_group_invitation(
                    invite=invite, inviter=current_user
                )

                if success:
                    flash(f"Invitation email sent to {form.email.data}!", "success")
                else:
                    flash(
                        f"Invitation created but email failed to send. Share this link: {invite_url}",
                        "warning",
                    )
            except Exception as e:
                logger.error(f"Error sending invitation email: {e}")
                flash(
                    f"Invitation created but email failed to send. Share this link: {invite_url}",
                    "warning",
                )
        else:
            flash(f"Error creating invite: {message}", "error")

    # Get pending invites
    pending_invites = Invite.query.filter_by(
        group_id=group_id, is_active=True, is_used=False
    ).all()

    return render_template(
        "groups/invite.html", form=form, group=group, pending_invites=pending_invites
    )


@bp.route("/join", methods=["POST"])
@login_required
def join_by_form():
    """Join group by invite code submitted via form"""
    code = request.form.get("invite_code", "").strip()

    if not code:
        flash("Please enter an invite code.", "error")
        return redirect(url_for("groups.index"))

    # Redirect to the existing join route with the code
    return redirect(url_for("groups.join", code=code))


@bp.route("/join/<code>")
@login_required
def join(code):
    """Join group by invite code"""
    group = Group.query.filter_by(invite_code=code.upper()).first()

    if not group:
        flash("Invalid invite code.", "error")
        return redirect(url_for("groups.index"))

    if not group.is_active:
        flash("This group is no longer active.", "error")
        return redirect(url_for("groups.index"))

    # Try to add user to group
    success, message = group.add_member(current_user)

    if success:
        db.session.commit()
        flash(f'Successfully joined "{group.name}"!', "success")
        return redirect(url_for("groups.index", group=group.slug))
    else:
        flash(f"Unable to join group: {message}", "error")
        return redirect(url_for("groups.index"))


@bp.route("/invite/<token>")
def join_by_token(token):
    """Join group by invitation token"""
    invite = Invite.get_by_token(token)

    if not invite:
        flash("Invalid or expired invitation.", "error")
        return redirect(url_for("main.index"))

    if not invite.is_valid:
        # Provide more specific error message
        if invite.is_used:
            flash("This invitation has already been used.", "error")
        elif invite.is_expired:
            flash("This invitation has expired.", "error")
        elif not invite.is_active:
            flash("This invitation is no longer active.", "error")
        else:
            flash("This invitation is not valid.", "error")
        return redirect(url_for("main.index"))

    # If user is not logged in, redirect to login with next parameter
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.url))

    # Check if user's email matches the invite (case-insensitive)
    user_email = current_user.email.lower().strip() if current_user.email else ""
    invite_email = invite.invitee_email.lower().strip() if invite.invitee_email else ""

    if user_email != invite_email:
        flash(
            f"This invitation was sent to {invite.invitee_email}, but you are logged in as {current_user.email}.",
            "error",
        )
        return redirect(url_for("groups.index"))

    # Use the invite
    success, message = invite.use_invite(current_user.id)

    if success:
        db.session.commit()
        flash(f'Successfully joined "{invite.group.name}"!', "success")
        return redirect(url_for("groups.index", group=invite.group.slug))
    else:
        flash(f"Unable to join group: {message}", "error")
        return redirect(url_for("groups.index"))


@bp.route("/<int:group_id>/leave", methods=["POST"])
@login_required
def leave(group_id):
    """Leave a group"""
    group = Group.query.get_or_404(group_id)

    if not group.is_user_member(current_user.id):
        flash("You are not a member of this group.", "error")
        return redirect(url_for("groups.index"))

    # Don't allow group creator to leave if they are the only admin
    if group.creator_id == current_user.id:
        other_admins = (
            GroupMember.query.filter_by(
                group_id=group_id, is_admin=True, is_active=True
            )
            .filter(GroupMember.user_id != current_user.id)
            .count()
        )

        if other_admins == 0:
            flash(
                "You cannot leave this group as you are the only administrator. Please promote another member to admin first.",
                "error",
            )
            return redirect(url_for("groups.index", group=group.slug))

    success, message = group.remove_member(current_user.id)

    if success:
        db.session.commit()
        flash(f'You have left "{group.name}".', "info")
    else:
        flash(f"Error leaving group: {message}", "error")

    return redirect(url_for("groups.index"))


@bp.route("/<int:group_id>/delete", methods=["POST"])
@login_required
def delete(group_id):
    """Delete a group (creator only)"""
    group = Group.query.get_or_404(group_id)

    # Only the group creator can delete the group
    if group.creator_id != current_user.id:
        flash("Only the group creator can delete this group.", "error")
        return redirect(url_for("groups.index", group=group.slug))

    group_name = group.name

    try:
        # Delete admin actions associated with this group first
        from app.models import AdminAction

        AdminAction.query.filter_by(group_id=group_id).delete()

        # Delete all picks associated with this group (if per-group picks are enabled)
        Pick.query.filter_by(group_id=group_id).delete()

        # Delete the group (cascades to members and invites via SQLAlchemy relationships)
        db.session.delete(group)
        db.session.commit()

        flash(f'Group "{group_name}" has been permanently deleted.', "success")
        logger.info(
            f"Group {group_id} ({group_name}) deleted by user {current_user.id}"
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting group {group_id}: {e}")
        flash("An error occurred while deleting the group. Please try again.", "error")
        return redirect(url_for("groups.index"))

    # Get user's remaining groups to redirect to the latest one (or none if no groups left)
    remaining_groups = current_user.get_groups()
    if remaining_groups:
        # Redirect to the latest group (last in list)
        latest_group_slug = remaining_groups[-1].slug
        return redirect(url_for("groups.index", group=latest_group_slug))
    else:
        # No groups left, redirect to groups index without slug
        return redirect(url_for("groups.index"))


@bp.route("/<int:group_id>/toggle-active", methods=["POST"])
@login_required
def toggle_active(group_id):
    """Toggle group active status (disable/enable) - Creator only"""
    group = Group.query.get_or_404(group_id)

    # Only the group creator can disable/enable the group
    if group.creator_id != current_user.id:
        flash("Only the group creator can disable or enable this group.", "error")
        return redirect(url_for("groups.detail", group_id=group_id))

    # Toggle the is_active status
    group.is_active = not group.is_active
    action = "disabled" if not group.is_active else "enabled"

    try:
        # Log the action
        from app.models import AdminAction

        action_details = (
            f"Group {'disabled' if not group.is_active else 're-enabled'} by creator"
        )
        AdminAction.log_action(
            admin_user=current_user,
            action_type="group_disabled" if not group.is_active else "group_enabled",
            group=group,
            details=action_details,
        )

        db.session.commit()
        flash(f'Group "{group.name}" has been {action}.', "success")
        logger.info(
            f"Group {group_id} ({group.name}) {action} by user {current_user.id}"
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling group {group_id} active status: {e}")
        flash("An error occurred. Please try again.", "error")

    # If disabling, redirect to groups index; if enabling, stay on group page
    if not group.is_active:
        # Get user's remaining active groups
        remaining_groups = [g for g in current_user.get_groups() if g.is_active]
        if remaining_groups:
            return redirect(url_for("groups.index", group=remaining_groups[-1].slug))
        else:
            return redirect(url_for("groups.index"))
    else:
        return redirect(url_for("groups.detail", group_id=group_id))


@bp.route("/<int:group_id>/member/<int:user_id>/promote", methods=["POST"])
@login_required
def promote_member(group_id, user_id):
    """Promote member to admin"""
    group = Group.query.get_or_404(group_id)

    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    member = GroupMember.query.filter_by(
        group_id=group_id, user_id=user_id, is_active=True
    ).first()

    if not member:
        return jsonify({"error": "Member not found"}), 404

    member.promote_to_admin()

    # Log the action
    AdminAction.log_member_promotion(current_user, member.user, group)

    db.session.commit()

    return jsonify({"message": f"{member.user.username} promoted to admin"})


@bp.route("/<int:group_id>/member/<int:user_id>/demote", methods=["POST"])
@login_required
def demote_member(group_id, user_id):
    """Demote admin to regular member"""
    group = Group.query.get_or_404(group_id)

    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    # Don't allow demoting the group creator
    if group.creator_id == user_id:
        return jsonify({"error": "Cannot demote group creator"}), 400

    member = GroupMember.query.filter_by(
        group_id=group_id, user_id=user_id, is_active=True
    ).first()

    if not member:
        return jsonify({"error": "Member not found"}), 404

    member.demote_from_admin()

    # Log the action
    AdminAction.log_member_demotion(current_user, member.user, group)

    db.session.commit()

    return jsonify({"message": f"{member.user.username} demoted to regular member"})


@bp.route("/<int:group_id>/member/<int:user_id>/remove", methods=["POST"])
@login_required
def remove_member(group_id, user_id):
    """Remove member from group"""
    group = Group.query.get_or_404(group_id)

    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    # Don't allow removing the group creator
    if group.creator_id == user_id:
        return jsonify({"error": "Cannot remove group creator"}), 400

    # Get user info before removal for logging
    target_user = User.query.get(user_id)

    success, message = group.remove_member(user_id)

    if success:
        # Log the action
        if target_user:
            AdminAction.log_member_removal(current_user, target_user, group)

        db.session.commit()
        return jsonify({"message": message})
    else:
        return jsonify({"error": message}), 400


@bp.route("/<int:group_id>/admin/picks", methods=["GET", "POST"])
@login_required
def admin_picks(group_id):
    """Admin interface for managing picks"""
    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        flash("You do not have permission to manage picks for this group.", "error")
        return redirect(url_for("groups.index", group=group.slug))

    current_season = Season.get_current_season()
    if not current_season:
        flash("No active season found.", "error")
        return redirect(url_for("groups.index", group=group.slug))

    form = AdminPickForm()

    # Populate form choices - eager load users to avoid N+1 queries
    from sqlalchemy.orm import joinedload

    members = (
        GroupMember.query.filter_by(group_id=group_id, is_active=True)
        .options(joinedload(GroupMember.user))
        .all()
    )

    form.user_id.choices = [(m.user_id, m.user.username) for m in members]

    # Get weeks with games
    weeks_with_games = (
        db.session.query(Game.week)
        .filter_by(season_id=current_season.id)
        .distinct()
        .order_by(Game.week)
        .all()
    )
    form.week.choices = [(w[0], f"Week {w[0]}") for w in weeks_with_games]

    if form.validate_on_submit():
        user_id = form.user_id.data
        week = form.week.data
        game_id = form.game_id.data
        team_id = form.team_id.data
        admin_override = form.admin_override.data

        logger.info(
            f"Admin pick submission: user_id={user_id}, week={week}, game_id={game_id}, team_id={team_id}, override={admin_override}"
        )

        target_user = User.query.get(user_id)
        game = Game.query.options(
            db.joinedload(Game.home_team),
            db.joinedload(Game.away_team)
        ).get(game_id)

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not all([target_user, game]):
            error_msg = "Invalid selection. Please try again."
            if not is_ajax:
                flash(error_msg, "error")
            logger.warning(
                f"Invalid selection: target_user={target_user}, game={game}, team_id={team_id}"
            )
            if is_ajax:
                return jsonify({"success": False, "error": error_msg})
            return redirect(url_for("groups.admin_picks", group_id=group_id))
        
        # Validate team exists in game (use preloaded relationships)
        if team_id not in [game.home_team_id, game.away_team_id]:
            error_msg = "Team is not playing in this game."
            if not is_ajax:
                flash(error_msg, "error")
            logger.warning(f"Team {team_id} not in game {game_id}")
            if is_ajax:
                return jsonify({"success": False, "error": error_msg})
            return redirect(url_for("groups.admin_picks", group_id=group_id))

        # Check if user already has a pick for this week
        existing_pick = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == user_id,
                Pick.season_id == current_season.id,
                Game.week == week,
            )
            .first()
        )

        success_msg = None
        error_msg = None

        if existing_pick:
            # Update existing pick
            old_team = existing_pick.selected_team
            old_game = existing_pick.game

            # Update pick with new selection
            existing_pick.selected_team_id = team_id
            existing_pick.game_id = game_id

            # Validate the updated pick unless admin override is enabled
            if not admin_override:
                is_valid, validation_message = existing_pick.is_valid_pick()
                if not is_valid:
                    # Rollback the temporary changes
                    db.session.rollback()
                    error_msg = f"Cannot update pick: {validation_message}"
                    if not is_ajax:
                        flash(error_msg, "error")
                    logger.warning(f"Pick validation failed: {validation_message}")
                    if is_ajax:
                        return jsonify({"success": False, "error": error_msg})
                    return redirect(url_for("groups.admin_picks", group_id=group_id))

            # Validation passed or admin override enabled - commit the update

            # If game is already final, immediately calculate result
            if game.is_final:
                existing_pick.update_result()
                logger.info(
                    f"Updated pick for final game - auto-scored: is_correct={existing_pick.is_correct}, points={existing_pick.points_earned}"
                )

            # Log the update
            AdminAction.log_pick_update(
                current_user,
                target_user,
                group,
                type("obj", (object,), {"selected_team": old_team})(),
                existing_pick,
            )

            db.session.commit()
            override_note = " (admin override)" if admin_override else ""
            success_msg = f"Pick updated{override_note}: {old_team.abbreviation} ({old_game.away_team.abbreviation} @ {old_game.home_team.abbreviation}) → {team.abbreviation} ({game.away_team.abbreviation} @ {game.home_team.abbreviation})"
            if not is_ajax:
                flash(success_msg, "success")
            logger.info(
                f"Successfully updated pick: user_id={user_id}, week={week}, game_id={game_id}, team_id={team_id}, override={admin_override}"
            )
        else:
            # Create new pick
            if admin_override:
                # Admin override: create pick directly without validation
                # Set group_id based on user's picks_are_global setting
                pick_group_id = None if target_user.picks_are_global else group_id

                # Check if user already has a pick for this week (handle switching)
                existing_week_pick = (
                    Pick.query.join(Game)
                    .filter(
                        Pick.user_id == user_id,
                        Pick.season_id == current_season.id,
                        Game.week == week,
                    )
                    .first()
                )

                if existing_week_pick:
                    # Delete existing pick to allow switching
                    db.session.delete(existing_week_pick)
                    db.session.flush()

                pick = Pick(
                    user_id=user_id,
                    game_id=game_id,
                    season_id=current_season.id,
                    selected_team_id=team_id,
                    group_id=pick_group_id,
                )
                db.session.add(pick)
                db.session.flush()

                # If game is already final, immediately calculate result
                if game.is_final:
                    pick.update_result()
                    logger.info(
                        f"Game already final - auto-scored pick: is_correct={pick.is_correct}, points={pick.points_earned}"
                    )

                # Log the creation
                AdminAction.log_pick_creation(
                    current_user,
                    target_user,
                    group,
                    pick,
                    f"Created pick with admin override for {target_user.username}: {team.abbreviation} in Week {week}",
                )

                db.session.commit()
                success_msg = f"Pick created: {team.abbreviation} (Week {week})"
                if not is_ajax:
                    flash(success_msg, "success")
                logger.info(
                    f"Successfully created pick with override: user_id={user_id}, week={week}, team_id={team_id}"
                )
            else:
                # Use normal validation
                pick, message = Pick.create_pick(user_id, game_id, team_id)
                if pick:
                    # If game is already final, immediately calculate result
                    if game.is_final:
                        pick.update_result()
                        logger.info(
                            f"Game already final - auto-scored pick: is_correct={pick.is_correct}, points={pick.points_earned}"
                        )

                    # Log the creation
                    AdminAction.log_pick_creation(
                        current_user, target_user, group, pick
                    )

                    db.session.commit()
                    success_msg = f"Pick created: {team.abbreviation} (Week {week})"
                    if not is_ajax:
                        flash(success_msg, "success")
                    logger.info(
                        f"Successfully created pick: user_id={user_id}, week={week}, team_id={team_id}"
                    )
                else:
                    error_msg = message
                    if not is_ajax:
                        flash(f"Error creating pick: {message}", "error")

        # Return JSON for AJAX requests
        if is_ajax:
            if success_msg:
                return jsonify({"success": True, "message": success_msg})
            else:
                return jsonify(
                    {"success": False, "error": error_msg or "Unknown error"}
                )

        return redirect(url_for("groups.admin_picks", group_id=group_id))

    # Log form validation errors if form was submitted but didn't validate
    if request.method == "POST" and not form.validate_on_submit():
        logger.warning(f"Form validation failed. Errors: {form.errors}")
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "error")

    # Get all picks for the group by week (optimized single query with eager loading)
    from sqlalchemy.orm import joinedload

    # Expire all cached objects to force fresh data from database
    db.session.expire_all()

    member_ids = [m.user_id for m in members]
    logger.info(
        f"Loading picks for admin_picks page: group_id={group_id}, member_ids={member_ids}"
    )

    all_picks = (
        Pick.query.join(Game)
        .filter(Pick.user_id.in_(member_ids), Pick.season_id == current_season.id)
        .options(joinedload(Pick.game), joinedload(Pick.selected_team))
        .order_by(Game.week)
        .all()
    )

    logger.info(f"Found {len(all_picks)} total picks for display")

    # Organize picks by week and user
    picks_by_week = {}
    for pick in all_picks:
        week = pick.week
        if week not in picks_by_week:
            picks_by_week[week] = {}
        picks_by_week[week][pick.user_id] = pick

    logger.info(f"Organized picks: {len(picks_by_week)} weeks with picks")

    # Create response with no-cache headers
    response = make_response(
        render_template(
            "groups/admin_picks.html",
            form=form,
            group=group,
            members=members,
            current_season=current_season,
            picks_by_week=picks_by_week,
            weeks_with_games=[w[0] for w in weeks_with_games],
        )
    )

    # Prevent browser caching of this page
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@bp.route("/<int:group_id>/admin/picks/user/<int:user_id>")
@login_required
def admin_picks_user_data(group_id, user_id):
    """AJAX endpoint to get user's existing picks and used teams"""
    logger.info(f"admin_picks_user_data called: group_id={group_id}, user_id={user_id}")

    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season"}), 400

    # Get all picks for this user in this season
    user_picks = (
        Pick.query.join(Game)
        .filter(Pick.user_id == user_id, Pick.season_id == current_season.id)
        .options(joinedload(Pick.game), joinedload(Pick.selected_team))
        .all()
    )

    # Organize by week and get used team IDs
    picks_by_week = {}
    used_team_ids = set()

    for pick in user_picks:
        game = pick.game
        picks_by_week[game.week] = {
            "id": pick.id,
            "pick_id": pick.id,
            "game_id": pick.game_id,
            "team_id": pick.selected_team_id,
            "team": pick.selected_team.abbreviation,  # For display in table
            "team_name": pick.selected_team.full_name,
            "team_abbr": pick.selected_team.abbreviation,
            "game": f"{game.away_team.abbreviation} @ {game.home_team.abbreviation}",  # For display in table
            "is_correct": pick.is_correct,
        }
        # Only add to used_team_ids if it's a regular season pick (weeks 1-18)
        # Playoffs (weeks 19+) allow team reuse
        if game.week <= current_season.regular_season_weeks:
            used_team_ids.add(pick.selected_team_id)

    return jsonify(
        {"picks_by_week": picks_by_week, "used_team_ids": list(used_team_ids)}
    )


@bp.route("/<int:group_id>/admin/picks/games/<int:week>")
@login_required
def admin_picks_games(group_id, week):
    """AJAX endpoint to get games for a specific week"""
    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season"}), 400

    games = (
        Game.query.filter_by(season_id=current_season.id, week=week)
        .order_by(Game.game_time)
        .all()
    )

    games_data = []
    for game in games:
        games_data.append(
            {
                "id": game.id,
                "text": f"{game.away_team.abbreviation} @ {game.home_team.abbreviation} - {game.game_time.strftime('%a %m/%d %I:%M %p')}",
            }
        )

    return jsonify(games_data)


@bp.route("/<int:group_id>/admin/picks/teams/<int:game_id>")
@login_required
def admin_picks_teams(group_id, game_id):
    """AJAX endpoint to get teams for a specific game"""
    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    game = Game.query.get_or_404(game_id)

    teams_data = [
        {
            "id": game.away_team.id,
            "text": f"{game.away_team.abbreviation} - {game.away_team.name}",
        },
        {
            "id": game.home_team.id,
            "text": f"{game.home_team.abbreviation} - {game.home_team.name}",
        },
    ]

    return jsonify(teams_data)


@bp.route("/<int:group_id>/admin/picks/delete/<int:pick_id>", methods=["POST"])
@login_required
def admin_delete_pick(group_id, pick_id):
    """Delete a pick (admin only)"""
    group = Group.query.get_or_404(group_id)

    # Check if user is admin
    if not group.is_user_admin(current_user.id):
        return jsonify({"error": "Permission denied"}), 403

    pick = Pick.query.get_or_404(pick_id)
    target_user = User.query.get(pick.user_id)

    # Log the deletion before deleting the pick
    AdminAction.log_pick_deletion(current_user, target_user, group, pick)

    db.session.delete(pick)
    db.session.commit()

    return jsonify(
        {
            "message": f"Deleted pick for {target_user.username}: {pick.selected_team.abbreviation} (Week {pick.week})"
        }
    )


@bp.route("/<int:group_id>/admin/audit")
@login_required
def admin_audit(group_id):
    """View audit log for group"""
    group = Group.query.get_or_404(group_id)

    # Check if user is a member (audit log is visible to all members)
    if not group.is_user_member(current_user.id):
        flash("You are not a member of this group.", "error")
        return redirect(url_for("groups.index"))

    page = request.args.get("page", 1, type=int)
    per_page = 50

    # Get audit actions for this group
    actions = (
        AdminAction.query.filter_by(group_id=group_id)
        .order_by(AdminAction.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("groups/admin_audit.html", group=group, actions=actions)
