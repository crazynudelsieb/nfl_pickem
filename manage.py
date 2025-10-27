#!/usr/bin/env python3
"""
NFL Pick'em Management CLI

This script provides command-line management functionality for the NFL Pick'em application.
"""

import logging
import os
from datetime import date

import click
from flask.cli import with_appcontext
from flask_migrate import downgrade, migrate, upgrade
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app, db
from app.models import Game, Group, Season, Team, User
from app.utils.data_sync import DataSync

app = create_app()


@click.group()
def cli():
    """NFL Pick'em Management CLI"""
    pass


# Season Management Commands
@cli.group()
def season():
    """Season management commands"""
    pass


@season.command()
@click.argument("year", type=int)
@click.option(
    "--start-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Season start date (YYYY-MM-DD)",
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Season end date (YYYY-MM-DD)",
)
@click.option("--activate", is_flag=True, help="Activate this season")
@with_appcontext
def create(year, start_date, end_date, activate):
    """Create a new season"""
    try:
        # Set default dates if not provided
        if not start_date:
            start_date = date(year, 9, 1)  # September 1st
        else:
            start_date = start_date.date()

        if not end_date:
            end_date = date(year + 1, 2, 15)  # February 15th next year
        else:
            end_date = end_date.date()

        # Check if season already exists
        existing = Season.query.filter_by(year=year).first()
        if existing:
            click.echo(f"Season {year} already exists!")
            return

        # Create season
        season = Season.create_season(year, start_date, end_date)

        if activate:
            season.activate()

        db.session.commit()
        click.echo(f"✅ Created season {year} ({start_date} to {end_date})")

        if activate:
            click.echo(f"✅ Activated season {year}")

    except IntegrityError as e:
        db.session.rollback()
        click.echo(f"❌ Season {year} already exists!")
        logging.error(f"Season creation failed - integrity error: {e}")
    except SQLAlchemyError as e:
        db.session.rollback()
        click.echo(f"❌ Database error creating season: {str(e)}")
        logging.error(f"Season creation failed - SQL error: {e}")
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Unexpected error creating season: {str(e)}")
        logging.error(f"Season creation failed - unexpected error: {e}")


@season.command()
@click.argument("year", type=int)
@with_appcontext
def activate(year):
    """Activate a season"""
    try:
        season = Season.query.filter_by(year=year).first()
        if not season:
            click.echo(f"❌ Season {year} not found!")
            return

        season.activate()
        db.session.commit()
        click.echo(f"✅ Activated season {year}")

    except SQLAlchemyError as e:
        db.session.rollback()
        click.echo(f"❌ Database error activating season: {str(e)}")
        logging.error(f"Season activation failed - SQL error: {e}")
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Unexpected error activating season: {str(e)}")
        logging.error(f"Season activation failed - unexpected error: {e}")


@season.command()
@with_appcontext
def list_seasons():
    """List all seasons"""
    seasons = Season.query.order_by(Season.year.desc()).all()

    if not seasons:
        click.echo("No seasons found.")
        return

    click.echo("Seasons:")
    for s in seasons:
        status = "🟢 ACTIVE" if s.is_active else "⚪ Inactive"
        complete = "✅ Complete" if s.is_complete else f"Week {s.current_week}"
        click.echo(f"  {s.year}: {status} - {complete}")


# Data Sync Commands
@cli.group()
def sync():
    """Data synchronization commands"""
    pass


@sync.command()
@click.argument("year", type=int)
@with_appcontext
def teams(year):
    """Sync teams for a season"""
    try:
        season = Season.query.filter_by(year=year).first()
        if not season:
            click.echo(f"❌ Season {year} not found! Create it first.")
            return

        click.echo(f"Syncing teams for {year} season...")
        data_sync = DataSync()

        # Sync just teams
        teams = data_sync._sync_teams(season)
        db.session.commit()

        click.echo(f"✅ Synced {len(teams)} teams for {year}")

    except Exception as e:
        click.echo(f"❌ Error syncing teams: {str(e)}")


