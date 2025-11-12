import logging
import os
from datetime import datetime, timezone

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app import db, limiter
from app.models import Game, Group, GroupMember, Pick, Season, Team, User
from app.routes.main import bp

logger = logging.getLogger(__name__)


# Helper functions for current_picks route
def _get_user_group_context(user, group_slug=None):
    """Get group context for picks page

    Returns:
        tuple: (current_group, user_groups) or (None, []) if no groups
    """
    user_groups = user.get_groups()
    if not user_groups:
        return None, []

    # Find group by slug or use latest
    current_group = None
    if group_slug:
        current_group = next((g for g in user_groups if g.slug == group_slug), None)

    if not current_group:
        current_group = user_groups[-1]

    return current_group, user_groups


def _get_admin_selected_user(admin_user, user_id_param):
    """Get target user for admin override

    Returns:
        tuple: (selected_user, all_users, admin_override_flag)
    """
    if not admin_user.is_admin:
        return admin_user, [], False

    selected_user = admin_user
    if user_id_param:
        user = User.query.get(user_id_param)
        if user:
            selected_user = user
        else:
            flash("Selected user not found.", "error")

    all_users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return selected_user, all_users, True


def _get_user_picks_for_week(user, game_ids, group_id=None):
    """Query user's existing picks for given games

    Args:
        user: User object
        game_ids: List of game IDs to query
        group_id: Optional group_id (respects user.picks_are_global)

    Returns:
        dict: {game_id: Pick} mapping
    """
    if not game_ids:
        return {}

    picks_query = Pick.query.filter(
        Pick.user_id == user.id, Pick.game_id.in_(game_ids)
    )

    # Use helper method for group filtering
    effective_group_id = user.get_group_id_for_filtering(group_id)
    if effective_group_id is not None:
        picks_query = picks_query.filter(Pick.group_id == effective_group_id)

    picks_list = picks_query.options(db.joinedload(Pick.selected_team)).all()
    return {pick.game_id: pick for pick in picks_list}


def _calculate_team_availability(
    user, games, current_week, season, group_id, user_picks, is_admin=False
):
    """Calculate which teams are available for picking

    Args:
        user: User making picks
        games: List of Game objects
        current_week: Current week number
        season: Season object
        group_id: Group ID for rule checking (respects user.picks_are_global)
        user_picks: Dict of existing picks {game_id: Pick}
        is_admin: Admin override flag

    Returns:
        dict: {team_id: {"can_pick": bool, "reason": str}}
    """
    available_teams = {}
    effective_group_id = user.get_group_id_for_filtering(group_id)

    # Get previous week's pick for consecutive opponent check
    prev_week_pick = None
    if current_week > 1 and not season.is_playoff_week(current_week):
        pick_filter = [
            Pick.user_id == user.id,
            Pick.season_id == season.id,
        ]
        if effective_group_id is not None:
            pick_filter.append(Pick.group_id == effective_group_id)
        else:
            pick_filter.append(Pick.group_id.is_(None))

        prev_week_pick = (
            Pick.query.join(Game)
            .filter(*pick_filter, Game.week == current_week - 1)
            .first()
        )

    for game in games:
        existing_pick = user_picks.get(game.id)
        exclude_pick_id = existing_pick.id if existing_pick else None

        for team in [game.home_team, game.away_team]:
            # Game started check (admin override)
            if not game.is_pickable() and not is_admin:
                available_teams[team.id] = {
                    "can_pick": False,
                    "reason": "Game has started",
                }
                continue

            # Standard rule checking
            can_pick, reason = user.can_pick_team(
                team.id,
                current_week,
                season.id,
                group_id=effective_group_id,
                exclude_pick_id=exclude_pick_id,
            )

            # Consecutive opponent check (regular season only)
            if (
                can_pick
                and prev_week_pick
                and not season.is_playoff_week(current_week)
            ):
                opponent_id = (
                    game.home_team.id if team.id == game.away_team.id else game.away_team.id
                )
                prev_game = prev_week_pick.game

                if opponent_id in [prev_game.home_team_id, prev_game.away_team_id]:
                    # Use preloaded team objects instead of querying
                    opponent_team = game.home_team if opponent_id == game.home_team_id else game.away_team
                    can_pick = False
                    reason = f"{opponent_team.abbreviation} was involved in your week {current_week - 1} pick"

            available_teams[team.id] = {"can_pick": can_pick, "reason": reason}

    return available_teams


