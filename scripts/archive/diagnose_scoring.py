#!/usr/bin/env python
"""Diagnose why picks aren't being scored"""
from app import create_app
from app.models import Game, Pick, Season, db
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    print("=== Scoring Diagnostics ===\n")
    
    # Get current season
    season = Season.get_current_season()
    if not season:
        print("No current season found!")
        exit(1)
    
    print(f"Current Season: {season.year}, Week: {season.current_week}")
    
    # Check for final games with unscored picks
    print("\n=== Final Games with Unscored Picks ===")
    
    final_games = Game.query.filter_by(
        season_id=season.id,
        is_final=True
    ).order_by(Game.week).all()
    
    print(f"Total final games: {len(final_games)}")
    
    unscored_count = 0
    for game in final_games:
        picks = game.picks.all()
        if picks:
            unscored_picks = [p for p in picks if p.is_correct is None and not game.is_tie]
            
            if unscored_picks:
                unscored_count += len(unscored_picks)
                print(f"\nWeek {game.week} - Game {game.id}:")
                print(f"  {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
                print(f"  is_final={game.is_final}, is_tie={game.is_tie}")
                print(f"  Unscored picks: {len(unscored_picks)} out of {len(picks)}")
                
                # Show first unscored pick details
                if unscored_picks:
                    p = unscored_picks[0]
                    print(f"  Example: Pick {p.id} - is_correct={p.is_correct}, points={p.points_earned}, tiebreaker={p.tiebreaker_points}")
    
    print(f"\n{'='*60}")
    print(f"Total unscored picks on final games: {unscored_count}")
    
    # Check tie games specifically
    print("\n=== Tie Games ===")
    tie_games = Game.query.filter_by(
        season_id=season.id,
        is_final=True
    ).filter(Game.home_score == Game.away_score).all()
    
    print(f"Total tie games: {len(tie_games)}")
    for game in tie_games:
        print(f"\nWeek {game.week} - Game {game.id}:")
        print(f"  {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
        print(f"  is_final={game.is_final}, is_tie={game.is_tie}")
        
        picks = game.picks.all()
        print(f"  Total picks: {len(picks)}")
        
        for pick in picks:
            print(f"    Pick {pick.id}: is_correct={pick.is_correct}, points={pick.points_earned}, tiebreaker={pick.tiebreaker_points}")
    
    # Check current week games
    print(f"\n{'='*60}")
    print(f"=== Current Week ({season.current_week}) Games ===")
    
    current_week_games = Game.query.filter_by(
        season_id=season.id,
        week=season.current_week
    ).order_by(Game.game_time).all()
    
    print(f"Total games in week {season.current_week}: {len(current_week_games)}")
    
    now = datetime.now(timezone.utc)
    for game in current_week_games:
        status = "FINAL" if game.is_final else ("LIVE" if game.game_time <= now else "SCHEDULED")
        print(f"\nGame {game.id}: {game.away_team.name} {game.away_score or 0} @ {game.home_team.name} {game.home_score or 0}")
        print(f"  Status: {status}, is_final={game.is_final}")
        print(f"  Game time: {game.game_time}")
        
        picks = game.picks.all()
        if picks:
            print(f"  Total picks: {len(picks)}")
            scored = [p for p in picks if p.is_correct is not None or p.points_earned > 0]
            print(f"  Scored picks: {len(scored)}")
    
    # Summary
    print(f"\n{'='*60}")
    print("=== Summary ===")
    print(f"If you see unscored picks on final games, run:")
    print(f"  docker exec nfl_pickem_web python manage.py rescore-picks")
