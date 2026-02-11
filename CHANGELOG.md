# Changelog

All notable changes to this project will be documented in this file.

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

MIT License with Commercial Use Restriction - See LICENSE file for details.
