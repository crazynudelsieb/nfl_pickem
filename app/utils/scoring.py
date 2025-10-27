"""
Scoring Engine for NFL Pick'em Application

This module handles all scoring calculations including:
- Regular season scoring
- Playoff scoring
- Tiebreaker calculations
- Weekly and season-long statistics
"""

from collections import defaultdict

from app import db
from app.models import Game, Pick


class ScoringEngine:
    """Handles all scoring logic for the NFL Pick'em application"""

    def __init__(self):
        self.regular_season_points = 1
        self.playoff_multipliers = {
            "Wild Card": 2,
            "Divisional": 3,
            "Conference Championship": 4,
            "Super Bowl": 5,
        }

    def calculate_pick_score(self, pick):
        """Calculate score for a single pick"""
        if not pick.game or not pick.game.is_final:
            return 0.0

        # Check if game is a tie
        if pick.game.is_tie:
            # Tie game: award half points
            points = self.regular_season_points / 2.0

            # Apply playoff multiplier if applicable
            season = pick.game.season
            if season.is_playoff_week(pick.game.week):
                week_info = season.get_weeks()[pick.game.week - 1]
                multiplier = self.playoff_multipliers.get(week_info["name"], 1)
                points *= multiplier

            return points

        # Check if pick is correct
        winning_team = pick.game.winning_team
        if not winning_team:  # Should not reach here if is_tie check works
            return 0.0

        is_correct = pick.selected_team_id == winning_team.id
        if not is_correct:
            return 0.0

        # Base points
        points = self.regular_season_points

        # Apply playoff multiplier if applicable
        season = pick.game.season
        if season.is_playoff_week(pick.game.week):
            week_info = season.get_weeks()[pick.game.week - 1]
            multiplier = self.playoff_multipliers.get(week_info["name"], 1)
            points *= multiplier

        return float(points)

    def calculate_user_week_score(self, user_id, season_id, week):
        """Calculate total score for a user in a specific week"""
        picks = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == user_id, Game.season_id == season_id, Game.week == week
            )
            .all()
        )

        total_score = 0
        correct_picks = 0

        for pick in picks:
            score = self.calculate_pick_score(pick)
            total_score += score
            if score > 0:
                correct_picks += 1

        return {
            "total_score": total_score,
            "correct_picks": correct_picks,
            "total_picks": len(picks),
        }

    def calculate_user_season_score(self, user_id, season_id):
        """Calculate total score for a user for the entire season"""
        picks = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == user_id,
                Game.season_id == season_id,
                Game.is_final.is_(True),
            )
            .all()
        )

        total_score = 0
        correct_picks = 0
        weekly_scores = defaultdict(int)

        for pick in picks:
            score = self.calculate_pick_score(pick)
            total_score += score
            if score > 0:
                correct_picks += 1
            weekly_scores[pick.game.week] += score

        return {
            "total_score": total_score,
            "correct_picks": correct_picks,
            "total_picks": len(picks),
            "win_percentage": correct_picks / len(picks) if picks else 0,
            "weekly_scores": dict(weekly_scores),
        }

    def get_group_leaderboard(self, group_id, season_id):
        """Get leaderboard for a specific group and season"""
        # Get all users in the group
        from app.models import GroupMember

        members = GroupMember.query.filter_by(group_id=group_id, is_active=True).all()

        leaderboard = []

        for member in members:
            score_data = self.calculate_user_season_score(member.user_id, season_id)

            leaderboard.append(
                {
                    "user_id": member.user_id,
                    "user": member.user,
                    "total_score": score_data["total_score"],
                    "correct_picks": score_data["correct_picks"],
                    "total_picks": score_data["total_picks"],
                    "win_percentage": score_data["win_percentage"],
                    "wins": score_data["correct_picks"],
                    "losses": score_data["total_picks"] - score_data["correct_picks"],
                }
            )

        # Sort by total score, then by win percentage
        leaderboard.sort(
            key=lambda x: (x["total_score"], x["win_percentage"]), reverse=True
        )

        # Add rankings
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1

        return leaderboard

    def get_weekly_leaderboard(self, group_id, season_id, week):
        """Get leaderboard for a specific week"""
        from app.models import GroupMember

        members = GroupMember.query.filter_by(group_id=group_id, is_active=True).all()

        leaderboard = []

        for member in members:
            score_data = self.calculate_user_week_score(member.user_id, season_id, week)

            leaderboard.append(
                {
                    "user_id": member.user_id,
                    "user": member.user,
                    "week_score": score_data["total_score"],
                    "correct_picks": score_data["correct_picks"],
                    "total_picks": score_data["total_picks"],
                    "win_percentage": (
                        score_data["correct_picks"] / score_data["total_picks"]
                        if score_data["total_picks"]
                        else 0
                    ),
                }
            )

        # Sort by week score, then by win percentage
        leaderboard.sort(
            key=lambda x: (x["week_score"], x["win_percentage"]), reverse=True
        )

        # Add rankings
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1

        return leaderboard

    def update_all_scores(self, season_id):
        """Recalculate all scores for a season (useful after games are updated)"""
        updated_count = 0

        # Get all picks for the season
        picks = (
            Pick.query.join(Game)
            .filter(Game.season_id == season_id, Game.is_final.is_(True))
            .all()
        )

        for pick in picks:
            old_score = pick.points_earned
            new_score = self.calculate_pick_score(pick)

            if old_score != new_score:
                pick.points_earned = new_score
                updated_count += 1

        db.session.commit()
        return updated_count

    def get_pick_accuracy_stats(self, user_id, season_id):
        """Get detailed accuracy statistics for a user"""
        picks = (
            Pick.query.join(Game)
            .filter(
                Pick.user_id == user_id,
                Game.season_id == season_id,
                Game.is_final.is_(True),
            )
            .all()
        )

        if not picks:
            return None

        stats = {
            "total_picks": len(picks),
            "correct_picks": sum(1 for p in picks if self.calculate_pick_score(p) > 0),
            "by_week_type": {
                "regular": {"total": 0, "correct": 0},
                "playoff": {"total": 0, "correct": 0},
            },
            "by_team": defaultdict(lambda: {"total": 0, "correct": 0}),
            "streak": {"current": 0, "longest": 0},
        }

        # Calculate detailed stats
        current_streak = 0
        longest_streak = 0

        for pick in picks:
            is_correct = self.calculate_pick_score(pick) > 0
            season = pick.game.season
            week_type = (
                "playoff" if season.is_playoff_week(pick.game.week) else "regular"
            )

            # Week type stats
            stats["by_week_type"][week_type]["total"] += 1
            if is_correct:
                stats["by_week_type"][week_type]["correct"] += 1

            # Team stats
            team_name = pick.selected_team.name if pick.selected_team else "Unknown"
            stats["by_team"][team_name]["total"] += 1
            if is_correct:
                stats["by_team"][team_name]["correct"] += 1

            # Streak calculation
            if is_correct:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 0

        stats["streak"]["current"] = current_streak
        stats["streak"]["longest"] = longest_streak
        stats["win_percentage"] = stats["correct_picks"] / stats["total_picks"]

        return stats
