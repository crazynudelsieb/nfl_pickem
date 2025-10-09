from functools import wraps

from flask import jsonify, request, session
from flask_login import current_user, login_required

from app import db
from app.models import Game, Group, GroupMember, Pick, Season, Team, User
from app.routes.api import bp
from app.utils.cache_utils import cached_route


def add_security_headers(f):
    """Add security headers to API responses"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        if hasattr(response, "headers"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
        return response

    return decorated_function


@bp.route("/set-group", methods=["POST"])
@login_required
@add_security_headers
def set_group():
    """Set the selected group in session"""
    data = request.get_json()
    group_id = data.get("group_id")

    if not group_id:
        return jsonify({"error": "No group_id provided"}), 400

    # Verify user is member of this group
    group = Group.query.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    if not group.is_user_member(current_user.id):
        return jsonify({"error": "Not a member of this group"}), 403

    # Store in session
    session["selected_group_id"] = int(group_id)
    session.modified = True

    return jsonify({"success": True, "group_id": group_id})


@bp.route("/seasons")
@cached_route(timeout=3600, key_prefix="seasons")  # Cache for 1 hour
def seasons():
    """Get all seasons"""
    seasons = Season.query.order_by(Season.year.desc()).all()
    return jsonify([season.to_dict() for season in seasons])


@bp.route("/seasons/current")
@cached_route(timeout=1800, key_prefix="current_season")  # Cache for 30 minutes
def current_season():
    """Get current active season"""
    season = Season.get_current_season()
    if season:
        return jsonify(season.to_dict())
    return jsonify({"error": "No active season"}), 404


@bp.route("/seasons/<int:season_id>/games")
@cached_route(timeout=3600, key_prefix="season_games")  # Cache for 1 hour
def season_games(season_id):
    """Get all games for a season"""
    season = Season.query.get_or_404(season_id)
    games = season.games.order_by(Game.week, Game.game_time).all()
    return jsonify([game.to_dict() for game in games])


@bp.route("/seasons/<int:season_id>/games/week/<int:week>")
@cached_route(
    timeout=300, key_prefix="week_games"
)  # Cache for 5 minutes (shorter due to live updates)
def week_games(season_id, week):
    """Get games for a specific week"""
    games = Game.get_games_for_week(season_id, week)
    return jsonify([game.to_dict(include_picks_count=True) for game in games])


@bp.route("/games/week/<int:week>")
@cached_route(
    timeout=300, key_prefix="current_week_games"
)  # Cache for 5 minutes (shorter due to live updates)
def current_season_week_games(week):
    """Get games for a specific week in the current season"""
    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season", "games": []}), 404

    games = Game.get_games_for_week(current_season.id, week)
    return jsonify(
        {"games": [game.to_dict(include_picks_count=True) for game in games]}
    )


@bp.route("/teams")
def teams():
    """Get teams for current season"""
    current_season = Season.get_current_season()
    if not current_season:
        return jsonify({"error": "No active season"}), 404

    teams = Team.get_all_for_season(current_season.id)
    return jsonify([team.to_dict() for team in teams])


@bp.route("/teams/<int:season_id>")
def teams_by_season(season_id):
    """Get teams for specific season"""
    teams = Team.get_all_for_season(season_id)
    return jsonify([team.to_dict() for team in teams])


@bp.route("/groups")
@login_required
@add_security_headers
def groups():
    """Get user's groups"""
    user_groups = current_user.get_groups()
    return jsonify([membership.group.to_dict() for membership in user_groups])


@bp.route("/groups/<int:group_id>/leaderboard")
@login_required
def group_leaderboard(group_id):
    """Get leaderboard for a group"""
    group = Group.query.get_or_404(group_id)

    if not group.is_user_member(current_user.id):
        return jsonify({"error": "Not a member of this group"}), 403

    season_id = request.args.get("season_id", type=int)
    if not season_id:
        current_season = Season.get_current_season()
        season_id = current_season.id if current_season else None

    if not season_id:
        return jsonify({"error": "No season specified"}), 400

    leaderboard = group.get_leaderboard(season_id)

    return jsonify(
        {
            "group": group.to_dict(),
            "season_id": season_id,
            "leaderboard": [
                {
                    "user": entry["user"].to_dict(),
                    "wins": entry["wins"],
                    "losses": entry["losses"],
                    "total_points": entry["total_points"],
                    "picks_made": entry["picks_made"],
                }
                for entry in leaderboard
            ],
        }
    )


@bp.route("/picks")
@login_required
@add_security_headers
def user_picks():
    """Get user's picks"""
    season_id = request.args.get("season_id", type=int)
    week = request.args.get("week", type=int)

    if not season_id:
        current_season = Season.get_current_season()
        season_id = current_season.id if current_season else None

    if not season_id:
        return jsonify({"error": "No season specified"}), 400

    picks_query = Pick.query.filter_by(user_id=current_user.id, season_id=season_id)

    if week:
        picks_query = picks_query.join(Game).filter(Game.week == week)

    picks = picks_query.all()
    return jsonify([pick.to_dict() for pick in picks])


