"""Picks lock at kickoff, and a refused pick tells the user why.

In production every game stayed pickable for two hours after it started: kickoff
was stored as Europe/Vienna wall clock in a naive column and read back as UTC.
game_time is now TIMESTAMP WITH TIME ZONE. Separately, a pick refused because
the week's pick was already locked reached the user as "Network response was
not ok: 400" - the picks page never offered the switch it was going to refuse,
and the reason the server gave was thrown away. These tests pin both.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import Game, Pick, Team
from app.routes.main.routes import _calculate_team_availability
from tests.conftest import _naive_utc


def make_game(db, season, week, kickoff, home, away):
    game = Game(
        season_id=season.id,
        week=week,
        home_team_id=home.id,
        away_team_id=away.id,
        game_time=_naive_utc(kickoff),
    )
    db.session.add(game)
    db.session.commit()
    return game


def make_pick(db, user, game, team, group_id=None):
    pick = Pick(
        user_id=user.id,
        game_id=game.id,
        season_id=game.season_id,
        selected_team_id=team.id,
        group_id=group_id,
    )
    db.session.add(pick)
    db.session.commit()
    return pick


def extra_teams(db, season):
    teams = [
        Team(name=ab, abbreviation=ab, city=ab, season_id=season.id)
        for ab in ("EEE", "FFF")
    ]
    db.session.add_all(teams)
    db.session.commit()
    return teams


def login(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def submit(client, group, game, team):
    return client.post(
        "/submit-picks",
        data={f"pick_{game.id}": str(team.id), "group": group.slug},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


def test_kickoff_read_back_in_the_session_zone_still_locks_on_time():
    """PostgreSQL returns timestamptz in the session zone, not in UTC."""
    vienna = ZoneInfo("Europe/Vienna")

    kicked_off = Game(game_time=datetime.now(vienna) - timedelta(minutes=5))
    upcoming = Game(game_time=datetime.now(vienna) + timedelta(minutes=5))

    assert kicked_off.has_started() and not kicked_off.is_pickable()
    assert not upcoming.has_started() and upcoming.is_pickable()


def test_started_week_pick_closes_the_other_games(
    db, season, teams, users, started_game
):
    eee, fff = extra_teams(db, season)
    later = make_game(db, season, 1, timedelta(hours=3), home=eee, away=fff)
    pick = make_pick(db, users[0], started_game, teams[2])

    available = _calculate_team_availability(
        users[0], [started_game, later], 1, season, None, {started_game.id: pick}
    )

    locked = {"can_pick": False, "reason": "Your pick this week is locked"}
    assert available[eee.id] == locked
    assert available[fff.id] == locked
    assert available[teams[2].id]["reason"] == "Game has started"


def test_pick_on_an_upcoming_game_leaves_the_others_open(
    db, season, teams, users
):
    eee, fff = extra_teams(db, season)
    picked = make_game(db, season, 1, timedelta(hours=1), home=teams[0], away=teams[1])
    other = make_game(db, season, 1, timedelta(hours=3), home=eee, away=fff)
    pick = make_pick(db, users[0], picked, teams[0])

    available = _calculate_team_availability(
        users[0], [picked, other], 1, season, None, {picked.id: pick}
    )

    assert available[eee.id]["can_pick"] is True
    assert available[fff.id]["can_pick"] is True


def test_admin_is_not_held_by_the_lock(db, season, teams, users, started_game):
    eee, fff = extra_teams(db, season)
    later = make_game(db, season, 1, timedelta(hours=3), home=eee, away=fff)
    pick = make_pick(db, users[0], started_game, teams[2])

    available = _calculate_team_availability(
        users[0],
        [started_game, later],
        1,
        season,
        None,
        {started_game.id: pick},
        is_admin=True,
    )

    assert available[eee.id]["can_pick"] is True


def test_switching_away_from_a_started_pick_is_refused_with_its_reason(
    app, db, season, teams, users, group, started_game
):
    eee, fff = extra_teams(db, season)
    later = make_game(db, season, 1, timedelta(hours=3), home=eee, away=fff)
    pick = make_pick(db, users[0], started_game, teams[2], group_id=group.id)

    response = submit(login(app, users[0]), group, later, eee)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert body["errors"] == [
        "Your week 1 pick (DDD @ CCC) is locked because that game has "
        "already started."
    ]
    assert Pick.query.one().id == pick.id
    assert Pick.query.one().game_id == started_game.id


def test_picking_a_started_game_is_refused_with_its_reason(
    app, db, users, group, teams, started_game
):
    response = submit(login(app, users[0]), group, started_game, teams[2])

    assert response.status_code == 400
    assert response.get_json()["errors"] == [
        "This game has already started - picks lock at kickoff."
    ]
    assert Pick.query.count() == 0


def test_picking_an_upcoming_game_is_saved(
    app, db, season, users, group, upcoming_game, teams
):
    response = submit(login(app, users[0]), group, upcoming_game, teams[0])

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert Pick.query.one().group_id == group.id
