#!/usr/bin/env python
"""Check scoring for specific users"""
from app import create_app
from app.models import User, Pick, Game

app = create_app()

with app.app_context():
    users = User.query.filter(User.username.in_(['Andi', 'Vera'])).all()
    
    for user in users:
        print(f"\n{'='*60}")
        print(f"User: {user.username} (ID: {user.id})")
        print(f"{'='*60}")
        
        # Get season stats using User model method
        stats = user.get_season_stats(season_id=1)
        print(f"\nSeason Stats:")
        print(f"  Total Score: {stats['total']['total_score']}")
        print(f"  Wins: {stats['total']['wins']}")
        print(f"  Ties: {stats['total']['ties']}")
        print(f"  Losses: {stats['total']['losses']}")
        print(f"  Tiebreaker: {stats['total']['tiebreaker_points']}")
        print(f"  Total Picks: {stats['total']['total_picks']}")
        
        # Get all picks
        picks = Pick.query.join(Game).filter(
            Pick.user_id == user.id,
            Game.season_id == 1,
            Game.is_final == True
        ).all()
        
        print(f"\nAll Final Game Picks:")
        total_manual = 0
        for pick in picks:
            game = pick.game
            points = pick.points_earned
            total_manual += points
            status = "WIN" if pick.is_correct is True else ("LOSS" if pick.is_correct is False else "TIE")
            print(f"  Week {game.week}: {game.away_team.abbreviation}@{game.home_team.abbreviation} {game.away_score}-{game.home_score} | {status} | Points: {points} | Tiebreaker: {pick.tiebreaker_points}")
        
        print(f"\nManual Total: {total_manual}")
        print(f"Calculated Total: {score['total_score']}")
        
        if abs(total_manual - score['total_score']) > 0.01:
            print(f"⚠️  MISMATCH! Difference: {abs(total_manual - score['total_score'])}")
