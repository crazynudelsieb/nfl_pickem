#!/usr/bin/env python3
"""
NFL Pick'em Startup Script

Auto-initializes the application on first container startup:
- Detects current NFL season
- Loads NFL data (teams, games)
- Creates default admin user
- Activates season
"""

import os
import sys
import time
from datetime import date, datetime

# Eventlet monkey patching MUST be first
import eventlet
eventlet.monkey_patch()

# Add app directory to path
sys.path.insert(0, "/app")

# Set up environment
os.environ.setdefault("FLASK_APP", "run.py")
os.environ.setdefault("FLASK_ENV", "production")

from app import create_app, db
from app.models import Game, Season, Team, User
from app.utils.data_sync import DataSync


def wait_for_db(app, max_retries=30):
    """Wait for database to be ready"""
    print("Waiting for database connection...")

    for i in range(max_retries):
        try:
            with app.app_context():
                result = db.session.execute(db.text("SELECT 1"))
                result.fetchone()
                print("Database connected!")
                return True
        except Exception as e:
            if i < max_retries - 1:
                print(f"Attempt {i+1}/{max_retries} failed, retrying in 2s...")
                print(f"   Error: {str(e)}")
                time.sleep(2)
            else:
                print(f"Database connection failed after {max_retries} attempts: {e}")
                return False
    return False


def get_current_nfl_season():
    """Determine current NFL season year"""
    now = datetime.now()

    # NFL season typically runs Sept-Feb
    # If it's Jan-July, we're in the previous season
    # If it's Aug-Dec, we're in the current season

    if now.month <= 7:  # Jan-July = previous year's season
        return now.year - 1
    else:  # Aug-Dec = current year's season
        return now.year


def create_default_admin():
    """Create default admin user if none exists"""
    admin = User.query.filter_by(username="admin").first()

    if admin:
        print("Admin user already exists")
        return admin

    print("Creating default admin user...")

    admin = User(
        username="admin",
        email="admin@nflpickem.com",
        display_name="Administrator",
        is_active=True,
        is_verified=True,
    )
    
    # Use environment variable for admin password, fallback to secure default
    admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")
    admin.set_password(admin_password)

    db.session.add(admin)
    db.session.commit()

    print("Created default admin user (username: admin)")
    print("WARNING: Please change the default password after first login!")
    if not os.environ.get("DEFAULT_ADMIN_PASSWORD"):
        print("WARNING: Using default password. Set DEFAULT_ADMIN_PASSWORD environment variable for security!")

    return admin


def initialize_season_data():
    """Initialize current season with data"""
    current_year = get_current_nfl_season()

    print(f"Initializing {current_year} NFL season...")

    # Check if season already exists and has data
    season = Season.query.filter_by(year=current_year).first()

    if season:
        team_count = Team.query.filter_by(season_id=season.id).count()
        game_count = Game.query.filter_by(season_id=season.id).count()

        if team_count > 0 and game_count > 0:
            print(
                f"Season {current_year} already has data ({team_count} teams, {game_count} games)"
            )

            # Make sure it's active
            if not season.is_active:
                season.activate()
                db.session.commit()
                print(f"Activated season {current_year}")

            return season

    # Initialize data sync
    data_sync = DataSync()

    try:
        # Try to sync current season
        print(f"Syncing {current_year} season data from ESPN...")
        success, message = data_sync.sync_season_data(current_year)

        if success:
            print(f"SUCCESS: {message}")

            # Activate the season
            season = Season.query.filter_by(year=current_year).first()
            if season:
                season.activate()
                db.session.commit()
                print(f"Activated {current_year} season")

            return season
        else:
            print(f"WARNING: Failed to sync {current_year}: {message}")

            # Try previous season as fallback
            fallback_year = current_year - 1
            print(f"Trying fallback to {fallback_year} season...")

            success, message = data_sync.sync_season_data(fallback_year)

            if success:
                print(f"SUCCESS: {message}")

                season = Season.query.filter_by(year=fallback_year).first()
                if season:
                    season.activate()
                    db.session.commit()
                    print(f"Activated {fallback_year} season (fallback)")
                    print(
                        f"WARNING: Note: Currently showing {fallback_year} season data"
                    )

                return season
            else:
                print(f"ERROR: Failed to sync fallback season: {message}")
                return None

    except Exception as e:
        print(f"ERROR: Error during season initialization: {e}")
        return None