def _get_other_users_picks(group, games, exclude_user_id):
    """Get other group members' picks for comparison

    Args:
        group: Group object
        games: List of Game objects
        exclude_user_id: User ID to exclude (current user)

    Returns:
        dict: {user_id: {"user": User, "picks": {game_id: Pick}}}
    """
    if not games or not group:
        return {}

    # Get group members excluding current user
    group_members = [
        membership.user
        for membership in group.members
        if membership.user.id != exclude_user_id
    ]

    if not group_members:
        return {}

    game_ids = [game.id for game in games]
    group_picks_query = db.session.query(Pick).filter(
        Pick.game_id.in_(game_ids),
        Pick.user_id.in_([user.id for user in group_members]),
        db.or_(
            Pick.group_id == group.id,  # Per-group picks
            Pick.group_id.is_(None),  # Global picks
        ),
    )

    group_picks = group_picks_query.options(
        db.joinedload(Pick.user), db.joinedload(Pick.selected_team)
    ).all()

    # Organize by user and game
    other_users_picks = {}
    for pick in group_picks:
        if pick.user_id not in other_users_picks:
            other_users_picks[pick.user_id] = {"user": pick.user, "picks": {}}
        other_users_picks[pick.user_id]["picks"][pick.game_id] = pick

    return other_users_picks


@bp.route("/")
def index():
    """Home page - simplified pick interface for authenticated users"""
    if current_user.is_authenticated:
        # Get group parameter from query string
        group_slug = request.args.get("group")

        # If no group specified, use the latest group as default
        if not group_slug:
            user_groups = current_user.get_groups()
            if user_groups:
                group_slug = user_groups[-1].slug

        # Redirect with group parameter if available
        if group_slug:
            return redirect(url_for("main.current_picks", group=group_slug))
        return redirect(url_for("main.current_picks"))

    # Get some stats for the homepage
    stats = {
        "total_users": User.query.filter_by(is_active=True).count(),
        "total_groups": Group.query.filter_by(is_active=True).count(),
        "current_season": Season.get_current_season(),
    }

    return render_template("main/index.html", stats=stats)


@bp.route("/picks")
@login_required
def current_picks():
    """Simplified current game week picks interface"""
    # Get group context
    current_group, user_groups = _get_user_group_context(
        current_user, request.args.get("group")
    )
    if not current_group:
        flash("You need to join or create a group before you can make picks!", "info")
        return redirect(url_for("groups.index"))

    # Get admin-selected user if applicable
    selected_user, all_users, admin_override = _get_admin_selected_user(
        current_user, request.args.get("user_id", type=int)
    )

    # Get current season
    current_season = Season.get_current_season()

    if not current_season:
        flash(
            "No active NFL season found. Please check back during the NFL season.",
            "warning",
        )
        return render_template("main/no_season.html")

    # Get week from query parameter or use current week
    requested_week = request.args.get("week", type=int)
    if requested_week and 1 <= requested_week <= (
        current_season.regular_season_weeks + current_season.playoff_weeks
    ):
        current_week = requested_week
    else:
        # Auto-calculate and update the current week based on game schedule
        current_week = current_season.update_current_week()

    # Get games for current week
    current_games = Game.get_games_for_week(current_season.id, current_week)

    # Get user's existing picks using helper
    game_ids = [game.id for game in current_games] if current_games else []
    user_picks = _get_user_picks_for_week(selected_user, game_ids, current_group.id)

    # Get pickable games (admin override allows all)
    pickable_games = current_games
    completed_games = [] if admin_override else [g for g in current_games if not g.is_pickable()]

    # Get user stats
    effective_group_id = selected_user.get_group_id_for_filtering(current_group.id)
    user_season_stats = selected_user.get_season_stats(current_season.id, group_id=effective_group_id)

    if user_season_stats:
        stats = user_season_stats["total"]
        stats["regular_season"] = user_season_stats["regular_season"]
        stats["playoffs"] = user_season_stats["playoffs"]
    else:
        stats = {
            "wins": 0,
            "completed_picks": 0,
            "total_picks": 0,
            "tiebreaker_points": 0,
            "accuracy": 0,
            "current_streak": 0,
            "regular_season": {"wins": 0, "total_picks": 0, "tiebreaker_points": 0},
            "playoffs": {"wins": 0, "total_picks": 0, "tiebreaker_points": 0},
        }

    # Get used teams and calculate availability
    used_teams = selected_user.get_used_teams_this_season(current_season.id, group_id=effective_group_id)
    used_team_ids = [team.id for team in used_teams]

    available_teams = _calculate_team_availability(
        selected_user,
        pickable_games,
        current_week,
        current_season,
        current_group.id,
        user_picks,
        admin_override,
    )

    # Check playoff eligibility
    playoff_eligible, playoff_status = selected_user.is_playoff_eligible(
        current_season.id, group_id=effective_group_id
    )

    # Get admin-only data
    all_weeks = current_season.get_weeks() if admin_override else []

    # Get other users' picks for comparison
    other_users_picks = _get_other_users_picks(current_group, current_games, selected_user.id)

    return render_template(
        "main/current_picks.html",
        season=current_season,
        current_week=current_week,
        current_group=current_group,
        user_groups=user_groups,
        pickable_games=pickable_games,
        completed_games=completed_games,
        user_picks=user_picks,
        stats=stats,
        used_teams=used_teams,
        used_team_ids=used_team_ids,
        available_teams=available_teams,
        playoff_eligible=playoff_eligible,
        playoff_status=playoff_status,
        admin_override=admin_override,
        selected_user=selected_user,
        all_users=all_users,
        all_weeks=all_weeks,
        other_users_picks=other_users_picks,
    )


