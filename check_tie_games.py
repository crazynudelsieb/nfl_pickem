#!/usr/bin/env python
"""Check tie games status in week 8"""
from app import create_app
from app.models import Game, Pick, db

app = create_app()

with app.app_context():
    print("=== Week 8 Tie Games ===")
    tie_games = Game.query.filter_by(week=8, is_final=True).filter(
        Game.home_score == Game.away_score
    ).all()
    
    print(f"\nFound {len(tie_games)} tie game(s) in week 8:")
    for game in tie_games:
        print(f"\nGame {game.id}: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score}")
        print(f"  Status: is_final={game.is_final}")
        
        # Get picks for this game
        picks = game.picks.all()
        print(f"  Total picks: {len(picks)}")
        
        for pick in picks:
            print(f"    Pick {pick.id}: User {pick.user_id}")
            print(f"      is_correct: {pick.is_correct}")
            print(f"      points_earned: {pick.points_earned}")
            print(f"      tiebreaker_points: {pick.tiebreaker_points}")
            print(f"      selected_team_id: {pick.selected_team_id}")
    
    print("\n=== All Picks on Tie Games (Week 8) ===")
    tie_picks = Pick.query.join(Game).filter(
        Game.week == 8,
        Game.is_final == True,
        Game.home_score == Game.away_score
    ).all()
    
    print(f"\nTotal picks on tie games: {len(tie_picks)}")
    
    pending_picks = [p for p in tie_picks if p.is_correct is None]
    print(f"Picks with is_correct=None: {len(pending_picks)}")
    
    correct_picks = [p for p in tie_picks if p.is_correct is True]
    print(f"Picks with is_correct=True: {len(correct_picks)}")
    
    incorrect_picks = [p for p in tie_picks if p.is_correct is False]
    print(f"Picks with is_correct=False: {len(incorrect_picks)}")
    
    zero_point_picks = [p for p in tie_picks if p.points_earned == 0]
    print(f"Picks with 0 points: {len(zero_point_picks)}")
    
    half_point_picks = [p for p in tie_picks if p.points_earned == 0.5]
    print(f"Picks with 0.5 points: {len(half_point_picks)}")
    
    print("\n=== Data Type Check ===")
    # Check column data types
    result = db.session.execute(db.text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'picks' 
        AND column_name IN ('points_earned', 'tiebreaker_points')
    """))
    for row in result:
        print(f"{row[0]}: {row[1]}")
