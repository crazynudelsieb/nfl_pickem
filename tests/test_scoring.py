"""Scoring rules: 1.0 win, 0.5 tie, 0.0 loss, with margin as signed tiebreaker."""

from datetime import timedelta

import pytest

from app.models import Game, Pick
from app.utils.scoring import calculate_pick_score
from tests.conftest import _naive_utc


def make_final_game(db, season, teams, home_score, away_score, week=1):
    game = Game(
        season_id=season.id,
        week=week,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        game_time=_naive_utc(timedelta(days=-1)),
        home_score=home_score,
        away_score=away_score,
        is_final=True,
    )
    db.session.add(game)
    db.session.flush()
    return game


def make_pick(db, user, game, team_id):
    pick = Pick(
        user_id=user.id,
        game_id=game.id,
        season_id=game.season_id,
        selected_team_id=team_id,
    )
    db.session.add(pick)
    db.session.flush()
    return pick


def test_correct_pick_scores_one(db, season, teams, users):
    game = make_final_game(db, season, teams, 30, 10)
    pick = make_pick(db, users[0], game, teams[0].id)

    pick.update_result()

    assert pick.is_correct is True
    assert pick.points_earned == 1.0
    assert calculate_pick_score(pick) == 1.0


def test_incorrect_pick_scores_zero(db, season, teams, users):
    game = make_final_game(db, season, teams, 30, 10)
    pick = make_pick(db, users[0], game, teams[1].id)

    pick.update_result()

    assert pick.is_correct is False
    assert pick.points_earned == 0.0


def test_tie_scores_half_and_is_neither_correct_nor_incorrect(
    db, season, teams, users
):
    game = make_final_game(db, season, teams, 17, 17)
    pick = make_pick(db, users[0], game, teams[0].id)

    pick.update_result()

    assert pick.is_correct is None
    assert pick.points_earned == 0.5
    assert pick.tiebreaker_points == 0


def test_unfinished_game_scores_nothing(db, season, teams, users, upcoming_game):
    pick = make_pick(db, users[0], upcoming_game, teams[0].id)

    assert calculate_pick_score(pick) == 0.0

    pick.update_result()
    assert pick.is_correct is None


@pytest.mark.parametrize(
    "home,away,picked_home,expected_tiebreaker",
    [
        (30, 10, True, 20.0),   # correct pick banks the margin
        (30, 10, False, -20.0),  # wrong pick pays the margin
        (21, 20, True, 1.0),
        (21, 20, False, -1.0),
    ],
)
def test_tiebreaker_is_signed_margin(
    db, season, teams, users, home, away, picked_home, expected_tiebreaker
):
    game = make_final_game(db, season, teams, home, away)
    picked = teams[0].id if picked_home else teams[1].id
    pick = make_pick(db, users[0], game, picked)

    pick.update_result()

    assert pick.tiebreaker_points == expected_tiebreaker


def test_recalculate_for_game_rescores_after_correction(
    db, season, teams, users
):
    """A corrected final score must flip the pick when recalculated."""
    game = make_final_game(db, season, teams, 30, 10)
    pick = make_pick(db, users[0], game, teams[0].id)
    pick.update_result()
    db.session.commit()
    assert pick.is_correct is True

    # ESPN corrects the result: the away team actually won.
    game.home_score = 10
    game.away_score = 30
    db.session.commit()

    updated, week = Pick.recalculate_for_game(game.id)

    assert updated == 1
    assert week == 1
    assert pick.is_correct is False
    assert pick.points_earned == 0.0
    assert pick.tiebreaker_points == -20.0