def _process_single_pick(
    target_user, game_id, team_id, current_season, is_admin, current_group=None
):
    """Helper function to process a single pick submission"""
    from app.models.team import Team

    # Validate inputs
    if not target_user or not current_season:
        return False, "Invalid user or season"

    # Determine group_id based on user's picks_are_global setting
    group_id = (
        None
        if target_user.picks_are_global
        else (current_group.id if current_group else None)
    )

    # Get the game and validate it's pickable (or admin override)
    game = Game.query.get(game_id)
    if not game:
        return False, "Game not found"

    # Validate game belongs to current season
    if game.season_id != current_season.id:
        return False, "Game does not belong to current season"

    # Validate team exists in this game (using preloaded relationships)
    if team_id not in [game.home_team_id, game.away_team_id]:
        return False, "Team is not playing in this game"

    # Allow admins to edit any game, otherwise check if pickable
    if not is_admin and not game.is_pickable():
        return False, "Game no longer available for picks"

    # Check if target user already has a pick for this game (and group if applicable)
    existing_pick_query = Pick.query.filter_by(user_id=target_user.id, game_id=game_id)
    if group_id is not None:
        existing_pick_query = existing_pick_query.filter_by(group_id=group_id)
    else:
        existing_pick_query = existing_pick_query.filter_by(group_id=None)
    existing_pick = existing_pick_query.first()

    # Check if user already has a pick for a DIFFERENT game in this week
    existing_week_pick_query = Pick.query.join(Game).filter(
        Pick.user_id == target_user.id,
        Pick.season_id == current_season.id,
        Game.week == game.week,
        Pick.game_id != game_id,  # Different game
    )
    if group_id is not None:
        existing_week_pick_query = existing_week_pick_query.filter(
            Pick.group_id == group_id
        )
    else:
        existing_week_pick_query = existing_week_pick_query.filter(
            Pick.group_id.is_(None)
        )
    existing_week_pick = existing_week_pick_query.first()

    # Determine which pick to exclude from validation
    exclude_pick_id = None
    if existing_pick:
        # Updating same game - exclude this pick from validation
        exclude_pick_id = existing_pick.id
    elif existing_week_pick:
        # Switching to different game - exclude the old week pick from validation
        exclude_pick_id = existing_week_pick.id

    # Validate the pick (unless admin)
    if not is_admin:
        can_pick, reason = target_user.can_pick_team(
            team_id,
            game.week,
            current_season.id,
            group_id=group_id,
            exclude_pick_id=exclude_pick_id,
        )
        if not can_pick:
            # Use preloaded team relationships instead of additional query
            team_name = (
                game.home_team.abbreviation if team_id == game.home_team_id 
                else game.away_team.abbreviation if team_id == game.away_team_id
                else "Unknown"
            )
            return False, f"Cannot pick {team_name}: {reason}"

        # Additional validation: Check if opponent was picked in consecutive week (new rule for regular season only)
        season = Season.query.get(current_season.id)
        if season and not season.is_playoff_week(game.week):
            # Determine the opponent team for THIS pick
            opponent_id = (
                game.home_team_id if team_id == game.away_team_id else game.away_team_id
            )

            # Build pick filter for user's previous week pick
            pick_filter = [
                Pick.user_id == target_user.id,
                Pick.season_id == current_season.id,
            ]
            if not target_user.picks_are_global:
                pick_filter.append(Pick.group_id == group_id)
            else:
                pick_filter.append(Pick.group_id.is_(None))
            if exclude_pick_id:
                pick_filter.append(Pick.id != exclude_pick_id)

            # Check if user picked a game involving the opponent in the PREVIOUS week (consecutive check)
            if game.week > 1:
                prev_week_pick = (
                    Pick.query.join(Game)
                    .filter(*pick_filter, Game.week == game.week - 1)
                    .first()
                )

                if prev_week_pick:
                    # Check if opponent was involved in previous week's game (as either home or away team)
                    # This checks BOTH: if they picked this team OR if this team was their opponent
                    prev_game = prev_week_pick.game
                    if opponent_id in [prev_game.home_team_id, prev_game.away_team_id]:
                        # Use preloaded team objects instead of query
                        opponent_team = game.home_team if opponent_id == game.home_team_id else game.away_team
                        return (
                            False,
                            f"Cannot pick this game: {opponent_team.abbreviation} was involved in your week {game.week - 1} pick (consecutive weeks not allowed)",
                        )

    # If user has a pick for a different game this week, delete it (switching picks)
    if existing_week_pick and not is_admin:
        # Check if the old pick's game has already started
        if existing_week_pick.game.has_started():
            return (
                False,
                f"Cannot switch pick: Your current pick ({existing_week_pick.game.away_team.abbreviation} vs {existing_week_pick.game.home_team.abbreviation}) has already started",
            )
        else:
            # Delete the old pick to allow switching
            logger.debug(
                f"Deleting old pick for game {existing_week_pick.game_id} to switch to game {game_id}"
            )
            db.session.delete(existing_week_pick)

    if existing_pick:
        # Update existing pick
        existing_pick.selected_team_id = team_id
        existing_pick.game_id = game_id  # Update game as well
        existing_pick.group_id = group_id  # Update group_id
        existing_pick.updated_at = datetime.now(timezone.utc)
        return True, "Pick updated"
    else:
        # Create new pick (validation already done above)
        logger.debug(
            f"Creating pick for user {target_user.username}, game {game_id}, team {team_id}, group {group_id}"
        )

        pick = Pick(
            user_id=target_user.id,
            game_id=game_id,
            selected_team_id=team_id,
            season_id=current_season.id,
            group_id=group_id,
        )
        db.session.add(pick)
        logger.debug("Pick created successfully")
        return True, "Pick created"


