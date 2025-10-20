"""
One-time fix script to retroactively score picks for games that became final
before the scoring bug was fixed.

This script:
1. Finds all picks for final games that have is_correct=NULL
2. Calls pick.update_result() to score them properly
3. Commits the changes to the database

Run this ONCE after deploying the fixed code to production.
"""

from app import create_app, db
from app.models import Game, Pick
from app.utils.cache_utils import invalidate_model_cache


def fix_unscored_picks():
    """Find and score all picks that should have been scored"""

    app = create_app()

    with app.app_context():
        print("="*60)
        print("Fixing Unscored Picks for Final Games")
        print("="*60)

        # Find all final games
        final_games = Game.query.filter_by(is_final=True).all()
        print(f"\nFound {len(final_games)} final games")

        if not final_games:
            print("No final games found - nothing to fix")
            return

        # Get IDs of final games
        final_game_ids = [g.id for g in final_games]

        # Find picks for final games that haven't been scored
        unscored_picks = (
            Pick.query.filter(
                Pick.game_id.in_(final_game_ids), Pick.is_correct.is_(None)
            )
            .join(Game)
            .all()
        )

        if not unscored_picks:
            print("No unscored picks found - all picks are already scored!")
            return

        print(f"\nFound {len(unscored_picks)} unscored picks to fix:")

        # Group by game for reporting
        picks_by_game = {}
        for pick in unscored_picks:
            if pick.game_id not in picks_by_game:
                picks_by_game[pick.game_id] = []
            picks_by_game[pick.game_id].append(pick)

        # Score each pick
        fixed_count = 0
        for game_id, picks in picks_by_game.items():
            game = Game.query.get(game_id)
            print(
                f"\nGame {game_id} (Week {game.week}): "
                f"{game.away_team.abbreviation} {game.away_score} @ "
                f"{game.home_team.abbreviation} {game.home_score} (Final)"
            )
            print(f"  Fixing {len(picks)} picks...")

            for pick in picks:
                # Score the pick
                old_correct = pick.is_correct
                old_points = pick.points_earned
                old_tiebreaker = pick.tiebreaker_points

                pick.update_result()

                print(
                    f"    Pick {pick.id} (User {pick.user_id}): "
                    f"is_correct: {old_correct} -> {pick.is_correct}, "
                    f"points: {old_points} -> {pick.points_earned}, "
                    f"tiebreaker: {old_tiebreaker} -> {pick.tiebreaker_points}"
                )
                fixed_count += 1

        # Commit all changes
        print(f"\nCommitting {fixed_count} fixed picks to database...")
        db.session.commit()

        # Invalidate caches
        print("Invalidating caches...")
        invalidate_model_cache("Pick")
        invalidate_model_cache("Game")

        # Force session reload
        db.session.expire_all()

        print(f"\n{'='*60}")
        print(f"SUCCESS! Fixed {fixed_count} unscored picks")
        print(f"{'='*60}")

        # Verify the fix
        remaining_unscored = (
            Pick.query.filter(
                Pick.game_id.in_(final_game_ids), Pick.is_correct.is_(None)
            ).count()
        )

        if remaining_unscored == 0:
            print(f"\n[OK] All picks for final games are now scored!")
        else:
            print(
                f"\n[WARN] {remaining_unscored} picks still unscored - may need investigation"
            )


if __name__ == "__main__":
    try:
        fix_unscored_picks()
    except Exception as e:
        print(f"\n[ERROR] Failed to fix picks: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