@sync.command()
@click.argument("year", type=int)
@with_appcontext
def games(year):
    """Sync games for a season"""
    try:
        season = Season.query.filter_by(year=year).first()
        if not season:
            click.echo(f"❌ Season {year} not found!")
            return

        teams = Team.query.filter_by(season_id=season.id).all()
        if not teams:
            click.echo(f"❌ No teams found for {year}! Sync teams first.")
            return

        click.echo(f"Syncing games for {year} season...")
        data_sync = DataSync()

        # Sync games
        games = data_sync._sync_games(season, teams)
        db.session.commit()

        click.echo(f"✅ Synced {len(games)} games for {year}")

    except Exception as e:
        click.echo(f"❌ Error syncing games: {str(e)}")


@sync.command()
@click.argument("year", type=int)
@with_appcontext
def all(year):
    """Sync all data for a season (teams + games)"""
    try:
        click.echo(f"Starting full sync for {year}...")
        data_sync = DataSync()

        success, message = data_sync.sync_season_data(year)

        if success:
            click.echo(f"✅ {message}")
        else:
            click.echo(f"❌ {message}")

    except Exception as e:
        click.echo(f"❌ Error syncing data: {str(e)}")


@sync.command()
@with_appcontext
def scores():
    """Update live scores for current season"""
    try:
        click.echo("Updating live scores...")
        data_sync = DataSync()

        success, message = data_sync.update_live_scores()

        if success:
            click.echo(f"✅ {message}")
        else:
            click.echo(f"❌ {message}")

    except Exception as e:
        click.echo(f"❌ Error updating scores: {str(e)}")


# User Management Commands
@cli.group()
def user():
    """User management commands"""
    pass


