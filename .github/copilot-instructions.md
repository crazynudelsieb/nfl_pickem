# NFL Pick'em - AI Agent Instructions

## Project Overview
Flask-based Progressive Web App for NFL pick'em leagues with real-time score updates. Users make weekly picks following specific game rules, compete in groups, and track standings with tiebreaker systems.

## Architecture

### Core Components
- **Backend**: Flask application with Blueprint-based routing (`app/routes/{auth,main,groups,api}`)
- **Database**: SQLAlchemy ORM with PostgreSQL (production) or SQLite (dev)
- **Real-time**: Socket.IO for live score updates via `/scores` namespace
- **Background Jobs**: APScheduler-based `scheduler_service` syncing NFL data from ESPN API
- **Caching**: Redis-backed Flask-Caching with model-level cache invalidation
- **Frontend**: Server-rendered Jinja2 templates + vanilla JS with Socket.IO client

### Key Models (app/models/)
- **User**: Supports `picks_are_global` flag (False = separate picks per group, True = shared picks)
- **Pick**: Unique constraint on `(user_id, game_id, group_id)` - stores selection and results
- **Game**: Tracks NFL games with ESPN API sync, status tracking (`scheduled`, `in_progress`, `completed`)
- **Season**: Manages weeks (1-18 regular, 19-22 playoffs) and current week calculation
- **Group**: Pick'em leagues with invite system and group-specific leaderboards

## Game Rules (Critical for Pick Validation)

These rules are enforced in `Pick.is_valid_pick()` and `User.can_pick_team()`:

1. **One pick per week**: Users pick one game per week; can switch before current pick's game starts
2. **One team per season**: Teams can't be reused during regular season (weeks 1-18), but reusable in playoffs
3. **No consecutive losses**: If team loses in week N, can't pick same team in week N+1 (must skip a week)

**Scoring**: 1 point per win. Tiebreaker: margin of victory (winning pick) or negative margin (losing pick) stored in `Pick.tiebreaker_points`

## Critical Developer Workflows

### Running the Application
```powershell
# Docker (recommended)
docker compose up --build -d

# Access at http://localhost:5000
# Services: PostgreSQL (5432), Redis (6379), Flask (5000)

# Local development
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py  # Will fallback to SQLite + SimpleCache if Redis unavailable
```

### Database Operations
```powershell
# Flask-Migrate commands (when models change)
flask db migrate -m "Description"
flask db upgrade

# Create admin user
docker compose exec web python -c "from app import db; from app.models import User; u = User.query.filter_by(username='USERNAME').first(); u.is_admin = True; db.session.commit()"
```

### Configuration
- `.env` file required with `SECRET_KEY`, `WTF_CSRF_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`
- Generate secrets: `python generate_secrets.py`
- Config classes in `config.py`: `DevelopmentConfig`, `ProductionConfig`, `TestingConfig`
- Set via `FLASK_ENV` environment variable (defaults to `development`)

## Project-Specific Patterns

### Per-Group vs Global Picks
```python
# User model controls pick scope
if not user.picks_are_global:
    # Filter picks by group_id - user has separate picks per group
    picks = Pick.query.filter_by(user_id=user.id, group_id=group.id).all()
else:
    # User has one set of picks shared across all groups (group_id=None)
    picks = Pick.query.filter_by(user_id=user.id, group_id=None).all()
```

### Scheduler Service (app/services/scheduler_service.py)
Background jobs sync NFL data with adaptive frequency:
- **Live games** (90s): Updates in-progress games only during game windows
- **Game status** (5min): Checks for status changes, triggers `Pick.update_result()` on completion
- **Hourly sync**: Full score updates + scoring recalculation
- **Daily maintenance**: Full season data sync + cleanup

Access admin controls: `/admin/scheduler` (requires `user.is_admin=True`)

### Real-Time Updates (app/socketio_handlers.py)
```python
# Emit patterns called from scheduler
broadcast_score_update(game)  # Updates game scores
broadcast_game_final(game)    # Triggers pick result calculations
notify_user(user_id, type, message, data)  # User notifications

# Client subscribes to rooms: game_{id}, user_picks_{id}, group_{id}
```

### Data Sync with Rate Limiting (app/utils/data_sync.py)
ESPN API integration with exponential backoff:
- `DataSync._enforce_rate_limit()`: Max 60 req/min, 500ms min interval
- `@rate_limit_decorator`: Retries with backoff on 429/5xx errors
- Uses `requests.Session` with persistent connections

