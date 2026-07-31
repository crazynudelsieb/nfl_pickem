"""Pick.create_pick must refuse picks the main submission path refuses.

The two paths used to disagree: create_pick validated team rules only, so a
group admin could create a pick on a game that had already finished and have it
scored from a known result.
"""

from app.models import Pick


def test_rejects_pick_on_finished_game(db, season, teams, users, finished_game):
    pick, message = Pick.create_pick(
        users[1].id, finished_game.id, teams[0].id, group_id=None
    )

    assert pick is None
    assert "complete" in message.lower() or "started" in message.lower()
    assert Pick.query.count() == 0


def test_rejects_pick_on_started_game(db, season, teams, users, started_game):
    pick, message = Pick.create_pick(
        users[1].id, started_game.id, teams[2].id, group_id=None
    )

    assert pick is None
    assert "started" in message.lower()
    assert Pick.query.count() == 0


def test_accepts_pick_on_upcoming_game(db, season, teams, users, upcoming_game):
    pick, message = Pick.create_pick(
        users[1].id, upcoming_game.id, teams[0].id, group_id=None
    )

    assert pick is not None, message
    assert pick.selected_team_id == teams[0].id
    assert pick.season_id == season.id


def test_rejects_playoff_pick_without_snapshot(db, season, teams, users):
    """Playoff weeks are gated on eligibility, which create_pick used to skip."""
    from datetime import timedelta

    from app.models import Game
    from tests.conftest import _naive_utc

    season.current_week = 19
    playoff_game = Game(
        season_id=season.id,
        week=19,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        game_time=_naive_utc(timedelta(days=2)),
    )
    db.session.add(playoff_game)
    db.session.commit()

    # No snapshot and no regular-season picks, so this user did not qualify.
    pick, message = Pick.create_pick(
        users[1].id, playoff_game.id, teams[0].id, group_id=None
    )

    assert pick is None
    assert message
    assert Pick.query.count() == 0


def test_rejected_pick_leaves_existing_pick_intact(
    db, season, teams, users, upcoming_game, finished_game
):
    """A refused pick must not delete the pick the user already had."""
    existing, message = Pick.create_pick(
        users[1].id, upcoming_game.id, teams[0].id, group_id=None
    )
    assert existing is not None, message
    db.session.commit()
    existing_id = existing.id

    # Same season, different week - the finished game must still be refused
    # without disturbing the pick already on record.
    pick, _ = Pick.create_pick(
        users[1].id, finished_game.id, teams[0].id, group_id=None
    )

    assert pick is None
    assert db.session.get(Pick, existing_id) is not None
