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


@season.command()
@click.argument("year", type=int)
@click.option("--force", is_flag=True, help="Force finalization even if already complete")
@with_appcontext
def finalize(year, force):
    """Finalize a season and award winners (after Super Bowl)"""
    try:
        season = Season.query.filter_by(year=year).first()
        if not season:
            click.echo(f"❌ Season {year} not found!")
            return

        if season.is_complete and not force:
            click.echo(f"Season {year} is already complete. Use --force to re-award winners.")
            return

        # Check if Super Bowl is complete
        super_bowl_week = season.regular_season_weeks + season.playoff_weeks
        super_bowl_game = Game.query.filter_by(
            season_id=season.id, week=super_bowl_week
        ).first()

        if not super_bowl_game:
            click.echo(f"❌ No Super Bowl game found for season {year}")
            return

        if not super_bowl_game.is_final:
            click.echo(f"❌ Super Bowl game is not final yet. Score: {super_bowl_game.away_score}-{super_bowl_game.home_score}")
            return

        click.echo(f"Super Bowl: {super_bowl_game.away_team.name} vs {super_bowl_game.home_team.name}")
        click.echo(f"Final Score: {super_bowl_game.away_score}-{super_bowl_game.home_score}")

        # If forcing, delete existing winners first
        if force and season.is_complete:
            from app.models import SeasonWinner
            deleted = SeasonWinner.query.filter_by(season_id=season.id).delete()
            click.echo(f"Deleted {deleted} existing winner records")
            season.is_complete = False
            db.session.commit()

        # Finalize the season
        result = season.finalize_season()

        if result:
            click.echo(f"✅ Season {year} finalized!")
            click.echo(f"   Global winners: {len(result.get('global_winners', []))}")
            for winner in result.get('global_winners', []):
                user = User.query.get(winner.user_id)
                click.echo(f"     #{winner.rank} {winner.award_type}: {user.username}")
            click.echo(f"   Group winners: {len(result.get('group_winners', {}))}")
        else:
            click.echo(f"Season {year} was already complete")

    except SQLAlchemyError as e:
        db.session.rollback()
        click.echo(f"❌ Database error: {str(e)}")
        logging.error(f"Season finalization failed - SQL error: {e}", exc_info=True)
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Unexpected error: {str(e)}")
        logging.error(f"Season finalization failed - unexpected error: {e}", exc_info=True)


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
@click.argument("season_id", type=int)
@click.option("--force", is_flag=True, help="Force snapshot creation even if already exists")
@with_appcontext
def create_snapshot(season_id, force):
    """Create regular season snapshot for a season"""
    from app.models.regular_season_snapshot import RegularSeasonSnapshot

    season = Season.query.get(season_id)
    if not season:
        click.echo(f"❌ Season {season_id} not found")
        return

    # Check if snapshot already exists
    existing = RegularSeasonSnapshot.query.filter_by(season_id=season_id).first()
    if existing and not force:
        click.echo(f"⚠️  Snapshot already exists for season {season_id}")
        click.echo(f"   Use --force to recreate")
        return

    if force and existing:
        # Delete existing snapshots
        click.echo(f"🗑️  Deleting existing snapshots...")
        RegularSeasonSnapshot.query.filter_by(season_id=season_id).delete()
        db.session.commit()

    click.echo(f"📸 Creating regular season snapshot for season {season.year}...")

    result = season.create_regular_season_snapshot()

    if isinstance(result, tuple):
        # Error occurred
        success, message = result
        click.echo(f"❌ {message}")
        return

    # Success
    global_count = len(result["global"])
    group_count = sum(len(s) for s in result["groups"].values())

    click.echo(f"✅ Created {global_count} global snapshots")
    click.echo(f"✅ Created {group_count} group snapshots")

    # Display top 4
    top4_snapshots = RegularSeasonSnapshot.query.filter_by(
        season_id=season_id,
        is_playoff_eligible=True,
        group_id=None
    ).order_by(RegularSeasonSnapshot.final_rank).limit(4).all()

    if top4_snapshots:
        click.echo(f"\n🏆 Top 4 (Playoff Eligible):")
        for snap in top4_snapshots:
            click.echo(f"   {snap.final_rank}. {snap.user.username} - {snap.total_wins} wins, {snap.total_score} pts")


@cli.command()
@click.argument("season_id", type=int)
@with_appcontext
def show_playoff_eligible(season_id):
    """Display top 4 playoff-eligible users for a season"""
    from app.models.regular_season_snapshot import RegularSeasonSnapshot

    season = Season.query.get(season_id)
    if not season:
        click.echo(f"❌ Season {season_id} not found")
        return

    # Check if snapshot exists
    snapshots = RegularSeasonSnapshot.query.filter_by(
        season_id=season_id,
        is_playoff_eligible=True,
        group_id=None
    ).order_by(RegularSeasonSnapshot.final_rank).all()

    if not snapshots:
        click.echo(f"⚠️  No playoff snapshots found for season {season.year}")
        click.echo(f"   Run: python manage.py create-snapshot {season_id}")
        return

    click.echo(f"\n🏈 Playoff Eligible Users - Season {season.year}\n")
    click.echo(f"{'Rank':<6} {'Username':<20} {'Wins':<6} {'Score':<8} {'Tiebreaker':<12}")
    click.echo("-" * 60)

    for snap in snapshots:
        click.echo(
            f"{snap.final_rank:<6} {snap.user.username:<20} {snap.total_wins:<6} "
            f"{snap.total_score:<8.1f} {snap.tiebreaker_points:<12.1f}"
        )


