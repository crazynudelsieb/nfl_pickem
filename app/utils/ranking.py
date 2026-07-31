"""Leaderboard ordering and the tiebreak chain.

Ranking used to be an inline ``sort(key=lambda x: (score, tiebreaker))`` in four
separate places. Two keys are not enough: players tie on both routinely (after
week 1, everyone who picked a winner in a game decided by the same margin has
an identical pair), and the sort was left to fall back on database row order -
which Postgres does not guarantee, so tied players could swap places between
page loads and the playoff cutoff could land differently on each run.

Every key below is something a player did on the field. The chain only runs out
when two players are indistinguishable across all of them, and at the playoff
cutoff that case is handled by admitting both rather than picking one - see
``expand_ties_at_cutoff``.

Keys are written for an ascending sort, so "higher is better" values are
negated. Do not pass reverse=True.
"""


def _first_present(entry, *names, default=0):
    """Read the first key that exists.

    The leaderboard builders grew up separately and spell the same quantity
    differently ("tiebreaker_points" vs "total_tiebreaker"). Rather than rename
    keys the templates already read, resolve the aliases here.
    """
    for name in names:
        if name in entry and entry[name] is not None:
            return entry[name]
    return default


def season_merit_key(entry):
    """Everything the player earned, most significant first.

    1. total_score      - the score itself
    2. tiebreaker_points- cumulative signed margin: reward confident wins,
                          punish being blown out
    3. wins             - outright wins beat the same score made of ties
                          (12W/0T places above 11W/2T)
    4. missed_games     - showing up every week beats skipping (fewer first)
    5. longest_streak   - the better sustained run
    """
    return (
        -_first_present(entry, "total_score"),
        -_first_present(entry, "tiebreaker_points", "total_tiebreaker"),
        -_first_present(entry, "wins"),
        _first_present(entry, "missed_games"),
        -_first_present(entry, "longest_streak"),
    )


def season_sort_key(entry):
    """Merit, then user id purely so the order is reproducible.

    Reaching the id means two players are identical on every measured key.
    That is a stable presentation order, not a verdict - anything that cuts a
    field at a rank must use expand_ties_at_cutoff so a genuine tie is never
    decided by which row the database happened to return first.
    """
    return season_merit_key(entry) + (_first_present(entry, "user_id"),)


def playoff_merit_key(entry):
    """Playoff ordering: playoff form first, regular season as the decider.

    1. playoff_wins     - wins in the playoff rounds
    2. tiebreaker_points- season-long signed margin
    3. regular_score    - the better regular season finishes ahead, the usual
                          convention that the higher seed takes the tie
    """
    return (
        -_first_present(entry, "playoff_wins"),
        -_first_present(entry, "tiebreaker_points", "total_tiebreaker"),
        -_first_present(entry, "regular_score", "regular_season_score"),
    )


def playoff_sort_key(entry):
    """Playoff merit, then user id for reproducibility. See season_sort_key."""
    return playoff_merit_key(entry) + (_first_present(entry, "user_id"),)


def sort_season_leaderboard(entries):
    """Sort regular season / overall standings in place and return them."""
    entries.sort(key=season_sort_key)
    return entries


def sort_playoff_leaderboard(entries):
    """Sort playoff standings in place and return them."""
    entries.sort(key=playoff_sort_key)
    return entries


def expand_ties_at_cutoff(entries, spots, merit_key=season_merit_key):
    """How many entries qualify when `spots` places are available.

    Returns `spots`, unless the player sitting on the cutoff line is tied on
    every merit key with the players just behind them - in which case the field
    widens to include all of them.

    Cutting between players who are genuinely equal would decide a season on
    row order. Admitting both is the answer real competitions use, and it is
    self-limiting: it only triggers when nothing measurable separates them.

    Args:
        entries: Leaderboard rows, already sorted.
        spots: Number of places nominally available.
        merit_key: Key function excluding the stable-id component.

    Returns:
        int: Number of entries that qualify (>= spots, <= len(entries)).
    """
    if spots <= 0:
        return 0
    if len(entries) <= spots:
        return len(entries)

    boundary = merit_key(entries[spots - 1])

    qualified = spots
    while qualified < len(entries) and merit_key(entries[qualified]) == boundary:
        qualified += 1

    return qualified
