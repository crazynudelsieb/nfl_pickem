# Deployment Guide: Scoring Bug Fix

## Issue Summary

**Problem**: Picks were not being scored when games became final due to a bug in the data sync process.

**Root Cause**: The `_update_game_score()` method in [app/utils/data_sync.py](app/utils/data_sync.py) was directly modifying game attributes instead of calling `Game.update_score()`, which prevented `Pick.update_result()` from being triggered.

**Impact on Production**:
- 105 final games on production
- 49 picks for those games
- **10 picks are unscored** (is_correct=NULL) due to this bug

## Files Changed

1. **app/utils/data_sync.py** - Fixed to call `Game.update_score()` method
2. **app/services/scheduler_service.py** - Removed duplicate scoring logic
3. **app/__init__.py** - Fixed Unicode characters for Windows console compatibility
4. **fix_unscored_picks.py** - One-time migration script to fix existing data

## Deployment Steps

### Step 1: Commit and Push Changes

```bash
# In your local repo
cd c:\git\nfl_pickem

git add app/utils/data_sync.py
git add app/services/scheduler_service.py
git add app/__init__.py
git add fix_unscored_picks.py

git commit -m "Fix: Ensure picks are scored when games become final

- Modified data_sync._update_game_score() to call Game.update_score()
- Removed duplicate scoring in scheduler._sync_game_status()
- Deprecated scheduler._process_completed_game() method
- Added fix_unscored_picks.py to retroactively score existing picks
- Fixed Unicode characters causing Windows console errors"

git push origin main
```

### Step 2: Rebuild and Deploy Docker Image

The GitHub Actions workflow should automatically:
1. Build new Docker image with the fixes
2. Push to `ghcr.io/crazynudelsieb/nfl_pickem:latest`

**OR manually build and push:**

```bash
docker build -t ghcr.io/crazynudelsieb/nfl_pickem:latest .
docker push ghcr.io/crazynudelsieb/nfl_pickem:latest
```

### Step 3: Deploy to Production

SSH into production server:

```bash
ssh -i "c:\git\oci_personal_ressources\certs\ssh-private-key.pem" ubuntu@158.180.50.199
```

Pull new image and restart:

```bash
# Pull the new image
docker pull ghcr.io/crazynudelsieb/nfl_pickem:latest

# Restart the web container
docker compose restart web

# Verify it's running
docker ps
docker logs nfl_pickem_web --tail 50
```

### Step 4: Fix Existing Unscored Picks (ONE-TIME ONLY)

Run the migration script to retroactively score the 10 unscored picks:

```bash
docker exec nfl_pickem_web python /app/fix_unscored_picks.py
```

**Expected Output:**
```
============================================================
Fixing Unscored Picks for Final Games
============================================================

Found 105 final games

Found 10 unscored picks to fix:

Game 260 (Week 6): BUF 20 @ NYJ 23 (Final)
  Fixing 2 picks...
    Pick 9 (User 4): is_correct: None -> True/False, points: 0 -> 0/1
    Pick 6 (User 2): is_correct: None -> True/False, points: 0 -> 0/1
    ...

Committing 10 fixed picks to database...
Invalidating caches...

============================================================
SUCCESS! Fixed 10 unscored picks
============================================================

[OK] All picks for final games are now scored!
```

### Step 5: Verify the Fix

Check that all picks are now scored:

```bash
docker exec nfl_pickem_web python -c "from app import create_app, db; from app.models import Game, Pick; app = create_app(); app.app_context().push(); final_game_ids = [g.id for g in Game.query.filter_by(is_final=True).all()]; unscored = Pick.query.filter(Pick.game_id.in_(final_game_ids), Pick.is_correct.is_(None)).count() if final_game_ids else 0; print(f'Unscored picks remaining: {unscored}'); print('✓ All picks scored!' if unscored == 0 else '✗ Still have unscored picks!')"
```

Should output: `Unscored picks remaining: 0`

## What Gets Fixed Automatically

Once the new image is deployed, **all future games** will automatically:
1. Score picks correctly when they become final
2. Update leaderboards in real-time
3. Send WebSocket notifications to users

## What Needs Manual Fix (One-Time)

The **10 existing unscored picks** need the migration script run once. These are from:
- Week 6: 2 picks (games 260, 261)
- Week 7: 8 picks (games 275, 276, 278)

## Testing

After deployment, verify with a test game:

1. Wait for a game to become final (or use the admin panel to manually mark a game as final)
2. Check that picks for that game are automatically scored
3. Verify leaderboard updates correctly
4. Check logs for any errors:

```bash
docker logs nfl_pickem_web --tail 100 -f
```

## Rollback Plan

If issues occur:

```bash
# Revert to previous version
docker pull ghcr.io/crazynudelsieb/nfl_pickem:previous-tag
docker compose restart web
```

## Notes

- The fix is **backward compatible** - no database schema changes required
- The scheduler will continue to work normally
- Redis caching is properly invalidated after scoring updates
- WebSocket notifications will be sent for newly final games

## Monitoring

After deployment, monitor for:
- Scheduler logs showing game status updates
- Pick scoring happening automatically
- No errors in `/app/logs/scheduler.log`
- Leaderboards updating correctly

## Success Criteria

✅ All 10 unscored picks are scored
✅ Future games automatically score picks when final
✅ No errors in application logs
✅ Leaderboards show correct scores
✅ Users receive real-time updates via WebSocket
