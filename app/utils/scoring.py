"""
Scoring Engine for NFL Pick'em Application

This module handles scoring calculations for individual picks.
For aggregated statistics and leaderboards, see User.get_season_stats() 
and User.get_season_leaderboard() in app/models/user.py

REMOVED in cleanup (revert commit to restore):
- calculate_user_week_score() - Use User.get_season_stats() instead
- calculate_user_season_score() - Use User.get_season_stats() instead  
- get_group_leaderboard() - Use User.get_season_leaderboard() instead
- get_weekly_leaderboard() - Use User.get_season_leaderboard() instead
- update_all_scores() - Picks auto-update via Pick.update_result()
- get_pick_accuracy_stats() - Use User.get_season_stats() instead
"""


class ScoringEngine:
    """Handles scoring logic for individual picks"""

    def __init__(self):
        self.regular_season_points = 1
        # Playoff multipliers removed - all games score the same (KISS principle)
        # Competition happens through player elimination, not increased point values

    def calculate_pick_score(self, pick):
        """Calculate score for a single pick"""
        if not pick.game or not pick.game.is_final:
            return 0.0

        # Check if game is a tie
        if pick.game.is_tie:
            # Tie game: award half points (same for all weeks)
            return self.regular_season_points / 2.0

        # Check if pick is correct
        winning_team = pick.game.winning_team
        if not winning_team:  # Should not reach here if is_tie check works
            return 0.0

        is_correct = pick.selected_team_id == winning_team.id
        if not is_correct:
            return 0.0

        # Win: 1 point for all games (regular season and playoffs)
        return float(self.regular_season_points)
