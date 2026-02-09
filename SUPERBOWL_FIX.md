# Super Bowl Fix Instructions

## Problem Identified

The scheduler's `_sync_live_games()` function had a restrictive time check (`_is_game_time()`) that only synced games during typical NFL hours (12 PM - 1 AM ET on Thu/Sun/Mon). The Super Bowl this morning (CET time) was likely outside this window, preventing automatic updates from ESPN.

## Fix Applied

**File Modified:** [app/services/scheduler_service.py](app/services/scheduler_service.py#L187-L192)
- **Removed** the `_is_game_time()` check from `_sync_live_games()`
- Now syncs whenever there are actual live games in the database, regardless of day/time
- The query itself filters for live games, so no unnecessary syncs will occur

## Commands to Run on OCI Server

### 1. SSH into your server
```bash
ssh -i "c:\git\oci_personal_ressources\certs\ssh-private-key.pem" -o StrictHostKeyChecking=no ubuntu@158.180.50.199
```

### 2. Navigate to app directory
```bash
cd /path/to/nfl_pickem
# If using Docker:
# cd /home/ubuntu/nfl_pickem  (or wherever you deployed it)
```

### 3. Pull latest code (contains the scheduler fix)
```bash
git pull origin main
```

### 4. Restart the app to apply scheduler fix
```bash
# If using Docker:
docker compose down
docker compose up -d

# If running directly:
sudo systemctl restart nfl_pickem
# or
pkill -f "python.*run.py" && python run.py &
```

### 5. Run the fix script to sync Super Bowl data and update picks
```bash
# If using Docker:
docker compose exec web python scripts/fix_superbowl.py

# If running directly:
python scripts/fix_superbowl.py
```

### 6. Verify the fixes
```bash
# If using Docker:
docker compose exec web python -c "
from app import create_app, db
from app.models import Game, Pick, User, Season

app = create_app()
with app.app_context():
    season = Season.get_current_season()
    sb_game = Game.query.filter_by(season_id=season.id, week=22).first()
    
    print(f'Super Bowl: {sb_game.away_team.name} @ {sb_game.home_team.name}')
    print(f'Score: {sb_game.away_score} - {sb_game.home_score}')
    print(f'Final: {sb_game.is_final}')
    print()
    
    martina = User.query.filter_by(username='martina').first()
    tb = User.query.filter_by(username='tb').first()
    
    if martina:
        pick = Pick.query.filter_by(user_id=martina.id, game_id=sb_game.id).first()
        if pick:
            print(f'Martina picked: {pick.selected_team.name}')
            print(f'  Correct: {pick.is_correct}, Points: {pick.points_earned}')
    
    if tb:
        pick = Pick.query.filter_by(user_id=tb.id, game_id=sb_game.id).first()
        if pick:
            print(f'TB picked: {pick.selected_team.name}')
            print(f'  Correct: {pick.is_correct}, Points: {pick.points_earned}')
"
```

## What the Script Does

The [scripts/fix_superbowl.py](scripts/fix_superbowl.py) script will:
1. Sync Super Bowl (week 22) data from ESPN API
2. Find or create picks for:
   - **Martina** → Seattle Seahawks
   - **TB** → New England Patriots  
3. Update pick results if the game is final
4. Display the results

## Alternative: Manual Database Update

If you need to update picks manually via database:

```bash
docker compose exec db psql -U nfl_user -d nfl_pickem_db

-- Find the Super Bowl game ID
SELECT id, week, home_team_id, away_team_id, home_score, away_score, is_final 
FROM games WHERE week = 22;

-- Find team IDs
SELECT id, name FROM teams WHERE name LIKE '%Seahawks%' OR name LIKE '%Patriots%';

-- Find user IDs  
SELECT id, username FROM users WHERE username IN ('martina', 'tb');

-- Update or insert picks (replace IDs with actual values)
UPDATE picks SET selected_team_id = <seahawks_id> 
WHERE user_id = <martina_id> AND game_id = <superbowl_game_id>;

UPDATE picks SET selected_team_id = <patriots_id>
WHERE user_id = <tb_id> AND game_id = <superbowl_game_id>;

-- Recalculate pick results
-- Exit psql and run:
docker compose exec web python -c "
from app import create_app, db
from app.models import Pick
app = create_app()
with app.app_context():
    picks_updated, week = Pick.recalculate_for_game(<superbowl_game_id>, commit=True)
    print(f'Updated {picks_updated} picks for week {week}')
"
```

## Future Prevention

With the scheduler fix in place, this issue should not occur again. The scheduler will now:
- Check for live games every 90 seconds regardless of day/time
- Sync immediately when games start, even if outside typical hours
- Handle playoff games (including Super Bowl) properly

The only requirement is that games must exist in the database (created by weekly/daily syncs).