def run_database_migrations():
    """Run database migrations for schema changes"""
    print("\n🔄 Checking for database migrations...")

    try:
        # Check if points_earned is already Float type
        result = db.session.execute(db.text("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name='picks' AND column_name='points_earned'
        """))
        current_type = result.fetchone()

        if current_type and current_type[0] == 'integer':
            print("   Converting points_earned to Float...")
            db.session.execute(db.text("""
                ALTER TABLE picks
                ALTER COLUMN points_earned TYPE DOUBLE PRECISION
            """))
            db.session.commit()
            print("   ✅ Converted points_earned to Float")
        else:
            print(f"   ✅ points_earned already type: {current_type[0] if current_type else 'unknown'}")

        # Check if tiebreaker_points is already Float type
        result = db.session.execute(db.text("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name='picks' AND column_name='tiebreaker_points'
        """))
        current_type = result.fetchone()

        if current_type and current_type[0] == 'integer':
            print("   Converting tiebreaker_points to Float...")
            db.session.execute(db.text("""
                ALTER TABLE picks
                ALTER COLUMN tiebreaker_points TYPE DOUBLE PRECISION
            """))
            db.session.commit()
            print("   ✅ Converted tiebreaker_points to Float")
        else:
            print(f"   ✅ tiebreaker_points already type: {current_type[0] if current_type else 'unknown'}")

        print("✅ Database migrations complete")
        return True

    except Exception as e:
        print(f"⚠️  Migration error (may be normal on first run): {e}")
        db.session.rollback()
        return False


def update_tie_game_picks():
    """Update all tie game picks with half points"""
    print("\n🔄 Checking for tie game picks to update...")

    try:
        # Find all tie games with picks
        result = db.session.execute(db.text("""
            SELECT COUNT(DISTINCT p.id)
            FROM picks p
            JOIN games g ON p.game_id = g.id
            WHERE g.is_final = true
            AND g.home_score = g.away_score
            AND g.home_score IS NOT NULL
            AND (p.is_correct IS NOT NULL OR p.points_earned != 0.5)
        """))

        count = result.fetchone()[0]

        if count == 0:
            print("   ✅ No tie game picks need updating")
            return True

        print(f"   Found {count} tie game picks to update...")

        # Update tie game picks
        db.session.execute(db.text("""
            UPDATE picks
            SET
                points_earned = 0.5,
                tiebreaker_points = (
                    SELECT (COALESCE(g.home_score, 0) + COALESCE(g.away_score, 0)) / 2.0
                    FROM games g
                    WHERE g.id = picks.game_id
                ),
                is_correct = NULL
            WHERE game_id IN (
                SELECT id FROM games
                WHERE is_final = true
                AND home_score = away_score
                AND home_score IS NOT NULL
            )
        """))

        db.session.commit()
        print(f"   ✅ Updated {count} tie game picks with 0.5 points")
        return True

    except Exception as e:
        print(f"⚠️  Tie game update error: {e}")
        db.session.rollback()
        return False


def check_initialization_needed():
    """Check if initialization is needed"""
    try:
        # Check if we have any active seasons
        active_season = Season.get_current_season()

        # Check if we have admin user
        admin_exists = User.query.filter_by(username="admin").first() is not None

        if active_season and admin_exists:
            team_count = Team.query.filter_by(season_id=active_season.id).count()
            game_count = Game.query.filter_by(season_id=active_season.id).count()

            if team_count > 0 and game_count > 0:
                print("Application already initialized")
                print(
                    f"Active season: {active_season.year} ({team_count} teams, {game_count} games)"
                )
                return False

        return True

    except Exception as e:
        print(f"Initialization check failed, proceeding with setup: {e}")
        return True


def main():
    """Main initialization function"""
    print("NFL Pick'em Auto-Initialization")
    print("=" * 50)

    # Create Flask app
    app = create_app()

    # Wait for database (outside app context first)
    if not wait_for_db(app):
        print("ERROR: Startup failed - database not available")
        sys.exit(1)

    with app.app_context():

        # Create database tables
        try:
            db.create_all()
            print("Database tables ready")
        except Exception as e:
            print(f"ERROR: Failed to create database tables: {e}")
            print(
                f"   Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')}"
            )
            sys.exit(1)

        # Run database migrations (always check, idempotent)
        run_database_migrations()

        # Update tie game picks (always check, idempotent)
        update_tie_game_picks()

        # Check if initialization is needed
        if not check_initialization_needed():
            return

        print("Starting first-time setup...")

        # Create default admin user
        create_default_admin()

        # Initialize season data
        season = initialize_season_data()

        if season:
            print("=" * 50)
            print("SUCCESS: NFL Pick'em is ready!")
            print(f"Active Season: {season.year}")
            print("Access the app at http://localhost:5000")
            print("Login: admin / admin123")
            print("WARNING: Remember to change the default password!")
            print("=" * 50)
        else:
            print("=" * 50)
            print("WARNING: Setup completed with warnings")
            print("Access the app at http://localhost:5000")
            print("Login: admin / admin123")
            print("NOTE: You may need to manually load NFL data")
            print("=" * 50)


if __name__ == "__main__":
    main()