@bp.route("/submit-picks", methods=["POST"])
@login_required
def submit_picks():
    """Submit picks for current game week"""
    current_season = Season.get_current_season()
    if not current_season:
        flash("No active season found.", "error")
        return redirect(url_for("main.index"))

    # Get current group from query parameter or session
    current_group = None
    group_slug = request.args.get("group") or request.form.get("group")
    if group_slug:
        current_group = Group.query.filter_by(slug=group_slug).first()

    # If no group specified, use user's latest group
    if not current_group:
        user_groups = current_user.get_groups()
        if user_groups:
            current_group = user_groups[-1]

    # Admin functionality: determine target user for picks
    target_user = current_user  # Default to current user
    if current_user.is_admin:
        selected_user_id = request.form.get("selected_user_id", type=int)
        if selected_user_id:
            target_user = User.query.get(selected_user_id)
            if not target_user:
                flash("Selected user not found.", "error")
                return redirect(url_for("main.current_picks"))

    picks_saved = 0
    errors = []

    try:
        # Process each pick from the form
        for key, value in request.form.items():
            if key.startswith("pick_"):
                try:
                    game_id = int(key.replace("pick_", ""))
                    team_id = int(value)

                    success, message = _process_single_pick(
                        target_user,
                        game_id,
                        team_id,
                        current_season,
                        current_user.is_admin,
                        current_group,
                    )

                    if success:
                        picks_saved += 1
                    else:
                        errors.append(message)

                except (ValueError, TypeError) as e:
                    errors.append(f"Invalid data for pick: {str(e)}")
                    continue

        # Commit all changes if we have any successful picks
        if picks_saved > 0:
            logger.debug(f"Committing {picks_saved} picks to database")
            try:
                db.session.commit()
                # Force session refresh to ensure subsequent queries see new data
                db.session.expire_all()
                logger.debug("Session expired, cache invalidated")
                # Clear any cache that might affect leaderboard calculations
                from app.utils.cache_utils import invalidate_model_cache

                invalidate_model_cache("pick")
                invalidate_model_cache("user")
            except Exception as commit_error:
                logger.error(f"Error during commit: {commit_error}")
                db.session.rollback()
                raise
        else:
            logger.debug("No picks to save, rolling back")
            db.session.rollback()

    except Exception as e:
        db.session.rollback()
        error_msg = f"An error occurred while saving picks: {str(e)}"
        # Check if this is an AJAX request
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            return jsonify({"success": False, "error": error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for("main.current_picks"))

    # Check if this is an AJAX request
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # For AJAX requests, return JSON
    if is_ajax:
        if picks_saved > 0:
            target_name = (
                target_user.username if target_user.id != current_user.id else "your"
            )
            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully saved {picks_saved} picks for {target_name}!",
                    "picks_saved": picks_saved,
                    "errors": errors[:5] if errors else [],
                }
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No picks were saved.",
                        "errors": errors[:5] if errors else [],
                    }
                ),
                400,
            )

    # For regular form submissions, use flash messages and redirect
    # Display errors
    for error in errors[:5]:  # Limit to 5 errors to avoid overwhelming the user
        flash(error, "error")

    # Prepare redirect parameters to maintain admin context and group
    redirect_params = {}
    if current_user.is_admin and target_user.id != current_user.id:
        redirect_params["user_id"] = target_user.id
    if request.form.get("week"):
        redirect_params["week"] = request.form.get("week")
    if current_group:
        redirect_params["group"] = current_group.slug

    if picks_saved > 0:
        target_name = (
            target_user.username if target_user.id != current_user.id else "your"
        )
        flash(f"Successfully saved {picks_saved} picks for {target_name}!", "success")
    else:
        flash("No picks were saved.", "info")

    # Redirect back to picks page with parameters
    if redirect_params:
        return redirect(url_for("main.current_picks", **redirect_params))
    else:
        return redirect(url_for("main.current_picks"))


