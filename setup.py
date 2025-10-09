#!/usr/bin/env python3
"""
Quick setup script for NFL Pick'em application
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and show progress"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False


def main():
    print("🏈 NFL Pick'em Quick Setup")
    print("=" * 40)

    # Check if .env file exists
    if not Path(".env").exists():
        print("⚠️  .env file not found. Copying from .env.example...")
        if Path(".env.example").exists():
            run_command("cp .env.example .env", "Creating .env file")
            print("📝 Please edit .env file with your settings before continuing!")
            return
        else:
            print("❌ .env.example not found!")
            return

    # Check Docker
    if not run_command("docker --version", "Checking Docker"):
        print("❌ Docker is required. Please install Docker first.")
        return

    if not run_command("docker-compose --version", "Checking Docker Compose"):
        print("❌ Docker Compose is required. Please install Docker Compose first.")
        return

    # Start database
    if run_command(
        "docker-compose -f docker-compose.dev.yml up -d db", "Starting database"
    ):
        print("✅ Database services started")
    else:
        print("❌ Failed to start database services")
        return

    # Install Python dependencies
    if run_command("pip install -r requirements.txt", "Installing Python dependencies"):
        print("✅ Dependencies installed")
    else:
        print("❌ Failed to install dependencies")
        return

    # Initialize database
    if run_command("python manage.py db-cmd init", "Initializing database"):
        print("✅ Database initialized")
    else:
        print("❌ Failed to initialize database")
        return

    # Create current season
    current_year = 2025
    if run_command(
        f"python manage.py season create {current_year} --activate",
        f"Creating {current_year} season",
    ):
        print(f"✅ Season {current_year} created and activated")
    else:
        print(f"❌ Failed to create season {current_year}")

    # Sync NFL data (this might take a while)
    print(f"🔄 Syncing NFL data for {current_year} (this may take a few minutes)...")
    if run_command(
        f"python manage.py sync all {current_year}",
        f"Syncing NFL data for {current_year}",
    ):
        print(f"✅ NFL data synced for {current_year}")
    else:
        print(
            f"⚠️  NFL data sync failed - you can run 'python manage.py sync all {current_year}' later"
        )

    print("\n🎉 Setup completed!")
    print("\nNext steps:")
    print("1. Review and update your .env file")
    print("2. Run the application: python run.py")
    print("3. Visit http://localhost:5000")
    print("4. Create your first user account")
    print("5. Create or join groups to start picking!")

    print("\nManagement commands:")
    print("- python manage.py status          # Check application status")
    print("- python manage.py user create-admin <username> <email> <password>")
    print("- python manage.py sync scores     # Update game scores")
    print("- python manage.py season list     # List all seasons")


if __name__ == "__main__":
    main()