@bp.route("/picks/<int:pick_id>")
@login_required
def pick_detail(pick_id):
    """Get pick details"""
    pick = Pick.query.get_or_404(pick_id)

    if pick.user_id != current_user.id:
        return jsonify({"error": "Permission denied"}), 403

    return jsonify(pick.to_dict())


@bp.route("/stats/user")
@login_required
def user_stats():
    """Get user statistics"""
    season_id = request.args.get("season_id", type=int)

    if not season_id:
        current_season = Season.get_current_season()
        season_id = current_season.id if current_season else None

    if not season_id:
        return jsonify({"error": "No season specified"}), 400

    picks = current_user.get_picks_for_season(season_id)
    completed_picks = [p for p in picks if p.is_correct is not None]

    wins = sum(1 for p in completed_picks if p.is_correct)
    losses = len(completed_picks) - wins
    total_points = sum(
        p.points_earned for p in completed_picks if p.points_earned is not None
    )

    # Get team usage
    team_usage = {}
    for pick in picks:
        team_name = pick.selected_team.full_name
        if team_name not in team_usage:
            team_usage[team_name] = {"picks": 0, "wins": 0, "points": 0}
        team_usage[team_name]["picks"] += 1
        if pick.is_correct:
            team_usage[team_name]["wins"] += 1
        if pick.points_earned:
            team_usage[team_name]["points"] += pick.points_earned

    return jsonify(
        {
            "season_id": season_id,
            "total_picks": len(picks),
            "completed_picks": len(completed_picks),
            "wins": wins,
            "losses": losses,
            "win_percentage": (
                (wins / len(completed_picks) * 100) if completed_picks else 0
            ),
            "total_points": total_points,
            "average_points": (
                total_points / len(completed_picks) if completed_picks else 0
            ),
            "team_usage": team_usage,
        }
    )


@bp.route("/games/<int:game_id>")
def game_detail(game_id):
    """Get game details"""
    game = Game.query.get_or_404(game_id)
    return jsonify(game.to_dict(include_picks_count=True))


@bp.route("/search")
@login_required
def search():
    """Search functionality"""
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)

    if not query:
        return jsonify({"results": {}})

    results = {"groups": [], "users": [], "games": []}

    # Search groups
    user_group_ids = [membership.group_id for membership in current_user.get_groups()]
    groups = (
        Group.query.filter(
            db.or_(Group.is_public.is_(True), Group.id.in_(user_group_ids)),
            Group.name.contains(query),
        )
        .limit(limit)
        .all()
    )
    results["groups"] = [group.to_dict() for group in groups]

    # Search users (in same groups)
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
            .limit(limit)
            .all()
        )
        results["users"] = [user.to_dict() for user in users]

    return jsonify({"results": results, "query": query})


@bp.route("/debug/avatars")
@login_required
@add_security_headers
def debug_avatars():
    """Debug endpoint to check avatar URLs"""
    users = User.query.all()
    result = []
    for user in users:
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "has_avatar": bool(user.avatar_url),
            }
        )
    return jsonify(result)


@bp.route("/debug/group/<int:group_id>")
@login_required
@add_security_headers
def debug_group(group_id):
    """Debug endpoint to check group data"""
    from app.models import Group, Season

    group = Group.query.get_or_404(group_id)
    season = Season.get_current_season()

    leaderboard = []
    if season:
        leaderboard = group.get_leaderboard(season.id)

    members = group.get_active_members()

    result = {
        "group_name": group.name,
        "leaderboard_count": len(leaderboard),
        "members_count": len(members),
        "leaderboard_sample": [],
        "members_sample": [],
    }

    # Sample first entry from leaderboard
    if leaderboard:
        entry = leaderboard[0]
        result["leaderboard_sample"].append(
            {
                "user_id": entry.get("user_id"),
                "username": entry["user"].username if entry.get("user") else "NO USER",
                "has_avatar_url": (
                    hasattr(entry["user"], "avatar_url") if entry.get("user") else False
                ),
                "avatar_url": (
                    entry["user"].avatar_url
                    if entry.get("user") and hasattr(entry["user"], "avatar_url")
                    else None
                ),
            }
        )

    # Sample first member
    if members:
        member = members[0]
        result["members_sample"].append(
            {
                "user_id": member.user_id,
                "username": member.user.username if member.user else "NO USER",
                "has_avatar_url": (
                    hasattr(member.user, "avatar_url") if member.user else False
                ),
                "avatar_url": (
                    member.user.avatar_url
                    if member.user and hasattr(member.user, "avatar_url")
                    else None
                ),
            }
        )

    return jsonify(result)
