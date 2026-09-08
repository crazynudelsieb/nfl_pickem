"""Teams are per-season rows, so the same franchise repeats across seasons.

`espn_id` shipped with a global UNIQUE index, which made the second season's
teams impossible to insert: the first rollover attempt died on "duplicate key
value violates unique constraint ix_teams_espn_id" and the app stayed on the
old, finished season. Nothing caught it because the fixtures never set espn_id
and no deployment had ever reached a second season.
"""

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import Season, Team
from app.utils.schema_guard import ensure_schema


def make_season(db, year):
    season = Season(
        year=year,
        name=f"{year} NFL Season",
        start_date=date(year, 9, 1),
        end_date=date(year + 1, 2, 15),
    )
    db.session.add(season)
    db.session.flush()
    return season


def cardinals(season_id, espn_id="22"):
    return Team(
        name="Cardinals",
        city="Arizona",
        abbreviation="ARI",
        espn_id=espn_id,
        season_id=season_id,
    )


def test_the_same_franchise_can_exist_in_two_seasons(db):
    """The rollover case: 2026's teams land alongside 2025's."""
    old = make_season(db, 2025)
    new = make_season(db, 2026)

    db.session.add(cardinals(old.id))
    db.session.add(cardinals(new.id))
    db.session.commit()

    assert Team.query.filter_by(espn_id="22").count() == 2


def test_a_franchise_cannot_be_duplicated_within_one_season(db):
    """Per-season uniqueness is the invariant that does hold."""
    season = make_season(db, 2025)

    db.session.add(cardinals(season.id))
    db.session.commit()

    db.session.add(cardinals(season.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def teams_index(db, name):
    return {i["name"]: i for i in inspect(db.engine).get_indexes("teams")}[name]


def test_schema_guard_relaxes_a_legacy_global_unique_index(db):
    """An already-deployed database keeps the old index until the guard runs."""
    db.session.execute(db.text("DROP INDEX ix_teams_espn_id"))
    db.session.execute(db.text("CREATE UNIQUE INDEX ix_teams_espn_id ON teams (espn_id)"))
    db.session.commit()
    assert teams_index(db, "ix_teams_espn_id")["unique"]

    ensure_schema()

    assert not teams_index(db, "ix_teams_espn_id")["unique"]

    # And the rollover it was blocking now goes through.
    old = make_season(db, 2025)
    new = make_season(db, 2026)
    db.session.add(cardinals(old.id))
    db.session.add(cardinals(new.id))
    db.session.commit()

    assert Team.query.filter_by(espn_id="22").count() == 2


def test_schema_guard_is_idempotent(db):
    """It runs on every startup, so a second pass must be a no-op."""
    ensure_schema()
    ensure_schema()

    assert not teams_index(db, "ix_teams_espn_id")["unique"]