@bp.route("/dashboard")
@login_required
def dashboard():
    """User dashboard"""
    # Get user's groups
    user_groups = current_user.get_groups()

    # If user has no groups, redirect them to group setup
    if not user_groups:
        flash(
            "Welcome! To start making picks, you need to join or create a group first.",
            "info",
        )
        return redirect(url_for("groups.index"))

    # Get current season
    current_season = Season.get_current_season()

    # Get selected group from URL parameter or default to first group
    group_slug = request.args.get("group")
    selected_group = None
    if group_slug:
        selected_group = next((g for g in user_groups if g.slug == group_slug), None)
    if not selected_group and user_groups:
        selected_group = user_groups[-1]

    # Get leaderboard for selected group
    leaderboard = []
    if selected_group and current_season:
        leaderboard = User.get_season_leaderboard(
            current_season.id, regular_season_only=False, group_id=selected_group.id
        )

    # Get user's season stats
    user_stats = None
    if current_season:
        # Get stats for selected group if user has per-group picks
        group_id_for_stats = (
            selected_group.id
            if (selected_group and not current_user.picks_are_global)
            else None
        )
        user_stats = current_user.get_season_stats(
            current_season.id, group_id=group_id_for_stats
        )

    # Get user's picks for current season
    current_picks = []
    if current_season:
        current_picks = current_user.get_picks_for_season(current_season.id)

    # Get upcoming games for current week
    upcoming_games = []
    if current_season:
        upcoming_games = Game.get_current_week_games(current_season.id)
        # Filter to games that haven't started
        upcoming_games = [game for game in upcoming_games if game.is_pickable()]

    # Get user's recent activity
    recent_picks = (
        Pick.query.filter_by(user_id=current_user.id)
        .order_by(Pick.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "main/dashboard.html",
        user_groups=user_groups,
        selected_group=selected_group,
        leaderboard=leaderboard,
        current_season=current_season,
        user_stats=user_stats,
        current_picks=current_picks,
        upcoming_games=upcoming_games,
        recent_picks=recent_picks,
    )


@bp.route("/seasons")
@login_required
def seasons():
    """List all seasons"""
    all_seasons = Season.query.order_by(Season.year.desc()).all()
    return render_template("main/seasons.html", seasons=all_seasons)


@bp.route("/season/<int:season_id>")
@login_required
def season_detail(season_id):
    """Season detail page"""
    season = Season.query.get_or_404(season_id)

    # Get all weeks for this season
    weeks = season.get_weeks()

    # Get user's picks for this season
    user_picks = (
        current_user.get_picks_for_season(season_id)
        if current_user.is_authenticated
        else []
    )
    user_picks_by_week = {pick.week: pick for pick in user_picks}

    return render_template(
        "main/season_detail.html",
        season=season,
        weeks=weeks,
        user_picks_by_week=user_picks_by_week,
    )


@bp.route("/week/<int:season_id>/<int:week>")
@login_required
def week_detail(season_id, week):
    """Week detail page"""
    season = Season.query.get_or_404(season_id)

    # Validate week number
    max_week = season.regular_season_weeks + season.playoff_weeks
    if week < 1 or week > max_week:
        flash(f"Invalid week number. Must be between 1 and {max_week}.", "error")
        return redirect(url_for("main.season_detail", season_id=season_id))

    # Get games for this week
    games = Game.get_games_for_week(season_id, week)

    # Get user's pick for this week
    user_pick = (
        current_user.get_pick_for_week(season_id, week)
        if current_user.is_authenticated
        else None
    )

    # Get week info
    weeks = season.get_weeks()
    current_week_info = next((w for w in weeks if w["week"] == week), None)

    return render_template(
        "main/week_detail.html",
        season=season,
        week=week,
        week_info=current_week_info,
        games=games,
        user_pick=user_pick,
    )


@bp.route("/leaderboard")
@login_required
def leaderboard():
    """Global leaderboard page showing stats across all players and groups"""

    # Get filter parameters
    filter_type = request.args.get("filter", "all-time")  # 'all-time' or 'season'
    season_id = request.args.get("season_id", type=int)

    # Get all seasons for filter dropdown
    all_seasons = Season.query.order_by(Season.year.desc()).all()

    # If season filter is selected, use the specified season
    if filter_type == "season":
        if season_id:
            selected_season = Season.query.get(season_id)
        else:
            selected_season = Season.get_current_season()
            if selected_season:
                season_id = selected_season.id
    else:
        selected_season = None

    leaderboard_data = []

    if filter_type == "all-time":
        # Calculate all-time statistics for all users
        all_users = User.query.filter_by(is_active=True).all()

        for user in all_users:
            # Get all-time stats (season_id=None means all seasons)
            stats = user.get_season_stats(season_id=None, group_id=None)
            
            if stats["total_picks"] == 0:
                continue  # Skip users with no picks

            # Calculate all-time longest streak
            longest_streak = user.calculate_alltime_longest_streak()

            leaderboard_data.append(
                {
                    "user_id": user.id,
                    "user": user,
                    "total_score": stats["total_score"],  # Wins + (0.5 × ties)
                    "wins": stats["wins"],
                    "ties": stats["ties"],
                    "losses": stats["losses"],
                    "missed_games": stats["missed_games"],
                    "completed_picks": stats["completed_picks"],
                    "total_picks": stats["total_picks"],
                    "tiebreaker_points": stats["tiebreaker_points"],
                    "accuracy": stats["accuracy"],
                    "longest_streak": longest_streak,
                }
            )

    elif filter_type == "season" and selected_season:
        # Get season leaderboard (across all groups)
        leaderboard_data = User.get_season_leaderboard(
            selected_season.id,
            regular_season_only=False,
            group_id=None,  # None = all groups
        )

    # Sort by total_score (descending), then by tiebreaker points (descending)
    leaderboard_data.sort(
        key=lambda x: (x["total_score"], x["tiebreaker_points"]), reverse=True
    )

    return render_template(
        "main/leaderboard.html",
        leaderboard_data=leaderboard_data,
        filter_type=filter_type,
        selected_season=selected_season,
        all_seasons=all_seasons,
        season=selected_season,
        current_week=selected_season.current_week if selected_season else None,
        has_live_games=False,
    )


@bp.route("/about")
def about():
    """About page"""
    return render_template("main/about.html")


@bp.route("/contact")
def contact():
    """Contact page"""
    return render_template("main/contact.html")


@bp.route("/rules")
def rules():
    """Game rules page"""
    return render_template("main/rules.html")


@bp.route("/season/<int:season_id>/winners")
@login_required
def season_winners(season_id):
    """Display season winners and hall of fame"""
    from app.models import SeasonWinner

    season = Season.query.get_or_404(season_id)

    # Get global winners
    global_winners = SeasonWinner.get_season_awards(season_id, group_id=None)

    # Get user's group winners
    user_groups = current_user.get_groups()
    group_winners = {}

    for membership in user_groups:
        winners = SeasonWinner.get_season_awards(
            season_id, group_id=membership.group_id
        )
        if winners:
            group_winners[membership.group] = winners

    # Check if current user won any awards
    user_awards = [w for w in global_winners if w.user_id == current_user.id]
    for winners_list in group_winners.values():
        user_awards.extend([w for w in winners_list if w.user_id == current_user.id])

    return render_template(
        "main/season_winners.html",
        season=season,
        global_winners=global_winners,
        group_winners=group_winners,
        user_awards=user_awards,
    )


@bp.route("/hall-of-fame")
@login_required
def hall_of_fame():
    """Display all-time hall of fame"""
    from app.models import SeasonWinner

    # Get user's awards
    user_awards = SeasonWinner.get_user_awards(current_user.id)

    # Get all global champions
    all_champions = (
        SeasonWinner.query.filter_by(award_type="champion", group_id=None)
        .order_by(SeasonWinner.season_id.desc())
        .all()
    )

    # Count championships by user
    from collections import Counter

    championship_counts = Counter(c.user_id for c in all_champions)

    # Get top champions
    top_champions = []
    for user_id, count in championship_counts.most_common(10):
        user = User.query.get(user_id)
        if user:
            top_champions.append(
                {
                    "user": user,
                    "championships": count,
                    "awards": SeasonWinner.get_user_awards(user_id),
                }
            )

    return render_template(
        "main/hall_of_fame.html", user_awards=user_awards, top_champions=top_champions
    )


@bp.route("/offline")
def offline():
    """Offline page for PWA"""
    return render_template("offline.html")


@bp.route("/health")
@limiter.exempt
def health():
    """Health check endpoint - exempt from rate limiting for monitoring systems"""
    return jsonify(
        {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    )


@bp.route("/manifest.json")
def manifest():
    """Serve manifest.json with correct MIME type"""
    return send_from_directory(
        os.path.join(bp.root_path, "..", "static"),
        "manifest.json",
        mimetype="application/manifest+json",
    )


@bp.route("/sw.js")
def service_worker():
    """Serve service worker with correct MIME type"""
    return send_from_directory(
        os.path.join(bp.root_path, "..", "static"),
        "sw.js",
        mimetype="application/javascript",
    )


@bp.route("/search")
@login_required
def search():
    """Search functionality"""
    query = request.args.get("q", "").strip()

    if not query:
        return render_template("main/search_results.html", query="", results={})

    results = {"groups": [], "users": [], "games": []}

    # Search groups (public ones or ones user is member of)
    user_group_ids = [membership.group_id for membership in current_user.get_groups()]
    groups = (
        Group.query.filter(
            db.or_(Group.is_public.is_(True), Group.id.in_(user_group_ids)),
            Group.name.contains(query),
        )
        .limit(10)
        .all()
    )
    results["groups"] = groups

    # Search users (limit to users in same groups)
    if user_group_ids:
        users = (
            db.session.query(User)
            .join(GroupMember)
            .filter(
                GroupMember.group_id.in_(user_group_ids),
                db.or_(
                    User.username.contains(query), User.display_name.contains(query)
                ),
                User.id != current_user.id,
            )
            .distinct()
            .limit(10)
            .all()
        )
        results["users"] = users

    return render_template("main/search_results.html", query=query, results=results)


@bp.route("/admin/scheduler")
@login_required
def admin_scheduler():
    """Admin scheduler management dashboard"""
    # Check if user is admin
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.index"))

    from app.services.scheduler_service import scheduler_service

    # Get scheduler status
    status = scheduler_service.get_status()

    return render_template("main/admin_scheduler.html", scheduler_status=status)


@bp.route("/admin/scheduler/action", methods=["POST"])
@login_required
def admin_scheduler_action():
    """Handle admin scheduler actions"""
    # Check if user is admin
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    from app.services.scheduler_service import scheduler_service

    action = request.json.get("action")

    try:
        if action == "start":
            scheduler_service.start()
            return jsonify({"message": "Scheduler started successfully"})

        elif action == "stop":
            scheduler_service.stop()
            return jsonify({"message": "Scheduler stopped successfully"})

        elif action == "status":
            status = scheduler_service.get_status()
            return jsonify(status)

        elif action == "force_sync":
            sync_type = request.json.get("sync_type", "live")
            success, message = scheduler_service.force_sync(sync_type)

            if success:
                return jsonify({"message": message})
            else:
                return jsonify({"error": message}), 500

        elif action == "pause_job":
            job_id = request.json.get("job_id")
            if not job_id:
                return jsonify({"error": "Job ID required"}), 400

            success, message = scheduler_service.pause_job(job_id)
            if success:
                return jsonify({"message": message})
            else:
                return jsonify({"error": message}), 500

        elif action == "resume_job":
            job_id = request.json.get("job_id")
            if not job_id:
                return jsonify({"error": "Job ID required"}), 400

            success, message = scheduler_service.resume_job(job_id)
            if success:
                return jsonify({"message": message})
            else:
                return jsonify({"error": message}), 500

        else:
            return jsonify({"error": "Unknown action"}), 400

    except Exception as e:
        return jsonify({"error": f"Scheduler action failed: {str(e)}"}), 500


@bp.route("/api/scores/live")
def api_live_scores():
    """API endpoint for live score updates"""
    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season"}), 404

    # Get live games
    live_games = Game.query.filter(
        Game.season_id == current_season.id, Game.status == "in_progress"
    ).all()

    games_data = []
    for game in live_games:
        games_data.append(
            {
                "id": game.id,
                "home_team": game.home_team.abbreviation,
                "away_team": game.away_team.abbreviation,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "status": game.status,
                "is_final": game.is_final,
                "week": game.week,
            }
        )

    return jsonify(
        {"games": games_data, "last_updated": datetime.now(timezone.utc).isoformat()}
    )


@bp.route("/api/player-picks/<int:user_id>")
@login_required
def api_player_picks(user_id):
    """API endpoint to get a player's picks for the current season"""
    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season"}), 404

    # Get optional group_id parameter
    group_id = request.args.get("group_id", type=int)

    # Get the user
    user = User.query.get_or_404(user_id)

    # Check if current user can view this player's picks
    # Allow if it's the same user, or if they're in the same group, or if current user is admin
    can_view = False
    if current_user.id == user_id or current_user.is_admin:
        can_view = True
    else:
        # Check if they share any groups
        current_user_groups = set(
            membership.group_id for membership in current_user.group_memberships
        )
        user_groups = set(membership.group_id for membership in user.group_memberships)
        if current_user_groups.intersection(user_groups):
            can_view = True

    if not can_view:
        return jsonify({"error": "Access denied"}), 403

    # Get user's picks for current season, filtered by group if user has per-group picks
    picks_query = (
        db.session.query(Pick)
        .join(Game)
        .filter(Pick.user_id == user_id, Pick.season_id == current_season.id)
    )

    # If user has per-group picks, filter by group_id
    if not user.picks_are_global and group_id:
        picks_query = picks_query.filter(Pick.group_id == group_id)

    picks = picks_query.order_by(Game.week.desc(), Game.game_time.desc()).all()

    picks_data = []
    for pick in picks:
        game = pick.game
        picks_data.append(
            {
                "id": pick.id,
                "week": game.week,
                "game_time": (
                    game.game_time.strftime("%m/%d %I:%M %p")
                    if game.game_time
                    else "TBD"
                ),
                "home_team": game.home_team.abbreviation if game.home_team else "TBD",
                "away_team": game.away_team.abbreviation if game.away_team else "TBD",
                "selected_team": (
                    pick.selected_team.abbreviation if pick.selected_team else "TBD"
                ),
                "is_correct": pick.is_correct,
                "points_earned": pick.points_earned,
                "tiebreaker_points": pick.tiebreaker_points,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "is_final": game.is_final,
            }
        )

    return jsonify(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
            },
            "picks": picks_data,
        }
    )
