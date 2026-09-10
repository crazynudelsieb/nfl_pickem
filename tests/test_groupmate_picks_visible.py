"""Groupmates see each other's picks as soon as they are made.

v1.3.0 hid a groupmate's pick until its game kicked off. That emptied the pick
badges on the week view and the player-picks modal for the whole run-up to the
games, although seeing who picked what has always been part of the game. These
tests keep a pick for a game that has not started visible in both places.
"""

from app.models import Group, GroupMember, Pick
from app.routes.main.routes import _get_other_users_picks


def make_pick(db, user, game, group_id):
    pick = Pick(
        user_id=user.id,
        game_id=game.id,
        season_id=game.season_id,
        selected_team_id=game.home_team_id,
        group_id=group_id,
    )
    db.session.add(pick)
    db.session.commit()
    return pick


def login(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def test_week_view_shows_groupmate_pick_before_kickoff(
    db, users, group, upcoming_game
):
    pick = make_pick(db, users[1], upcoming_game, group.id)

    others = _get_other_users_picks(group, [upcoming_game], users[0].id)

    picks = others[users[1].id]["picks"]
    assert {game_id: p.id for game_id, p in picks.items()} == {
        upcoming_game.id: pick.id
    }


def test_week_view_leaves_out_the_viewers_own_pick(
    db, users, group, upcoming_game
):
    make_pick(db, users[0], upcoming_game, group.id)

    assert _get_other_users_picks(group, [upcoming_game], users[0].id) == {}


def test_week_view_leaves_out_picks_made_for_another_group(
    db, users, group, upcoming_game
):
    other = Group(name="Other Group", creator_id=users[1].id)
    db.session.add(other)
    db.session.flush()
    db.session.add(GroupMember(user_id=users[1].id, group_id=other.id, is_admin=True))
    db.session.commit()
    make_pick(db, users[1], upcoming_game, other.id)

    assert _get_other_users_picks(group, [upcoming_game], users[0].id) == {}


def test_player_picks_modal_shows_groupmate_pick_before_kickoff(
    app, db, season, users, group, upcoming_game
):
    pick = make_pick(db, users[1], upcoming_game, group.id)

    response = login(app, users[0]).get(
        f"/api/player-picks/{users[1].id}?group_id={group.id}"
    )

    assert response.status_code == 200
    assert [p["id"] for p in response.get_json()["picks"]] == [pick.id]
