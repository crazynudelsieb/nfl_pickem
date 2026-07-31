import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Ensure imports like "from app import create_app" work no matter how pytest
# is invoked (console script vs. python -m pytest).
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402
from app.models import Game, Group, GroupMember, Season, Team, User  # noqa: E402


@pytest.fixture
def app():
    """App bound to a fresh in-memory database for each test."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


def _naive_utc(offset):
    """Game.game_time is a naive UTC column - match it."""
    return (datetime.now(UTC) + offset).replace(tzinfo=None)


@pytest.fixture
def season(db):
    season = Season(
        year=2025,
        name="2025 NFL Season",
        start_date=datetime(2025, 9, 1).date(),
        end_date=datetime(2026, 2, 20).date(),
        is_active=True,
        current_week=1,
        regular_season_weeks=18,
        playoff_weeks=4,
    )
    db.session.add(season)
    db.session.flush()
    return season


@pytest.fixture
def teams(db, season):
    teams = [
        Team(name=ab, abbreviation=ab, city=ab, season_id=season.id)
        for ab in ("AAA", "BBB", "CCC", "DDD")
    ]
    db.session.add_all(teams)
    db.session.flush()
    return teams


def make_user(db, username, email=None):
    user = User(username=username, email=email or f"{username}@example.com")
    user.set_password("Password1")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def users(db):
    return [make_user(db, "alice"), make_user(db, "bob")]


@pytest.fixture
def group(db, users):
    group = Group(name="Test Group", creator_id=users[0].id)
    db.session.add(group)
    db.session.flush()
    db.session.add_all(
        [
            GroupMember(user_id=users[0].id, group_id=group.id, is_admin=True),
            GroupMember(user_id=users[1].id, group_id=group.id),
        ]
    )
    db.session.commit()
    return group


@pytest.fixture
def finished_game(db, season, teams):
    """A week 1 game that kicked off yesterday and ended 30-10 for the home team."""
    game = Game(
        season_id=season.id,
        week=1,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        game_time=_naive_utc(timedelta(days=-1)),
        home_score=30,
        away_score=10,
        is_final=True,
    )
    db.session.add(game)
    db.session.commit()
    return game


@pytest.fixture
def started_game(db, season, teams):
    """A week 1 game already under way, no final score yet."""
    game = Game(
        season_id=season.id,
        week=1,
        home_team_id=teams[2].id,
        away_team_id=teams[3].id,
        game_time=_naive_utc(timedelta(hours=-1)),
        is_final=False,
    )
    db.session.add(game)
    db.session.commit()
    return game


@pytest.fixture
def upcoming_game(db, season, teams):
    """A week 2 game that has not kicked off."""
    game = Game(
        season_id=season.id,
        week=2,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        game_time=_naive_utc(timedelta(days=2)),
        is_final=False,
    )
    db.session.add(game)
    db.session.commit()
    return game
