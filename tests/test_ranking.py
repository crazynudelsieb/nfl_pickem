"""The tiebreak chain, and what happens when it runs out at a cutoff."""

import pytest

from app.utils.ranking import (
    expand_ties_at_cutoff,
    playoff_merit_key,
    season_merit_key,
    sort_playoff_leaderboard,
    sort_season_leaderboard,
)


def entry(user_id, score, tiebreaker=0.0, wins=0, missed=0, streak=0):
    return {
        "user_id": user_id,
        "total_score": score,
        "tiebreaker_points": tiebreaker,
        "wins": wins,
        "missed_games": missed,
        "longest_streak": streak,
    }


def order(entries):
    return [e["user_id"] for e in entries]


def test_score_outranks_everything():
    board = [entry(1, 10.0, tiebreaker=99), entry(2, 12.0, tiebreaker=-99)]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_margin_breaks_a_score_tie():
    board = [entry(1, 12.0, tiebreaker=30), entry(2, 12.0, tiebreaker=45)]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_outright_wins_break_a_margin_tie():
    """12W/0T beats 11W/2T at the same score - decisive results count."""
    board = [
        entry(1, 12.0, tiebreaker=40, wins=11),
        entry(2, 12.0, tiebreaker=40, wins=12),
    ]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_fewer_missed_games_breaks_a_wins_tie():
    board = [
        entry(1, 12.0, tiebreaker=40, wins=12, missed=3),
        entry(2, 12.0, tiebreaker=40, wins=12, missed=0),
    ]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_longest_streak_breaks_a_missed_games_tie():
    board = [
        entry(1, 12.0, tiebreaker=40, wins=12, missed=1, streak=3),
        entry(2, 12.0, tiebreaker=40, wins=12, missed=1, streak=7),
    ]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_loss_streak_ranks_below_win_streak():
    board = [
        entry(1, 12.0, tiebreaker=40, wins=12, missed=1, streak=-4),
        entry(2, 12.0, tiebreaker=40, wins=12, missed=1, streak=2),
    ]

    assert order(sort_season_leaderboard(board)) == [2, 1]


def test_fully_tied_players_sort_deterministically():
    """Identical on every merit key: order must not depend on input order."""
    a = [entry(3, 12.0, 40, 12, 1, 5), entry(1, 12.0, 40, 12, 1, 5)]
    b = [entry(1, 12.0, 40, 12, 1, 5), entry(3, 12.0, 40, 12, 1, 5)]

    assert order(sort_season_leaderboard(a)) == order(sort_season_leaderboard(b))


def test_playoff_regular_season_breaks_the_tie():
    """Higher regular season seed takes a tie on playoff form."""
    board = [
        {"user_id": 1, "playoff_wins": 2, "tiebreaker_points": 10,
         "regular_score": 11.0},
        {"user_id": 2, "playoff_wins": 2, "tiebreaker_points": 10,
         "regular_score": 14.0},
    ]

    assert order(sort_playoff_leaderboard(board)) == [2, 1]


def test_playoff_accepts_total_tiebreaker_alias():
    """is_superbowl_eligible spells the key differently - both must work."""
    board = [
        {"user_id": 1, "playoff_wins": 2, "total_tiebreaker": 5, "regular_score": 9},
        {"user_id": 2, "playoff_wins": 2, "total_tiebreaker": 25, "regular_score": 9},
    ]

    assert order(sort_playoff_leaderboard(board)) == [2, 1]


# --- cutoff behaviour ------------------------------------------------------


def test_cutoff_is_exact_when_players_are_separable():
    board = sort_season_leaderboard(
        [entry(i, score) for i, score in enumerate([15.0, 14.0, 13.0, 12.0, 11.0])]
    )

    assert expand_ties_at_cutoff(board, 4) == 4


def test_cutoff_widens_for_a_genuine_tie():
    """4th and 5th identical on every key: both get in, nobody is cut."""
    board = sort_season_leaderboard(
        [
            entry(1, 15.0, 50, 15),
            entry(2, 14.0, 40, 14),
            entry(3, 13.0, 30, 13),
            entry(4, 12.0, 20, 12),
            entry(5, 12.0, 20, 12),
        ]
    )

    assert expand_ties_at_cutoff(board, 4) == 5


def test_cutoff_widens_across_several_tied_players():
    board = sort_season_leaderboard(
        [entry(1, 15.0), entry(2, 12.0), entry(3, 12.0), entry(4, 12.0)]
    )

    assert expand_ties_at_cutoff(board, 2) == 4


def test_cutoff_does_not_widen_when_margin_separates():
    """Same score but different margin is separable - no widening."""
    board = sort_season_leaderboard(
        [entry(1, 15.0), entry(2, 12.0, tiebreaker=30), entry(3, 12.0, tiebreaker=10)]
    )

    assert expand_ties_at_cutoff(board, 2) == 2


def test_cutoff_handles_short_and_empty_fields():
    assert expand_ties_at_cutoff([], 4) == 0
    assert expand_ties_at_cutoff([entry(1, 10.0)], 4) == 1
    assert expand_ties_at_cutoff([entry(1, 10.0)], 0) == 0


@pytest.mark.parametrize("key_fn", [season_merit_key, playoff_merit_key])
def test_merit_keys_exclude_user_id(key_fn):
    """A merit key must not see the id, or nothing would ever tie."""
    assert key_fn({"user_id": 1}) == key_fn({"user_id": 999})