@user.command()
@click.argument("username")
@click.argument("email")
@click.argument("password")
@click.option("--first-name", help="First name")
@click.option("--last-name", help="Last name")
@with_appcontext
def create_admin(username, email, password, display_name=None):
    """Create an admin user"""
    try:
        # Check if user exists
        existing = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            click.echo(
                f"❌ User with username '{username}' or email '{email}' already exists!"
            )
            return

        # Create user
        user = User(
            username=username,
            email=email,
            display_name=display_name,
            is_active=True,
            is_verified=True,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        click.echo(f"✅ Created admin user '{username}' ({email})")

    except Exception as e:
        click.echo(f"❌ Error creating user: {str(e)}")


@user.command()
@with_appcontext
def list_users():
    """List all users"""
    users = User.query.order_by(User.created_at.desc()).all()

    if not users:
        click.echo("No users found.")
        return

    click.echo("Users:")
    for u in users:
        status = "🟢" if u.is_active else "🔴"
        verified = "✅" if u.is_verified else "⚠️"
        click.echo(f"  {status} {verified} {u.username} ({u.email}) - {u.full_name}")


# Database Commands
@cli.group()
def db_cmd():
    """Database commands"""
    pass


@db_cmd.command()
@with_appcontext
def init_db():
    """Initialize database tables"""
    try:
        db.create_all()
        click.echo("✅ Database tables created successfully!")
    except Exception as e:
        click.echo(f"❌ Error initializing database: {str(e)}")


@db_cmd.command()
@with_appcontext
def reset():
    """⚠️  DANGER: Drop and recreate all tables"""
    if not click.confirm("This will DELETE ALL DATA. Are you sure?"):
        click.echo("Cancelled.")
        return

    try:
        db.drop_all()
        db.create_all()
        click.echo("✅ Database reset successfully!")
    except Exception as e:
        click.echo(f"❌ Error resetting database: {str(e)}")


# Database Migration Commands
@cli.group()
def db_migrate():
    """Database migration commands"""
    pass


@db_migrate.command()
@with_appcontext
def init_migrations():
    """Initialize migrations repository"""
    try:
        if os.path.exists("migrations"):
            click.echo("❌ Migrations directory already exists!")
            return

        # Use the Flask-Migrate init function
        from flask_migrate import init as flask_migrate_init
        flask_migrate_init()
        click.echo("✅ Migrations repository initialized!")
    except Exception as e:
        click.echo(f"❌ Error initializing migrations: {str(e)}")


@db_migrate.command()
@click.option("-m", "--message", required=True, help="Migration message")
@with_appcontext
def create_migration(message):
    """Create a new migration"""
    try:
        migrate(message=message)
        click.echo(f"✅ Migration created: {message}")
    except Exception as e:
        click.echo(f"❌ Error creating migration: {str(e)}")


@db_migrate.command()
@click.option("--revision", default="head", help="Revision to upgrade to")
@with_appcontext
def apply_migrations(revision):
    """Apply migrations to database"""
    try:
        upgrade(revision=revision)
        click.echo(f"✅ Migrations applied to {revision}")
    except Exception as e:
        click.echo(f"❌ Error applying migrations: {str(e)}")


@db_migrate.command()
@click.option("--revision", required=True, help="Revision to downgrade to")
@with_appcontext
def rollback_migration(revision):
    """Rollback migrations to specific revision"""
    try:
        downgrade(revision=revision)
        click.echo(f"✅ Rolled back to {revision}")
    except Exception as e:
        click.echo(f"❌ Error rolling back: {str(e)}")


# Info Commands
@cli.command()
@click.option(
    "--season",
    type=int,
    help="Season year to update (default: current season)",
)
@with_appcontext
def update_tie_games(season):
    """Update all tie game picks with half points (retroactive fix)"""
    click.echo("🏈 Updating Tie Game Picks")
    click.echo("=" * 40)

    # Determine which season to update
    if season:
        season_obj = Season.query.filter_by(year=season).first()
        if not season_obj:
            click.echo(f"❌ Season {season} not found")
            return
    else:
        season_obj = Season.get_current_season()
        if not season_obj:
            click.echo("❌ No current season found")
            return

    click.echo(f"📅 Season: {season_obj.year}")

    # Find all tie games
    tie_games = Game.query.filter(
        Game.season_id == season_obj.id,
        Game.is_final == True,
        Game.home_score == Game.away_score,
        Game.home_score.isnot(None),
    ).all()

    click.echo(f"🔍 Found {len(tie_games)} tie games")

    if not tie_games:
        click.echo("✅ No tie games to update")
        return

    # Update picks for each tie game
    updated_count = 0
    for game in tie_games:
        click.echo(
            f"\n🎮 Game: {game.away_team.abbreviation} @ {game.home_team.abbreviation} "
            f"(Week {game.week}) - Score: {game.home_score}-{game.away_score}"
        )

        # Get all picks for this game
        picks = Pick.query.filter_by(game_id=game.id).all()

        for pick in picks:
            # Update the pick with tie game logic
            pick.is_correct = None
            pick.points_earned = 0.5  # Half point for ties
            total_score = game.total_score or 0
            pick.tiebreaker_points = total_score / 2.0

            updated_count += 1
            click.echo(
                f"   ✅ Updated pick for user {pick.user_id}: "
                f"0.5 points, tiebreaker: {pick.tiebreaker_points}"
            )

    # Commit all changes
    try:
        db.session.commit()
        click.echo(f"\n🎉 Successfully updated {updated_count} tie game picks!")
    except Exception as e:
        db.session.rollback()
        click.echo(f"\n❌ Error updating picks: {str(e)}")


@cli.command()
@with_appcontext
def status():
    """Show application status"""
    click.echo("🏈 NFL Pick'em Application Status")
    click.echo("=" * 40)

    # Database connection
    try:
        db.session.execute("SELECT 1")
        click.echo("✅ Database: Connected")
    except Exception as e:
        click.echo(f"❌ Database: Error - {str(e)}")

    # Current season
    current_season = Season.get_current_season()
    if current_season:
        click.echo(
            f"✅ Current Season: {current_season.year} (Week {current_season.current_week})"
        )
    else:
        click.echo("⚠️  Current Season: None active")

    # User count
    user_count = User.query.filter_by(is_active=True).count()
    click.echo(f"👥 Active Users: {user_count}")

    # Group count
    group_count = Group.query.filter_by(is_active=True).count()
    click.echo(f"🏆 Active Groups: {group_count}")

    # Game count (current season)
    if current_season:
        game_count = Game.query.filter_by(season_id=current_season.id).count()
        final_count = Game.query.filter_by(
            season_id=current_season.id, is_final=True
        ).count()
        click.echo(f"🏈 Games: {final_count}/{game_count} completed")


if __name__ == "__main__":
    with app.app_context():
        cli()
