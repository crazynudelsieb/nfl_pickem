"""Pick rules freeze once a group's season is under way.

Rules used to be editable at any moment, including after playoff snapshots were
taken. Changing pick_team_once mid-season retroactively legalises picks that
were rejected at the time, and changing playoff_spots moves the cutoff under
players who have already finished their regular season.
"""

from app.models import Pick


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


def test_rules_unlocked_before_any_pick(db, season, group):
    assert group.rules_locked_reason() is None


def test_rules_lock_once_the_group_has_a_pick(
    db, season, users, group, upcoming_game
):
    make_pick(db, users[0], upcoming_game, group.id)

    reason = group.rules_locked_reason()

    assert reason is not None
    assert season.name in reason


def test_apply_rules_succeeds_while_unlocked(db, season, group):
    applied, reason = group.apply_rules(
        pick_team_once=False,
        no_repeat_opponent=False,
        playoff_spots=6,
        superbowl_spots=3,
    )

    assert applied is True
    assert reason is None
    assert group.pick_team_once is False
    assert group.playoff_spots == 6


def test_apply_rules_refused_once_locked(
    db, season, users, group, upcoming_game
):
    make_pick(db, users[0], upcoming_game, group.id)

    applied, reason = group.apply_rules(
        pick_team_once=False,
        no_repeat_opponent=False,
        playoff_spots=8,
        superbowl_spots=4,
    )

    assert applied is False
    assert reason is not None
    # Stored rules must be untouched.
    assert group.pick_team_once is True
    assert group.no_repeat_opponent is True
    assert group.playoff_spots == 4
    assert group.superbowl_spots == 2


def test_resubmitting_identical_rules_is_not_reported_as_refused(
    db, season, users, group, upcoming_game
):
    """Saving the group name shouldn't warn about rules that didn't change."""
    make_pick(db, users[0], upcoming_game, group.id)

    applied, reason = group.apply_rules(
        pick_team_once=group.pick_team_once,
        no_repeat_opponent=group.no_repeat_opponent,
        playoff_spots=group.playoff_spots,
        superbowl_spots=group.superbowl_spots,
    )

    assert applied is False
    assert reason is None


def test_another_groups_picks_do_not_lock_this_group(
    db, season, users, group, upcoming_game
):
    """A group created mid-season stays configurable until its own first pick."""
    from app.models import Group, GroupMember

    fresh = Group(name="Late Joiners", creator_id=users[0].id)
    db.session.add(fresh)
    db.session.flush()
    db.session.add(GroupMember(user_id=users[0].id, group_id=fresh.id, is_admin=True))
    db.session.commit()

    make_pick(db, users[0], upcoming_game, group.id)

    assert group.rules_locked_reason() is not None
    assert fresh.rules_locked_reason() is None


def test_global_picks_do_not_lock_group_rules(
    db, season, users, group, upcoming_game
):
    """Global picks run on DEFAULT_RULES, so they say nothing about this group."""
    make_pick(db, users[0], upcoming_game, group_id=None)

    assert group.rules_locked_reason() is None


def test_edit_route_refuses_locked_rule_change(
    app, db, season, users, group, upcoming_game
):
    make_pick(db, users[0], upcoming_game, group.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(users[0].id)
        sess["_fresh"] = True

    response = client.post(
        f"/groups/{group.id}/edit",
        data={
            "name": "Renamed Group",
            "description": "",
            "is_public": "y",
            "max_members": 50,
            "pick_team_once": "",
            "no_repeat_opponent": "",
            "playoff_spots": 10,
            "superbowl_spots": 4,
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)

    db.session.refresh(group)
    # Cosmetic edit landed, rules did not.
    assert group.name == "Renamed Group"
    assert group.pick_team_once is True
    assert group.playoff_spots == 4
    assert group.superbowl_spots == 2
