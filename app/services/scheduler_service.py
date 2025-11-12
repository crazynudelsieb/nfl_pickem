"""
NFL Pick'em Automatic Sync Scheduler Service

This module handles automatic background syncing of NFL data using APScheduler.
It provides intelligent scheduling that adjusts frequency based on game status.
"""

import atexit
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app import db
from app.models import Game, Pick, Season
from app.utils.cache_utils import (
    commit_refresh_and_invalidate_picks,
    invalidate_model_cache,
)
from app.utils.data_sync import DataSync
from app.utils.scoring import ScoringEngine

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages automatic background scheduling for NFL data syncing"""

    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        self.data_sync = None
        self.scoring_calc = None
        self.is_running = False
        self.sync_stats = {
            "last_sync": None,
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "last_error": None,
            "games_updated": 0,
        }

        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize scheduler with Flask app"""
        self.app = app
        self.scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

        # Initialize services
        with app.app_context():
            self.data_sync = DataSync()
            self.scoring_calc = ScoringEngine()

        # Register shutdown
        atexit.register(self.shutdown)

        # Start scheduler if enabled
        if app.config.get("SCHEDULER_ENABLED", True):
            self.start()

    def start(self):
        """Start the background scheduler"""
        if self.is_running:
            return

        try:
            # Clear any existing jobs
            self.scheduler.remove_all_jobs()

            # Add scheduled jobs
            self._add_core_jobs()

            # Start scheduler
            self.scheduler.start()
            self.is_running = True

            logger.info("Scheduler started successfully")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    def stop(self):
        """Stop the background scheduler"""
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Scheduler stopped")

        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def shutdown(self):
        """Graceful shutdown"""
        self.stop()

    def _add_core_jobs(self):
        """Add core scheduled jobs"""

        # High-frequency live game updates (every 90 seconds during games)
        self.scheduler.add_job(
            func=self._sync_live_games,
            trigger=IntervalTrigger(seconds=90),
            id="sync_live_games",
            name="Sync Live Game Scores",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )

        # Medium-frequency game status updates (every 5 minutes)
        self.scheduler.add_job(
            func=self._sync_game_status,
            trigger=IntervalTrigger(minutes=5),
            id="sync_game_status",
            name="Update Game Status",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

        # Hourly comprehensive sync
        self.scheduler.add_job(
            func=self._hourly_sync,
            trigger=CronTrigger(minute=0),  # Top of every hour
            id="hourly_sync",
            name="Hourly Comprehensive Sync",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )

        # Daily maintenance sync (2 AM UTC)
        self.scheduler.add_job(
            func=self._daily_maintenance,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_maintenance",
            name="Daily Maintenance Sync",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # Weekly schedule update (Tuesday 6 AM UTC)
        self.scheduler.add_job(
            func=self._weekly_schedule_sync,
            trigger=CronTrigger(day_of_week=1, hour=6, minute=0),  # Tuesday
            id="weekly_schedule_sync",
            name="Weekly Schedule Update",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        logger.info("Core scheduled jobs added")

    def _sync_live_games(self):
        """High-frequency sync for live games only with two-phase commit"""
        with self.app.app_context():
            try:
                # Only run during game days and times
                if not self._is_game_time():
                    return

                current_season = Season.get_current_season()
                if not current_season:
                    return

                # Get only live games
                live_games = Game.query.filter(
                    Game.season_id == current_season.id, Game.status == "in_progress"
                ).all()

                if not live_games:
                    return  # Silent - no need to log when no games are live

                # PHASE 1: Update game scores
                updates = 0
                games_finalized = []

                for game in live_games:
                    was_final_before = game.is_final
                    if self.data_sync._update_game_score(game):
                        updates += 1

                        # Track if game just became final
                        if game.is_final and not was_final_before:
                            games_finalized.append(game.id)

                if updates > 0:
                    # Commit game updates
                    db.session.commit()
                    invalidate_model_cache("Game")
                    logger.info(f"Phase 1: Updated {updates} live games")

                    # PHASE 2: Recalculate picks for finalized games
                    if games_finalized:
                        from app.models import Pick

                        total_picks_updated = 0
                        for game_id in games_finalized:
                            picks_updated, week = Pick.recalculate_for_game(game_id, commit=True)
                            total_picks_updated += picks_updated

                            if picks_updated > 0:
                                logger.info(
                                    f"Game {game_id} (week {week}) finalized: "
                                    f"Updated {picks_updated} picks"
                                )

                        logger.info(
                            f"Phase 2: Recalculated {total_picks_updated} picks "
                            f"across {len(games_finalized)} finalized games"
                        )

                    self._update_stats(True, updates)

                    # Trigger real-time updates
                    self._emit_score_updates(live_games)

            except Exception as e:
                db.session.rollback()
                self._update_stats(False)
                self.sync_stats["last_error"] = str(e)
                logger.error(f"Error in live games sync: {e}", exc_info=True)

    def _sync_game_status(self):
        """Medium-frequency sync for game status changes with two-phase commit"""
        with self.app.app_context():
            try:

                current_season = Season.get_current_season()
                if not current_season:
                    return

                # Get games that might need status updates (started but not final)
                current_week = current_season.current_week
                recent_games = Game.query.filter(
                    Game.season_id == current_season.id,
                    Game.week.in_([current_week - 1, current_week, current_week + 1]),
                    Game.is_final.is_(False),
                    Game.game_time <= datetime.now(timezone.utc) + timedelta(hours=6),
                ).all()

                # PHASE 1: Update game scores
                updates = 0
                newly_final_games = []

                for game in recent_games:
                    old_status = game.is_final
                    if self.data_sync._update_game_score(game):
                        updates += 1

                        # Track newly completed games
                        if not old_status and game.is_final:
                            newly_final_games.append(game.id)

                if updates > 0:
                    # Commit game updates
                    db.session.commit()
                    invalidate_model_cache("Game")
                    logger.info(f"Phase 1: Updated {updates} games")

                    # PHASE 2: Recalculate picks for newly finalized games
                    if newly_final_games:
                        from app.models import Pick

                        total_picks_updated = 0
                        for game_id in newly_final_games:
                            picks_updated, week = Pick.recalculate_for_game(game_id, commit=True)
                            total_picks_updated += picks_updated

                            if picks_updated > 0:
                                logger.info(
                                    f"Game {game_id} (week {week}) finalized: "
                                    f"Updated {picks_updated} picks"
                                )

                        logger.info(
                            f"Phase 2: Recalculated {total_picks_updated} picks "
                            f"across {len(newly_final_games)} finalized games"
                        )

                        # Check if Super Bowl just completed
                        self._check_season_completion()

                    self._update_stats(True, updates)

                    # Emit real-time updates for updated games
                    self._emit_score_updates(recent_games)

                    logger.info(
                        f"Updated {updates} games, {len(newly_final_games)} newly completed"
                    )

            except Exception as e:
                db.session.rollback()
                self._update_stats(False)
                self.sync_stats["last_error"] = str(e)
                logger.error(f"Error in game status sync: {e}", exc_info=True)

    def _hourly_sync(self):
        """Comprehensive hourly sync"""
        with self.app.app_context():
            try:
                logger.info("Running hourly comprehensive sync...")

                current_season = Season.get_current_season()
                if not current_season:
                    return

                # Update current week
                current_season.update_current_week()
                db.session.commit()

                # Full score update with two-phase commit
                # Phase 1: Updates game scores
                # Phase 2: Recalculates picks for finalized games
                success, message = self.data_sync.update_live_scores()

                if success:
                    # Picks already updated by two-phase commit in update_live_scores()
                    db.session.expire_all()
                    invalidate_model_cache("Game")
                    invalidate_model_cache("Pick")

                    self._update_stats(True)
                    logger.info(f"Hourly sync completed: {message}")
                else:
                    self._update_stats(False)
                    self.sync_stats["last_error"] = message
                    logger.warning(f"Hourly sync issues: {message}")

            except Exception as e:
                db.session.rollback()
                self._update_stats(False)
                self.sync_stats["last_error"] = str(e)
                logger.error(f"Error in hourly sync: {e}", exc_info=True)

    def _daily_maintenance(self):
        """Daily maintenance and cleanup"""
        with self.app.app_context():
            try:
                logger.info("Running daily maintenance...")

                current_season = Season.get_current_season()
                if not current_season:
                    return

                # Full season data sync
                success, message = self.data_sync.sync_season_data(current_season.year)

                if success:
                    # Clean up old sync stats
                    self._cleanup_old_data()

                    # Picks auto-update via Pick.update_result() when games finalize
                    db.session.expire_all()
                    invalidate_model_cache("Game")
                    invalidate_model_cache("Pick")
                    invalidate_model_cache("Team")

                    self._update_stats(True)
                    logger.info(f"Daily maintenance completed: {message}")
                else:
                    self._update_stats(False)
                    self.sync_stats["last_error"] = message
                    logger.warning(f"Daily maintenance issues: {message}")

            except Exception as e:
                db.session.rollback()
                self._update_stats(False)
                self.sync_stats["last_error"] = str(e)
                logger.error(f"Error in daily maintenance: {e}", exc_info=True)

    def _weekly_schedule_sync(self):
        """Weekly schedule and team updates"""
        with self.app.app_context():
            try:
                logger.info("Running weekly schedule sync...")

                current_season = Season.get_current_season()
                if not current_season:
                    return

                # Full data refresh
                success, message = self.data_sync.sync_season_data(current_season.year)

                if success:
                    # Expire session to prevent stale data reads
                    db.session.expire_all()

                    # Invalidate caches after updates
                    invalidate_model_cache("Game")
                    invalidate_model_cache("Team")
                    invalidate_model_cache("Season")

                    self._update_stats(True)
                    logger.info(f"Weekly schedule sync completed: {message}")
                else:
                    self._update_stats(False)
                    self.sync_stats["last_error"] = message
                    logger.warning(f"Weekly schedule sync issues: {message}")

            except Exception as e:
                db.session.rollback()
                self._update_stats(False)
                self.sync_stats["last_error"] = str(e)
                logger.error(f"Error in weekly schedule sync: {e}", exc_info=True)

    def _is_game_time(self):
        """Check if current time is during typical NFL game hours"""
        now = datetime.now(timezone.utc)

        # Convert to US Eastern Time for game scheduling
        eastern_offset = timedelta(hours=-5)  # EST (adjust for DST as needed)
        eastern_time = now + eastern_offset

        # NFL games typically:
        # Thursday: 8:15 PM ET
        # Sunday: 1:00 PM, 4:05/4:25 PM, 8:20 PM ET
        # Monday: 8:15 PM ET
        game_days = [3, 6, 0]  # Thursday, Sunday, Monday

        if eastern_time.weekday() not in game_days:
            return False

        # Game hours (12 PM - 1 AM ET next day to cover all games + overtime)
        game_start_hour = 12
        game_end_hour = 25  # 1 AM next day

        current_hour = eastern_time.hour
        return game_start_hour <= current_hour <= game_end_hour

    def _check_season_completion(self):
        """Check if season (Super Bowl) is complete and finalize"""
        try:
            current_season = Season.get_current_season()
            if not current_season:
                return

            # Reload season to ensure we have latest data
            db.session.refresh(current_season)

            # Only process if season is not already complete (idempotency)
            if not current_season.is_complete:
                result = current_season.check_super_bowl_complete()
                if result:
                    db.session.commit()
                    logger.info(
                        f"Season {current_season.year} completed! Winners awarded: {len(result.get('global_winners', []))} global, {len(result.get('group_winners', {}))} groups"
                    )
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error checking season completion: {e}", exc_info=True)

    def _emit_score_updates(self, games):
        """Emit real-time score updates via SocketIO"""
        try:
            from app.socketio_handlers import (
                broadcast_game_final,
                broadcast_score_update,
            )

            for game in games:
                broadcast_score_update(game)

                # Check if game just became final
                if game.is_final:
                    broadcast_game_final(game)

        except Exception as e:
            logger.error(f"Error emitting score updates: {e}")

    def _update_stats(self, success, games_updated=0):
        """Update sync statistics"""
        self.sync_stats["last_sync"] = datetime.now(timezone.utc)
        self.sync_stats["total_syncs"] += 1

        if success:
            self.sync_stats["successful_syncs"] += 1
            self.sync_stats["games_updated"] += games_updated
            self.sync_stats["last_error"] = None
        else:
            self.sync_stats["failed_syncs"] += 1

    def _cleanup_old_data(self):
        """Clean up old data and statistics"""
        try:
            # Reset sync stats periodically
            if self.sync_stats["total_syncs"] > 10000:
                self.sync_stats = {
                    "last_sync": self.sync_stats["last_sync"],
                    "total_syncs": 0,
                    "successful_syncs": 0,
                    "failed_syncs": 0,
                    "last_error": None,
                    "games_updated": 0,
                }

        except Exception as e:
            logger.error(f"Error in cleanup: {e}")

    def get_status(self):
        """Get scheduler status information"""
        jobs = []
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                next_run = job.next_run_time
                jobs.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run": next_run.isoformat() if next_run else None,
                        "trigger": str(job.trigger),
                    }
                )

        return {"is_running": self.is_running, "jobs": jobs, "stats": self.sync_stats}

    def force_sync(self, sync_type="live"):
        """Manually trigger a sync"""
        with self.app.app_context():
            try:
                if sync_type == "live":
                    self._sync_live_games()
                elif sync_type == "status":
                    self._sync_game_status()
                elif sync_type == "hourly":
                    self._hourly_sync()
                elif sync_type == "daily":
                    self._daily_maintenance()
                elif sync_type == "weekly":
                    self._weekly_schedule_sync()
                else:
                    raise ValueError(f"Unknown sync type: {sync_type}")

                return True, f"Manual {sync_type} sync completed"

            except Exception as e:
                return False, f"Manual sync failed: {e}"

    def pause_job(self, job_id):
        """Pause a specific job"""
        try:
            self.scheduler.pause_job(job_id)
            return True, f"Job {job_id} paused"
        except Exception as e:
            return False, f"Failed to pause job: {e}"

    def resume_job(self, job_id):
        """Resume a specific job"""
        try:
            self.scheduler.resume_job(job_id)
            return True, f"Job {job_id} resumed"
        except Exception as e:
            return False, f"Failed to resume job: {e}"


# Global scheduler instance
scheduler_service = SchedulerService()
