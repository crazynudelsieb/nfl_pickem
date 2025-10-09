"""
Timezone utility functions for the NFL Pick'em application
"""

from datetime import datetime, timezone

import pytz
from flask import current_app


def get_app_timezone():
    """Get the application's configured timezone"""
    try:
        timezone_name = current_app.config.get("TIMEZONE", "UTC")
        return pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        # Fallback to UTC if timezone is invalid
        return pytz.UTC


def get_current_time():
    """Get current time in the application's timezone"""
    app_tz = get_app_timezone()
    return datetime.now(app_tz)


def get_utc_time():
    """Get current time in UTC"""
    return datetime.now(timezone.utc)


def convert_to_app_timezone(dt):
    """Convert a datetime to the application's timezone"""
    if dt is None:
        return None

    app_tz = get_app_timezone()

    # If datetime is naive, assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(app_tz)


def convert_to_utc(dt):
    """Convert a datetime to UTC"""
    if dt is None:
        return None

    # If datetime is naive, assume it's in the application timezone
    if dt.tzinfo is None:
        app_tz = get_app_timezone()
        dt = app_tz.localize(dt)

    return dt.astimezone(timezone.utc)


def format_game_time(dt, format_str="%a %m/%d at %I:%M %p"):
    """Format a game time in the application's timezone"""
    if dt is None:
        return "TBD"

    app_time = convert_to_app_timezone(dt)
    return app_time.strftime(format_str)
