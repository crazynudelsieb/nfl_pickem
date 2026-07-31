"""Playoff qualification against a real leaderboard, not a synthetic one.

The cutoff used to be a bare `rank <= playoff_spots` over a two-key sort, so
players who were level on both keys were split by whatever order the database
returned rows in.
"""

from datetime import timedelta

from app.models import Game, Group, GroupMember, Pick, RegularSeasonSnapshot, Season
from tests.conftest import _naive_utc, make_user


def final_game(db, season, home, away, home_score, away_score, week=1):
    game = Game(
        season_id=season.id,
        week=week,
        home_team_id=home.id,
        away_team_id=away.id,
        game_time=_naive_utc(timedelta(days=-1)),
        home_score=home_score,
        away_score=away_score,
        is_final=True,
    )
    db.session.add(game)
    db.session.flush()
    return game


def finished_season(db):
    """A one-week 'season' so ranking is easy to control precisely."""
    season = Season(
        year=2024,
        name="2024 NFL Season",
        start_date=_naive_utc(timedelta(days=-30)).date(),
        end_date=_naive_utc(timedelta(days=30)).date(),
        is_active=True,
        current_week=1,
        regular_season_weeks=1,
        playoff_weeks=4,
    )
    db.session.add(season)
    db.session.flush()
    return season


def make_group(db, creator, playoff_spots):
    group = Group(
        name=f"Spots{playoff_spots}",
        creator_id=creator.id,
        playoff_spots=playoff_spots,
    )
    db.session.add(group)
    db.session.flush()
    return group


def enrol(db, group, user):
    db.session.add(GroupMember(user_id=user.id, group_id=group.id))
    db.session.flush()


def score_pick(db, user, game, team_id, group):
    """A group-scoped pick, scored. Users default to per-group picks."""
    pick = Pick(
        user_id=user.id,
        game_id=game.id,
        season_id=game.season_id,
        selected_team_id=team_id,
        group_id=group.id,
    )
    db.session.add(pick)
    db.session.flush()
    pick.update_result()
    return pick


def eligible_ids(snapshots):
    return {s.user_id for s in snapshots if s.is_playoff_eligible}


def test_cutoff_admits_players_tied_on_every_key(db, teams):
    """Three players identical on everything, two spots: all three get in."""
    season = finished_season(db)
    game = final_game(db, season, teams[0], teams[1], 27, 20)

    players = [make_user(db, f"p{i}") for i in range(3)]
    group = make_group(db, players[0], playoff_spots=2)
    for player in players:
        enrol(db, group, player)
        score_pick(db, player, game, teams[0].id, group)  # same pick, same margin
    db.session.commit()

    snapshots = RegularSeasonSnapshot.create_snapshot(season.id, group_id=group.id)

    assert eligible_ids(snapshots) == {p.id for p in players}, (
        "tied players must not be split by row order"
    )


def test_cutoff_holds_when_margins_separate_players(db, teams):
    """Same score, different margins: the third player is properly cut."""
    season = finished_season(db)
    blowout = final_game(db, season, teams[0], teams[1], 40, 3)
    squeaker = final_game(db, season, teams[2], teams[3], 17, 16)

    big = make_user(db, "big")
    mid = make_user(db, "mid")
    small = make_user(db, "small")

    group = make_group(db, big, playoff_spots=2)
    for player in (big, mid, small):
        enrol(db, group, player)

    score_pick(db, big, blowout, teams[0].id, group)     # +37
    score_pick(db, mid, blowout, teams[0].id, group)     # +37
    score_pick(db, small, squeaker, teams[2].id, group)  # +1
    db.session.commit()

    snapshots = RegularSeasonSnapshot.create_snapshot(season.id, group_id=group.id)

    assert eligible_ids(snapshots) == {big.id, mid.id}


def test_cutoff_separates_equal_scores_by_wins(db, teams):
    """One win beats a tie-and-a-half at the same score, so no widening."""
    season = finished_season(db)
    decided = final_game(db, season, teams[0], teams[1], 24, 17)
    drawn = final_game(db, season, teams[2], teams[3], 20, 20)

    winner = make_user(db, "winner")
    drawer = make_user(db, "drawer")

    group = make_group(db, winner, playoff_spots=1)
    for player in (winner, drawer):
        enrol(db, group, player)

    score_pick(db, winner, decided, teams[0].id, group)  # 1.0
    score_pick(db, drawer, drawn, teams[2].id, group)    # 0.5
    db.session.commit()

    snapshots = RegularSeasonSnapshot.create_snapshot(season.id, group_id=group.id)

    assert eligible_ids(snapshots) == {winner.id}


def test_ranking_is_stable_across_repeated_builds(db, teams):
    """The same standings must come back in the same order every time."""
    from app.models import User

    season = finished_season(db)
    game = final_game(db, season, teams[0], teams[1], 27, 20)

    players = [make_user(db, f"u{i}") for i in range(4)]
    group = make_group(db, players[0], playoff_spots=2)
    for player in players:
        enrol(db, group, player)
        score_pick(db, player, game, teams[0].id, group)
    db.session.commit()

    orders = [
        [
            row["user_id"]
            for row in User.get_season_leaderboard(season.id, group_id=group.id)
        ]
        for _ in range(5)
    ]

    assert all(order == orders[0] for order in orders)
    assert len(set(orders[0])) == 4
