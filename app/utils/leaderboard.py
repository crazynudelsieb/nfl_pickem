"""
Shared leaderboard builders.

The playoff-mode leaderboard (dual regular season / playoff scores for all
users) was previously duplicated across the dashboard, global leaderboard and
group pages - this module is the single implementation.
"""

from app.models import Game, User
from app.utils.ranking import sort_playoff_leaderboard


def build_playoff_leaderboard(season, group_id=None, users=None):
    """Build the playoff-mode leaderboard with dual regular/playoff scores.

    Shows ALL given users (not just playoff qualifiers) so everyone can see the
    overall standings, with playoff eligibility flagged per row. Sorted by
    playoff wins, then season-long tiebreaker points.

    Args:
        season: Season object
        group_id: Optional group ID for per-group pick filtering
        users: Users to include. Defaults to all active users with picks
            handled by the caller; pass an explicit list for group leaderboards.

    Returns:
        list of leaderboard row dicts
    """
    if users is None:
        users = User.query.filter_by(is_active=True).all()

    # Fetch completed games once and share across all users' stats
    completed_games = Game.query.filter(
        Game.season_id == season.id, Game.is_final == True  # noqa: E712
    ).all()

    leaderboard = []

    for user in users:
        stats = user.get_season_stats(
            season.id, group_id=group_id, completed_games=completed_games
        )
        if not stats:
            continue

        # Use eligibility methods (have proper fallback if snapshots missing)
        is_po_eligible, _ = user.is_playoff_eligible(season.id, group_id)
        is_sb_eligible, _ = user.is_superbowl_eligible_from_snapshot(
            season.id, group_id
        )

        leaderboard.append(
            {
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
                "is_playoff_eligible": is_po_eligible,
                "is_superbowl_eligible": is_sb_eligible,
                "regular_wins": stats["regular_season"]["wins"],
                "regular_score": stats["regular_season"]["total_score"],
                "playoff_wins": stats["playoffs"]["wins"],
                "playoff_score": stats["playoffs"]["total_score"],
            }
        )

    # During playoffs, rank by playoff form with the regular season as decider
    return sort_playoff_leaderboard(leaderboard)
