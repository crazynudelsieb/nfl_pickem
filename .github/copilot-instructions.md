# NFL Pick'em - AI Agent Instructions

## AI Development Environment

**Compatible with**: GitHub Copilot, Claude Code (C:\Users\q913966\.claude), Claude API  
**Primary IDE**: Visual Studio Code with Copilot/Claude Code extensions  
**Version Control**: Git with feature branch workflow  
**OS**: Windows with PowerShell (pwsh.exe)

### Available Tools & Services
- **Serena MCP Server**: Semantic code search, symbol navigation, refactoring tools
- **Context7 MCP**: Library documentation retrieval
- **Playwright MCP**: Browser automation for testing
- **Sequential Thinking MCP**: Complex problem-solving chains
- **GitHub Copilot**: Code completion, chat assistance
- **Claude Code**: Autonomous coding agent for multi-step tasks

### Tool Usage Guidelines
1. **Semantic Search**: Use Serena's `find_symbol` and `search_for_pattern` to navigate code efficiently
2. **Code Edits**: Prefer Serena's `replace_symbol_body` for symbol-level changes, `replace_string_in_file` for line-level edits
3. **Documentation**: Use Context7 for up-to-date library docs (Flask, SQLAlchemy, etc.)
4. **Testing**: Use Playwright for UI/integration tests, pytest for unit tests
5. **Thinking**: Use Sequential Thinking MCP for complex architectural decisions

### Best Practices
- **Read Minimal Code**: Use symbol overview and targeted reads, avoid reading entire files
- **KISS Principle**: Keep solutions simple, avoid over-engineering
- **Feature Branches**: Always work on feature branches for easy revert
- **Commit Often**: Small, focused commits with clear messages
- **Test Before Merge**: Verify changes with Docker/local tests before merging

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
2. **One team per season**: Teams can't be reused as winners during regular season (weeks 1-18), but reusable in playoffs
3. **No consecutive losses**: If team loses in week N, can't pick same team in week N+1 (must skip a week)
4. **No consecutive opponents**: Can't pick against the same opponent team twice in a row during regular season

**Scoring System (v1.0.13+)**:
- **Win**: 1 point (`Pick.points_earned = 1.0`)
- **Tie**: 0.5 points (`Pick.points_earned = 0.5`, `Pick.is_correct = None`)
- **Loss**: 0 points (`Pick.points_earned = 0.0`, `Pick.is_correct = False`)
- **Tiebreaker**: Margin of victory (winning pick) or negative margin (losing pick) stored in `Pick.tiebreaker_points`
- **Leaderboards**: Sort by `total_score` (sum of `points_earned`), then by `tiebreaker_points`

**Tri-State Pick Results** (CRITICAL):
- `Pick.is_correct = True`: Win (team won the game)
- `Pick.is_correct = False`: Loss (team lost the game)
- `Pick.is_correct = None`: Tie (game ended in a tie)
- Use `is_correct is None` not `is_correct == None` for tie detection

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

### Scoring Architecture (v1.0.16+ Cleanup)

**Single Source of Truth** (KISS Principle):
- **User Model Methods**: Primary source for stats & leaderboards
  - `User.get_season_stats(season_id, group_id=None)`: Returns wins/ties/losses/total_score/tiebreaker
  - `User.get_season_leaderboard(season_id, group_id=None)`: Returns sorted leaderboard with total_score
- **ScoringEngine**: Only for individual pick scoring
  - `ScoringEngine.calculate_pick_score(pick)`: Returns 0.0, 0.5, or 1.0 based on game result
  - Used by `Pick.update_result()` when games finalize

**Removed in v1.0.16 Cleanup** (~240 lines of duplicate code):
- ❌ `ScoringEngine.calculate_user_week_score()` → Use `User.get_season_stats()` filtered by week
- ❌ `ScoringEngine.calculate_user_season_score()` → Use `User.get_season_stats()`
- ❌ `ScoringEngine.get_group_leaderboard()` → Use `User.get_season_leaderboard()`
- ❌ `ScoringEngine.get_weekly_leaderboard()` → Use `User.get_season_leaderboard()` + filter
- ❌ `ScoringEngine.update_all_scores()` → Picks auto-update via `Pick.update_result()`
- ❌ `ScoringEngine.get_pick_accuracy_stats()` → Use `User.get_season_stats()`

**Key Points**:
1. Picks auto-update their `points_earned` when games finalize via `Pick.update_result()`
2. Never call `update_all_scores()` - it's redundant and removed
3. Always use `User.get_season_stats()` for aggregated statistics
4. Always use `User.get_season_leaderboard()` for sorted rankings
5. ScoringEngine only calculates individual pick scores (0.0, 0.5, or 1.0)

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
5. **Tie detection**: Use `is_correct is None` not `is_correct == None` for proper SQL generation
6. **Scoring methods**: Don't use removed `ScoringEngine` methods - use `User` model methods instead
7. **Total score vs wins**: Display `total_score` (includes 0.5 for ties), not `wins` in leaderboards

## Version History & Recent Changes

### v1.0.13 - Tie Game Foundation
- Added tri-state `Pick.is_correct` (True/False/None)
- Implemented 0.5 point scoring for tie games
- Added `Game.is_tie` property for tie detection
- Updated `Pick.update_result()` to handle ties correctly

### v1.0.14 - UI & Template Fixes
- Fixed all templates to display `total_score` instead of `wins`
- Added `total_score` calculation to `User.get_season_stats()`
- Updated dashboard, leaderboard, and group templates
- Fixed accuracy calculations to account for ties

### v1.0.15 - CRITICAL Leaderboard Sort Fix
- Fixed `User.get_season_leaderboard()` to sort by `total_score` not `wins`
- Added `total_score` to leaderboard return dictionary
- Fixed tie count in loss calculations (losses = total_picks - wins - ties)
- Leaderboards now rank correctly with tie points

### v1.0.16 - Modal & API Enhancement
- Added `points_earned` to player-picks API response
- Fixed modal tie display to show yellow "TIE" text
- Enhanced real-time pick updates with accurate tie status

### v1.0.17 - Playoff Team Reuse & Admin Override Fix (2026-01-19)
- **CRITICAL FIX**: Playoff weeks now allow team reuse per game rules
- Fixed `admin_picks_user_data()` to only return regular season teams as "USED"
- Fixed admin override to properly handle existing picks (delete and recreate)
- Admin override now truly bypasses ALL validation including playoff eligibility
- Teams used in playoffs won't show "USED" badge in subsequent playoff weeks
- **Breaking Change Fixed**: Admin interface now works correctly for playoff picks

### cleanup-unused-scoring-code Branch - Code Simplification
- Removed ~240 lines of unused `ScoringEngine` methods
- Established `User` model as single source of truth for stats/leaderboards
- Removed redundant `update_all_scores()` calls from scheduler
- Updated debug scripts to use new architecture
- KISS principle: Simplified scoring to one method per concern
- **Branch Status**: Ready for testing, easy revert via `git checkout main`

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