### Database Query Patterns
```python
# ALWAYS use joinedload to avoid N+1 queries
games = Game.query.options(
    db.joinedload(Game.home_team),
    db.joinedload(Game.away_team)
).filter_by(season_id=season_id).all()

# Session management after writes
db.session.commit()
db.session.expire_all()  # Force reload from DB when stale data suspected
from app.utils.cache_utils import invalidate_model_cache
invalidate_model_cache('pick')  # Clear Redis cache for model
```

### Admin Override Pattern
Admins can manage picks for any user and edit past games:
```python
target_user = current_user
if current_user.is_admin and request.form.get('selected_user_id'):
    target_user = User.query.get(request.form.get('selected_user_id'))
    is_admin_override = True  # Bypass game.is_pickable() checks
```

## Key Integration Points

### Blueprint Registration (app/__init__.py)
```python
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(main_bp)  # No prefix - handles /picks, /leaderboard
app.register_blueprint(groups_bp, url_prefix='/groups')
app.register_blueprint(api_bp, url_prefix='/api')
```

### CSRF Protection
- Flask-WTF CSRF enabled globally via `CSRFProtect`
- Exempt API routes: Use `@csrf.exempt` decorator
- Forms use `{{ form.hidden_tag() }}` for tokens

### Timezone Handling (app/utils/timezone_utils.py)
```python
# All database timestamps stored in UTC
game.game_time = datetime.now(timezone.utc)

# Display conversion uses TIMEZONE config (default: Europe/Vienna)
from app.utils.timezone_utils import format_game_time
formatted = format_game_time(game.game_time, '%a %m/%d at %I:%M %p')
```

### PWA Features (app/static/)
- `manifest.json`: PWA metadata, served with correct MIME type via `/manifest.json` route
- `sw.js`: Service worker for offline caching, served via `/sw.js` route
- Icons in `app/static/images/` (various sizes for iOS/Android)

## Debugging Tips

### Logging
- Main logs: `logs/nfl_pickem.log` (application) and `logs/scheduler.log` (background jobs)
- Errors: `logs/errors.log`
- Configure verbosity: `LOG_LEVEL` env var (INFO/DEBUG/WARNING)

### Database Inspection
```powershell
# Connect to PostgreSQL in Docker
docker compose exec db psql -U nfl_user -d nfl_pickem_db

# Useful queries
SELECT * FROM picks WHERE user_id=X AND season_id=Y;
SELECT * FROM games WHERE week=N ORDER BY game_time;
```

### Common Pitfalls
1. **Stale leaderboard data**: Call `db.session.expire_all()` + `invalidate_model_cache()` after pick submissions
2. **Group filtering**: Always check `user.picks_are_global` before filtering by `group_id`
3. **Timezone-naive datetimes**: Use `datetime.now(timezone.utc)` not `datetime.now()`
4. **N+1 queries**: Use `db.joinedload()` for relationships, check SQL logs with `SQLALCHEMY_ECHO=True`

## Example: Adding a New Pick Validation Rule

```python
# 1. Update Pick model validation (app/models/pick.py)
def _validate_team_rules(self):
    # ... existing rules ...
    
    # New rule: Example - can't pick division rival consecutively
    if self.game.week > 1:
        prev_pick = Pick.query.join(Game).filter(
            Pick.user_id == self.user_id,
            Game.week == self.game.week - 1
        ).first()
        
        if prev_pick and self._is_division_rival(prev_pick.selected_team_id, self.selected_team_id):
            return False, "Can't pick division rivals back-to-back"
    
    return True, "Valid"

# 2. Update frontend validation (app/routes/main/routes.py)
available_teams = {}
for team in teams:
    can_pick, reason = user.can_pick_team(team.id, week, season_id, group_id)
    available_teams[team.id] = {'can_pick': can_pick, 'reason': reason}

# 3. Update template to show restriction (app/templates/main/current_picks.html)
{% if not available_teams[team.id]['can_pick'] %}
    <small class="text-muted">{{ available_teams[team.id]['reason'] }}</small>
{% endif %}
```

## Testing Patterns

```python
# Unit tests use in-memory SQLite (config.py TestingConfig)
SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
WTF_CSRF_ENABLED = False

# Run tests
pytest tests/
```

## Useful File Locations
- Routes: `app/routes/{main,auth,groups,api}/routes.py`
- Models: `app/models/*.py`
- Templates: `app/templates/{main,auth,groups,errors}/`
- Utilities: `app/utils/{scoring.py,data_sync.py,cache_utils.py}`
- Configuration: `config.py` (class-based), `.env` (secrets)
