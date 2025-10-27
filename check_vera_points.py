from app import create_app, db
from app.models import Pick, Game, User

app = create_app()
app.app_context().push()

vera = User.query.filter_by(username='Vera').first()
print(f'Vera ID: {vera.id}')

picks = Pick.query.filter_by(user_id=vera.id).order_by(Pick.week).all()
total_points = sum(p.points_earned or 0 for p in picks)

print(f'\nTotal points from database: {total_points}')
print(f'Number of picks: {len(picks)}')

print('\nAll picks:')
for p in picks:
    print(f'Week {p.week}: is_correct={p.is_correct}, points={p.points_earned}, tiebreaker={p.tiebreaker_points}')