@cli.command()
@click.argument("season_id", type=int)
@with_appcontext
def update_superbowl_eligibility(season_id):
    """Update Super Bowl eligibility (top 2 from playoffs) for a season"""
    from app.models.regular_season_snapshot import RegularSeasonSnapshot

    season = Season.query.get(season_id)
    if not season:
        click.echo(f"❌ Season {season_id} not found")
        return

    click.echo(f"🏆 Updating Super Bowl eligibility for season {season.year}...")

    # Update global
    RegularSeasonSnapshot.update_superbowl_eligibility(season_id, group_id=None)

    # Update for each group
    from app.models import Group
    active_groups = Group.query.filter_by(is_active=True).all()
    for group in active_groups:
        RegularSeasonSnapshot.update_superbowl_eligibility(season_id, group_id=group.id)

    # Show results
    sb_eligible = RegularSeasonSnapshot.query.filter_by(
        season_id=season_id,
        is_superbowl_eligible=True,
        group_id=None
    ).all()

    click.echo(f"✅ Updated Super Bowl eligibility")
    click.echo(f"\n🏈 Super Bowl Eligible Users:")
    for snap in sb_eligible:
        click.echo(f"   • {snap.user.username} (Regular season rank: #{snap.final_rank})")


@cli.command()
@click.argument("season_id", type=int)
@with_appcontext
def fix_superbowl(season_id):
    """Fix Super Bowl data: create snapshots if missing and update eligibility.

    Run this after deploying the retroactive snapshot fix to ensure all
    playoff/Super Bowl eligibility data is correct. Safe to run multiple times.

    IMPORTANT: Back up the database before running this command.
    """
    from app.models.regular_season_snapshot import RegularSeasonSnapshot

    season = Season.query.get(season_id)
    if not season:
        click.echo(f"❌ Season {season_id} not found")
        return

    click.echo(f"🏈 Fixing Super Bowl data for season {season.year}...")
    click.echo(f"   Current week: {season.current_week}")
    click.echo()

    # Step 1: Check/create regular season snapshots
    existing = RegularSeasonSnapshot.query.filter_by(season_id=season_id).first()
    if existing:
        click.echo(f"✅ Regular season snapshots already exist")
    else:
        click.echo(f"📸 Creating regular season snapshots...")
        result = season.create_regular_season_snapshot()

        if isinstance(result, tuple):
            _, message = result
            click.echo(f"❌ Failed to create snapshots: {message}")
            return

        global_count = len(result["global"])
        group_count = sum(len(s) for s in result["groups"].values())
        click.echo(f"   Created {global_count} global + {group_count} group snapshots")

    click.echo()

    # Step 2: Update Super Bowl eligibility
    click.echo(f"🏆 Updating Super Bowl eligibility...")

    # Global
    RegularSeasonSnapshot.update_superbowl_eligibility(season_id, group_id=None)

    # Per group
    active_groups = Group.query.filter_by(is_active=True).all()
    for group in active_groups:
        RegularSeasonSnapshot.update_superbowl_eligibility(season_id, group_id=group.id)

    click.echo(f"   Updated for global + {len(active_groups)} groups")
    click.echo()

    # Step 3: Show results
    top4 = RegularSeasonSnapshot.query.filter_by(
        season_id=season_id,
        is_playoff_eligible=True,
        group_id=None
    ).order_by(RegularSeasonSnapshot.final_rank).all()

    if top4:
        click.echo(f"📋 Playoff Eligible (Top 4):")
        for snap in top4:
            sb = "⭐ SB" if snap.is_superbowl_eligible else ""
            click.echo(
                f"   {snap.final_rank}. {snap.user.username} - "
                f"{snap.total_wins} wins, {snap.total_score:.1f} pts {sb}"
            )

    sb_eligible = RegularSeasonSnapshot.query.filter_by(
        season_id=season_id,
        is_superbowl_eligible=True,
        group_id=None
    ).all()

    if sb_eligible:
        click.echo(f"\n🏟️  Super Bowl Eligible:")
        for snap in sb_eligible:
            click.echo(f"   • {snap.user.username}")
    else:
        click.echo(f"\n⚠️  No Super Bowl eligible users found (playoff games may not be final yet)")

    click.echo(f"\n✅ Done! Super Bowl data has been fixed.")


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
