# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Season rollover stalled on an upstream 403** - The NFL data feed started
  refusing the hardcoded `NFL-Pickem-App/1.0` User-Agent, so every sync failed
  and the automatic rollover could never create the new season; the app sat on
  the previous, finished season instead. The default User-Agent now identifies
  the app with a contact URL, and `NFL_API_USER_AGENT` overrides it without a
  rebuild.

## [1.3.0] - 2026-07-20

### Added
- **Per-group pick rules** - Group admins can now configure the ruleset per group
  (create/edit group pages): toggle the one-team-per-regular-season rule, toggle
  the no-repeat-opponent rule, and set the number of playoff spots (default 4)
  and Super Bowl spots (default 2). Global picks use the defaults.
- **Automatic season rollover** - The daily maintenance job now creates, syncs
  and activates the new season automatically from August 1st; no container
  restart or manual `manage.py` run needed anymore.
- **Schema guard** - Columns added after a table already exists are now added
  automatically on startup (`app/utils/schema_guard.py`); removed the manual
  `scripts/add_admin_column.py` hack.
- `/auth/change-password`, `/search`, and `/groups/<id>` no longer crash -
  missing templates were added (`change_password.html`, `search_results.html`)
  and the group detail route now redirects to the group page.

### Changed
- **Ruleset clarified** - The "no consecutive losers" rule was removed (it was
  redundant under one-team-per-season and contradicted free team reuse in the
  playoffs). The "no picking against the same opponent two weeks in a row" rule
  is now enforced consistently in one place (`User.can_pick_team`), documented
  on the rules page, and applies to the regular season only.
- Playoff weeks now have no team restrictions at all: teams and opponents can
  be repeated freely (only eligibility is enforced). Super Bowl qualifiers pick
  any team they like - the old opposing-teams constraint was removed.
- Groupmates' picks are hidden until each game kicks off (no more pick-sniping).
- Rules page rewritten to match the actual rules incl. tie scoring (0.5 points)
  and Super Bowl rules.
- **Redis removed.** The app runs as a single Gunicorn worker, so Redis had one
  client and backed three things that do not need it: a Socket.IO message queue
  that only matters across processes, rate limit counters that are equivalent
  in-memory, and a cache of a few read-only reference routes. Caching and rate
  limiting are now in-process. Drop the `redis` service from your compose file
  (`docker compose up -d --remove-orphans`); `CACHE_TYPE` and `CACHE_REDIS_URL`
  are no longer read. A shared backend is only needed to run more than one
  process, which also requires sticky session routing at the proxy.
- Cache invalidation no longer runs on pick and user writes at all (the hot
  path during live games); writes to game, season and team data clear the
  cache, which holds only the handful of cached reference routes.
- Leaderboards (all-time, playoff mode, season) rebuilt to use a fixed number
  of queries instead of dozens of queries per user; the duplicated playoff
  leaderboard code from three pages now lives in `app/utils/leaderboard.py`.

### Fixed
- **Security: pick deletion IDOR** - Group admins could delete or inspect ANY
  user's picks by ID; both endpoints now verify the pick belongs to the group.
- **Security: debug endpoints removed** (`/api/debug/avatars`, `/api/debug/group/<id>`)
  which exposed all users and any group's data to any logged-in user.
- **Security: rate limiter spoofing** - Client-supplied `X-Forwarded-For` was
  trusted directly; now handled by ProxyFix with a configurable hop count
  (`PROXY_HOPS`, default 1).
- **Security: production config** - `FLASK_ENV=production` now selects the
  production config even without `FLASK_CONFIG`; production refuses to start
  without an explicit `SECRET_KEY`; default admin gets a random generated
  password instead of `ChangeMe123!`; Postgres/Redis ports bound to localhost;
  CSP `img-src` no longer allows all https hosts; CDN scripts pinned with SRI.
- **Admin pick management corrupted per-group picks** - Admin flows looked up
  and deleted picks without a group filter, so managing a pick could modify or
  delete the user's pick in a *different* group, and `Pick.create_pick` always
  created global picks. All admin pick paths are now group-aware.
- **Admins could create duplicate week picks** - Switching a user's pick to a
  different game as admin left both picks in place (double points).
- **Live scores API returned nothing** - `/api/scores/live` filtered on the
  Python-only `Game.status` property; now filters on real columns.
