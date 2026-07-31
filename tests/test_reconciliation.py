"""Score corrections on already-final games must reach the picks.

update_live_scores() only queries games with is_final == False, so once ESPN
marked a game final nothing ever re-read it: a corrected score left the game
and every pick on it wrong permanently. reconcile_final_scores() closes that.
"""

from datetime import timedelta

import pytest

from app.models import Pick
from app.utils.data_sync import DataSync
from tests.conftest import _naive_utc


def espn_competition(home_score, away_score, completed=True):
    """Minimal shape of the ESPN /summary header.competition block."""
    return {
        "status": {"type": {"completed": completed}},
        "competitors": [
            {"homeAway": "home", "score": str(home_score)},
            {"homeAway": "away", "score": str(away_score)},
        ],
    }


@pytest.fixture
def sync(monkeypatch):
    """DataSync with the network stubbed out."""
    sync = DataSync()

    def unexpected_call(*args, **kwargs):
        raise AssertionError("test made a real HTTP request")

    monkeypatch.setattr(sync, "_make_api_request", unexpected_call)
    return sync


def stub_espn(monkeypatch, sync, competition):
    monkeypatch.setattr(sync, "_fetch_competition", lambda game: competition)


@pytest.fixture
def scored_pick(db, season, teams, users, finished_game):
    """alice correctly picked the 30-10 home-team winner."""
    finished_game.espn_id = "401547001"
    pick = Pick(
        user_id=users[0].id,
        game_id=finished_game.id,
        season_id=season.id,
        selected_team_id=teams[0].id,
    )
    db.session.add(pick)
    db.session.flush()  # resolve pick.game before scoring reads it
    pick.update_result()
    db.session.commit()

    assert pick.is_correct is True
    assert pick.points_earned == 1.0
    return pick


def test_correction_flips_pick_result(
    db, monkeypatch, sync, finished_game, scored_pick
):
    # ESPN now reports the away team actually won 30-10.
    stub_espn(monkeypatch, sync, espn_competition(home_score=10, away_score=30))

    success, message = sync.reconcile_final_scores()

    assert success, message
    assert finished_game.home_score == 10
    assert finished_game.away_score == 30
    assert scored_pick.is_correct is False
    assert scored_pick.points_earned == 0.0
    assert scored_pick.tiebreaker_points == -20.0


def test_margin_correction_updates_tiebreaker(
    db, monkeypatch, sync, finished_game, scored_pick
):
    """Winner unchanged, margin corrected 20 -> 14: the pick stays correct."""
    stub_espn(monkeypatch, sync, espn_competition(home_score=24, away_score=10))

    success, message = sync.reconcile_final_scores()

    assert success, message
    assert scored_pick.is_correct is True
    assert scored_pick.points_earned == 1.0
    assert scored_pick.tiebreaker_points == 14.0


def test_unchanged_score_is_a_no_op(
    db, monkeypatch, sync, finished_game, scored_pick
):
    stub_espn(monkeypatch, sync, espn_competition(home_score=30, away_score=10))

    success, message = sync.reconcile_final_scores()

    assert success
    assert "no corrections" in message.lower()
    assert scored_pick.is_correct is True
    assert scored_pick.tiebreaker_points == 20.0


def test_espn_reporting_incomplete_does_not_unscore(
    db, monkeypatch, sync, finished_game, scored_pick
):
    """A transient 'not completed' from ESPN must not unsettle scored picks."""
    stub_espn(
        monkeypatch,
        sync,
        espn_competition(home_score=0, away_score=0, completed=False),
    )

    success, _ = sync.reconcile_final_scores()

    assert success
    assert finished_game.home_score == 30
    assert finished_game.away_score == 10
    assert scored_pick.is_correct is True


def test_games_outside_window_are_not_fetched(
    db, monkeypatch, sync, finished_game, scored_pick
):
    """The window bounds API cost - an old game must not be re-fetched."""
    finished_game.game_time = _naive_utc(timedelta(days=-30))
    db.session.commit()

    def must_not_be_called(game):
        raise AssertionError("game outside the window was fetched")

    monkeypatch.setattr(sync, "_fetch_competition", must_not_be_called)

    success, message = sync.reconcile_final_scores(within_hours=48)

    assert success
    assert "no recently finalized games" in message.lower()


def test_game_without_espn_id_is_skipped(db, monkeypatch, sync, finished_game):
    finished_game.espn_id = None
    db.session.commit()

    def must_not_be_called(game):
        raise AssertionError("game without an espn_id was fetched")

    monkeypatch.setattr(sync, "_fetch_competition", must_not_be_called)

    success, _ = sync.reconcile_final_scores()

    assert success


def test_update_game_score_finalizes_open_game(
    db, monkeypatch, sync, started_game
):
    """The live path still works after sharing the parser with reconciliation."""
    started_game.espn_id = "401547002"
    db.session.commit()
    stub_espn(monkeypatch, sync, espn_competition(home_score=28, away_score=21))

    changed = sync._update_game_score(started_game)

    assert changed is True
    assert started_game.is_final is True
    assert started_game.home_score == 28
    assert started_game.away_score == 21


def test_update_game_score_no_change_returns_false(
    db, monkeypatch, sync, started_game
):
    started_game.espn_id = "401547003"
    started_game.home_score = 14
    started_game.away_score = 7
    db.session.commit()
    stub_espn(
        monkeypatch,
        sync,
        espn_competition(home_score=14, away_score=7, completed=False),
    )

    assert sync._update_game_score(started_game) is False
    assert started_game.is_final is False


def test_update_game_score_final_without_scores_is_refused(
    db, monkeypatch, sync, started_game
):
    """Guards the 0-0 phantom-tie case: no scores means no finalization."""
    started_game.espn_id = "401547004"
    db.session.commit()
    stub_espn(
        monkeypatch,
        sync,
        {"status": {"type": {"completed": True}}, "competitors": []},
    )

    assert sync._update_game_score(started_game) is False
    assert started_game.is_final is False


def test_parse_competition_reads_scores_and_status():
    home, away, is_final = DataSync._parse_competition(
        espn_competition(home_score=21, away_score=17)
    )

    assert (home, away, is_final) == (21, 17, True)


def test_parse_competition_treats_zero_as_zero():
    """'0' is falsy-adjacent in the original parser - pin the behaviour."""
    home, away, _ = DataSync._parse_competition(
        espn_competition(home_score=0, away_score=0)
    )

    assert (home, away) == (0, 0)
