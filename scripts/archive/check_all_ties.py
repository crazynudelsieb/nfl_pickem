#!/usr/bin/env python
"""Check all tie games across all weeks"""
from app import create_app
from app.models import Game, Pick, Season, db

app = create_app()

with app.app_context():
    print("=== Checking All Tie Games ===")
    
    # Get current season
    season = Season.get_current_season()
    if not season:
        print("No current season found!")
        exit(1)
    
    print(f"\nCurrent Season: {season.year}, Week: {season.current_week}")
    
    # Find all tie games in current season
    all_tie_games = Game.query.filter_by(
        season_id=season.id,
        is_final=True
    ).filter(Game.home_score == Game.away_score).all()
    
    print(f"\nTotal tie games this season: {len(all_tie_games)}")
    
    if len(all_tie_games) == 0:
        print("\nNo tie games found in current season.")
        
        # Check if there are any final games at all
        final_games = Game.query.filter_by(season_id=season.id, is_final=True).all()
        print(f"Total final games: {len(final_games)}")
        
        # Show some recent final games
        print("\nRecent final games (last 5):")
        recent = Game.query.filter_by(season_id=season.id, is_final=True).order_by(Game.game_time.desc()).limit(5).all()
        for game in recent:
            print(f"  Week {game.week}: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
    else:
        for game in all_tie_games:
            print(f"\n{'='*60}")
            print(f"Week {game.week} - Game {game.id}")
            print(f"{game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
            print(f"Status: is_final={game.is_final}, game_time={game.game_time}")
            
            # Get picks for this game
            picks = game.picks.all()
            print(f"\nTotal picks on this game: {len(picks)}")
            
            if len(picks) > 0:
                pending = [p for p in picks if p.is_correct is None]
                correct = [p for p in picks if p.is_correct is True]
                incorrect = [p for p in picks if p.is_correct is False]
                
                print(f"  Pending (is_correct=None): {len(pending)}")
                print(f"  Marked correct: {len(correct)}")
                print(f"  Marked incorrect: {len(incorrect)}")
                
                # Show first few picks
                print("\n  Sample picks:")
                for pick in picks[:5]:
                    print(f"    Pick {pick.id}: User {pick.user_id}")
                    print(f"      is_correct={pick.is_correct}, points={pick.points_earned}, tiebreaker={pick.tiebreaker_points}")
    
    print("\n" + "="*60)
    print("=== Summary of Picks Needing Correction ===")
    
    # Find all picks on tie games that don't have correct scoring
    # Correct scoring for ties: is_correct=None, points=0.5 (or with playoff multiplier), tiebreaker=0
    broken_picks = Pick.query.join(Game).filter(
        Game.season_id == season.id,
        Game.is_final == True,
        Game.home_score == Game.away_score,
        Pick.tiebreaker_points != 0  # Main issue: tiebreaker should be 0 for ties
    ).all()
    
    print(f"\nPicks needing correction: {len(broken_picks)}")
    
    if len(broken_picks) > 0:
        print("\nThese picks need to be updated:")
        for pick in broken_picks:
            game = pick.game
            
            # Calculate correct points
            from app.utils.scoring import ScoringEngine
            scoring = ScoringEngine()
            correct_points = scoring.calculate_pick_score(pick)
            
            print(f"  Pick {pick.id}: Game {game.id} (Week {game.week})")
            print(f"    Current: is_correct={pick.is_correct}, points={pick.points_earned}, tiebreaker={pick.tiebreaker_points}")
            print(f"    Should be: is_correct=None, points={correct_points}, tiebreaker=0")