- **Super Bowl eligibility job crashed on every run** (`len(None)` after commit).
- **Late-created groups never got playoff snapshots** - snapshot creation now
  checks per group instead of bailing when any snapshot exists.
- **TestingConfig used the real database** - the in-memory SQLite setting was
  overridden by the environment-based database URI.
- **Pick submissions accepted any group slug** without a membership check.
- Tie picks were re-processed by the "self-healing" sync forever.
- `/health` now actually checks database connectivity.
- Removed dead code (`_is_game_time`, `broadcast_pick_update`, `cached_query`,
  unused pick helpers) and unused dependencies (sportsipy, bcrypt, asgiref);
  deleted a stray committed `git diff` dump ("coring architecture").

## [1.2.34] - 2026-02-11

### Fixed
- **All-Time Statistics Missed Games** - Fixed all-time leaderboard counting playoff/Super Bowl weeks as missed for ineligible users
- Uses same snapshot-based eligibility checks as season stats to filter eligible weeks

## [1.2.33] - 2026-02-11

### Fixed
- **CRITICAL: Recursion Error** - Fixed infinite recursion in `get_season_stats()` when checking eligibility
- Root cause: `is_superbowl_eligible()` calls `get_season_stats()` which called eligibility checks, creating a loop
- Solution: Created lightweight snapshot-only helper methods (`_check_playoff_eligible_from_snapshot`, `_check_superbowl_eligible_from_snapshot`)

## [1.2.32] - 2026-02-11

### Fixed
- **Playoff Missed Games Calculation** - Users who didn't qualify for playoffs/Super Bowl no longer have those weeks counted as "missed games"
- Playoff eligibility (top 4) is checked before counting playoff weeks as missed
- Super Bowl eligibility (top 2 playoff performers) is checked before counting Super Bowl week as missed
- This ensures accuracy percentages are fair to users who weren't eligible to participate

## [1.2.31] - 2026-02-11

### Fixed
- **CRITICAL: Leaderboard Consistency** - Fixed Super Bowl picks not being counted in group/dashboard leaderboards
- **Root Cause**: Pick submissions via AJAX were missing the group parameter, causing picks for users with per-group picks (`picks_are_global=false`) to be saved with `group_id=NULL` instead of the correct group ID
- **Impact**: Super Bowl (week 22) picks were not showing in group leaderboards, dashboard views, or player picks modals, but appeared correctly in global leaderboard
- **Fix**: Added group slug to AJAX form submissions in `current_picks.html`
- **Data Migration**: Fixed 2 existing Super Bowl picks in production database that had NULL group_id

## [Unreleased] - 2025-10-09

### Fixed
- **UI Stability**: Fixed race condition where "Teams Used" badges would accumulate incorrectly when rapidly changing picks
- **Pick Status**: Fixed "✓ PICKED" badges showing on multiple games when switching picks quickly
- **Modal Alignment**: Fixed player picks modal table column alignment issues on both desktop and mobile
- **Mobile UX**: Removed horizontal scrollbar from player picks modal on mobile devices

### Changed
- Implemented debounced rebuild strategy for badge updates to prevent race conditions
- Added desktop-specific CSS for player picks modal table alignment
- Improved column width distribution in player picks modal (Week: 12%, Matchup: 32%, Pick: 18%, Score: 16%, Result: 16%, Points: 6%)

## [Previous] - October 2025

### Added
- Avatar system with Gravatar integration and custom image uploads
- Group management features with slug-based URLs
- Group disable/enable functionality for admins
- Per-group picks vs global picks toggle
- Statistics dashboard with detailed user analytics
- Tiebreaker points system
- Season winners tracking
- Comprehensive Docker setup with multi-stage builds
- Password reset functionality
- Responsive mobile interface with PWA support

### Fixed
- Pick validation for consecutive team usage rules
- Multiple picks submission bug
- Audit trail for admin actions
- Group deletion with proper cascading
- Pick table width responsive issues

### Security
- CSRF protection across all forms
- Input validation and sanitization
- Secure session management
- Rate limiting on API endpoints

## License

PolyForm Noncommercial License 1.0.0 - See LICENSE file for details.
Commercial use requires a separate license: appchen@outlook.at
