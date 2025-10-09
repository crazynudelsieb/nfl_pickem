#!/usr/bin/env python3
"""
Script to add team logos to the database.
Uses ESPN's CDN for team logos.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Season, Team

# ESPN team logo URLs - these are publicly available
TEAM_LOGOS = {
    "ARI": "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png",
    "ATL": "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png",
    "BAL": "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png",
    "BUF": "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png",
    "CAR": "https://a.espncdn.com/i/teamlogos/nfl/500/car.png",
    "CHI": "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png",
    "CIN": "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png",
    "CLE": "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png",
    "DAL": "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png",
    "DEN": "https://a.espncdn.com/i/teamlogos/nfl/500/den.png",
    "DET": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
    "GB": "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
    "HOU": "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png",
    "IND": "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png",
    "JAX": "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png",
    "KC": "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png",
    "LV": "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png",
    "LAC": "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png",
    "LAR": "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png",
    "MIA": "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png",
    "MIN": "https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
    "NE": "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png",
    "NO": "https://a.espncdn.com/i/teamlogos/nfl/500/no.png",
    "NYG": "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png",
    "NYJ": "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png",
    "PHI": "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png",
    "PIT": "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png",
    "SF": "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png",
    "SEA": "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png",
    "TB": "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png",
    "TEN": "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png",
    "WAS": "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png",
    "WSH": "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png",
}


def update_team_logos():
    """Update team logos in the database"""
    app = create_app()

    with app.app_context():
        # Get current season
        current_season = Season.get_current_season()
        if not current_season:
            print("No current season found!")
            return

        print(f"Updating team logos for {current_season.year} season...")

        # Get all teams for current season
        teams = Team.query.filter_by(season_id=current_season.id).all()

        updated_count = 0
        for team in teams:
            logo_url = TEAM_LOGOS.get(team.abbreviation)
            if logo_url and logo_url != team.logo_url:
                print(f"Updating {team.abbreviation} ({team.full_name}): {logo_url}")
                team.logo_url = logo_url
                updated_count += 1
            elif not logo_url:
                print(f"Warning: No logo found for {team.abbreviation}")

        if updated_count > 0:
            db.session.commit()
            print(f"Successfully updated {updated_count} team logos!")
        else:
            print("No updates needed.")


if __name__ == "__main__":
    update_team_logos()
