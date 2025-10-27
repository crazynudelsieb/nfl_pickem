#!/usr/bin/env python
"""Rescore all picks after rule changes (playoff multipliers removed)"""
from app import create_app
from app.models import Game, Pick, Season, db

app = create_app()

with app.app_context():
    print("=== Rescore All Picks After Rule Changes ===\n")
    
    # Get current season
    season = Season.get_current_season()
    if not season:
        print("No current season found!")
        exit(1)
    
    print(f"Current Season: {season.year}")
    
    # Find all final games
    final_games = Game.query.filter_by(
        season_id=season.id,
        is_final=True
    ).order_by(Game.week).all()
    
    print(f"Found {len(final_games)} final games")
    
    # Count all picks that need rescoring
    total_picks = 0
    for game in final_games:
        picks = game.picks.all()
        total_picks += len(picks)
    
    print(f"Total picks to rescore: {total_picks}")
    
    if total_picks == 0:
        print("No picks to rescore!")
        exit(0)
    
    # Show some examples
    print("\nExamples of games being rescored:")
    for game in final_games[:5]:
        picks = game.picks.all()
        if picks:
            print(f"  Week {game.week}: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score} - {len(picks)} picks")
    
    if len(final_games) > 5:
        print(f"  ... and {len(final_games) - 5} more games")
    
    # Confirm
    print(f"\n{'='*60}")
    response = input(f"Rescore all {total_picks} picks? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Cancelled.")
        exit(0)
    
    # Rescore all picks
    print("\nRescoring all picks...")
    rescored = 0
    
    for game in final_games:
        for pick in game.picks.all():
            pick.update_result()
            rescored += 1
            
            if rescored % 100 == 0:
                print(f"  Rescored {rescored}/{total_picks} picks...")
    
    # Commit
    db.session.commit()
    
    print(f"\n✓ Successfully rescored {rescored} picks")
    
    # Show tie game examples
    print("\n=== Tie Game Results ===")
    tie_games = Game.query.filter_by(
        season_id=season.id,
        is_final=True
    ).filter(Game.home_score == Game.away_score).all()
    
    if tie_games:
        for game in tie_games:
            print(f"\nWeek {game.week}: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
            for pick in game.picks.all()[:3]:  # Show first 3 picks
                print(f"  Pick {pick.id}: is_correct={pick.is_correct}, points={pick.points_earned}, tiebreaker={pick.tiebreaker_points}")
    
    print("\n✓ Rescore complete!")
