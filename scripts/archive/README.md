# Archived Debug & Diagnostic Scripts

This directory contains historical debugging and one-time fix scripts that were used during development to resolve specific issues. These scripts are archived for reference but should not be executed in production.

## Purpose

These scripts were created to diagnose and fix specific bugs during development, particularly related to:
- Tie game scoring implementation
- Pick result calculations
- Season score verification
- User-specific debugging

## Scripts Overview

### Diagnostic Scripts (Check/Diagnose)
- `check_tie_games.py` - Week 8 specific tie game debugging
- `check_all_ties.py` - Comprehensive tie game analysis across all weeks
- `check_vera_points.py` - User-specific point verification (debugging user "Vera")
- `check_user_scores.py` - General user score verification and comparison
- `diagnose_scoring.py` - Diagnostic for unscored picks and tie games

### Fix Scripts (One-Time Operations)
- `fix_tie_scoring.py` - One-time fix for tie game scoring (0.5 points)
- `fix_unscored_picks.py` - One-time fix for picks that weren't scored
- `manual_rescore.py` - Manual rescoring utility for specific scenarios
- `rescore_all_after_rule_change.py` - Full rescore after rule changes (tie scoring)

## Historical Context

These scripts were created between October 20-27, 2025 to address:

1. **Tie Game Scoring Bug**: Initial implementation didn't properly award 0.5 points for tie games
2. **Unscored Picks**: Some picks weren't being scored when games became final
3. **Rule Changes**: Transition from 1 point (win) / 0 points (loss) to include 0.5 points for ties
4. **User Score Verification**: Ensuring leaderboard calculations matched individual pick results

## Why Archived?

✅ **Issues Resolved**: All identified bugs have been fixed in the main codebase
✅ **Automated**: Pick scoring now happens automatically via `Pick.update_result()` when games become final
✅ **Redundant**: Functionality replaced by proper scheduler service and model methods
✅ **One-Time**: Fix scripts were designed for one-time use only

## Production Usage

**DO NOT RUN THESE SCRIPTS IN PRODUCTION**

These scripts are kept for historical reference only. Modern alternatives:

- **Check scores**: Use admin dashboard at `/admin/scheduler`
- **Rescore picks**: `python manage.py rescore-picks` (if needed)
- **Diagnose issues**: Check logs at `logs/nfl_pickem.log` and `logs/scheduler.log`
- **User stats**: Use `User.get_season_stats()` and `User.get_season_leaderboard()` methods

## References

Related commits that resolved these issues:
- `a20d0df` - Remove unused ScoringEngine methods (~230 lines)
- `4b1587f` - Remove update_all_scores() calls from scheduler
- `bf9bcad` - Simplify scoring to KISS principle
- `0b1cb35` - Implement tie game checks and scoring validation

## Restoration

If you need to review the logic from these scripts:
```bash
git log --all --oneline -- scripts/archive/
```

To restore a specific script temporarily:
```bash
git show <commit-hash>:script_name.py > temp_script.py
```
