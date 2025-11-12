"""
Scoring Engine for NFL Pick'em Application

This module handles scoring calculations for individual picks.
For aggregated statistics and leaderboards, see User.get_season_stats() 
and User.get_season_leaderboard() in app/models/user.py
"""


def calculate_pick_score(pick):
    """
    Calculate score for a single pick.
    
    Returns:
        1.0 for correct pick (win)
        0.5 for tie game
        0.0 for incorrect pick (loss) or incomplete game
    
    Args:
        pick: Pick object with game relationship loaded
    """
    if not pick.game or not pick.game.is_final:
        return 0.0
    
    # Tie game: award half point
    if pick.game.is_tie:
        return 0.5
    
    # Win: award full point
    if pick.selected_team_id == pick.game.winning_team_id:
        return 1.0
    
    # Loss: no points
    return 0.0


# Legacy class wrapper for backward compatibility
# TODO: Remove after updating all callers to use calculate_pick_score() directly
class ScoringEngine:
    """Legacy wrapper - use calculate_pick_score() function instead"""
    
    def calculate_pick_score(self, pick):
        """Legacy method - calls calculate_pick_score() function"""
        return calculate_pick_score(pick)

